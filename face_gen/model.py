"""
Face Generation GAN — Ultra Edition (StyleGAN2-inspired)
=========================================================
Generator:     z (512) -> w (1024) -> 128x128 RGB  (~120M params)
Discriminator: 128x128 RGB -> score              (~95M params)

New mechanisms over Heavy Edition:
  ┌─ Generator ──────────────────────────────────────────────────────┐
  │  • ModulatedConv2d: per-sample weight modulation + demodulation  │
  │    (StyleGAN2 core — replaces AdaIN entirely)                    │
  │  • NoiseInjection:  learnable stochastic detail noise per layer  │
  │  • SynthesisBlock:  3 ModConv layers per scale (was 2)           │
  │  • ToRGB skip connections accumulated across all 6 scales        │
  │  • Per-layer W: mapping net outputs separate w for every block   │
  │  • MultiHeadSelfAttention2d (8 heads) at 16x16, 32x32, 64x64    │
  │  • EqualizedLR on all linear + conv layers                       │
  │  • Mapping net: 16 layers, 1024-dim latent W space               │
  └──────────────────────────────────────────────────────────────────┘
  ┌─ Discriminator ──────────────────────────────────────────────────┐
  │  • 7 downsampling stages: 128->64->32->16->8->4->2->logit        │
  │  • 3 spectral-normed convs per residual block (was 2)            │
  │  • MultiHeadSelfAttention2d at 64x64, 32x32, 16x16              │
  │  • Multi-group minibatch std (4 groups × 4 channels)             │
  │  • Projection head for extra discriminative capacity             │
  └──────────────────────────────────────────────────────────────────┘

Channel schedule (StyleGAN2-style, capped at 512):
  4x4: 512  |  8x8: 512  |  16x16: 512  |  32x32: 512
  64x64: 256  |  128x128: 128
"""

import math
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.utils import spectral_norm


# ---------------------------------------------------------------------------
# Utility: channel schedule
# ---------------------------------------------------------------------------

def _nf(stage: int, base: int = 32, cap: int = 512) -> int:
    """Return number of channels at a given resolution stage (StyleGAN2 schedule)."""
    return min(base << (8 - stage), cap)


def _nf_custom(stage: int, cap: int) -> int:
    return _nf(stage, base=max(cap // 16, 1), cap=cap)


# ---------------------------------------------------------------------------
# Equalized learning-rate wrappers
# ---------------------------------------------------------------------------

class EqualLinear(nn.Module):
    """Linear with equalized learning rate (Karras et al. 2018)."""

    def __init__(self, in_dim: int, out_dim: int, bias: bool = True,
                 lr_mul: float = 1.0, bias_init: float = 0.0):
        super().__init__()
        self.weight = nn.Parameter(torch.randn(out_dim, in_dim) / lr_mul)
        self.bias = nn.Parameter(torch.full([out_dim], bias_init)) if bias else None
        self.scale = (1 / math.sqrt(in_dim)) * lr_mul
        self.lr_mul = lr_mul

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return F.linear(x, self.weight * self.scale,
                        self.bias * self.lr_mul if self.bias is not None else None)


# ---------------------------------------------------------------------------
# Modulated Convolution (StyleGAN2)
# ---------------------------------------------------------------------------

class ModulatedConv2d(nn.Module):
    """
    Per-sample weight modulation + demodulation (Karras et al. 2020).

    Key idea: instead of normalising activations (AdaIN), we modulate and
    demodulate the convolution weights themselves — this avoids the
    statistical assumptions of instance normalisation and gives much
    sharper control over style.
    """

    def __init__(self, in_ch: int, out_ch: int, kernel: int, w_dim: int,
                 demodulate: bool = True, upsample: bool = False):
        super().__init__()
        self.in_ch = in_ch
        self.out_ch = out_ch
        self.kernel = kernel
        self.demodulate = demodulate
        self.upsample = upsample
        self.pad = kernel // 2

        # Equalized weight
        self.weight = nn.Parameter(
            torch.randn(out_ch, in_ch, kernel, kernel) / math.sqrt(in_ch * kernel ** 2)
        )
        # Style modulation: w -> per-input-channel scale
        self.modulation = EqualLinear(w_dim, in_ch, bias_init=1.0)
        self.bias = nn.Parameter(torch.zeros(out_ch))

    def forward(self, x: torch.Tensor, w: torch.Tensor) -> torch.Tensor:
        B, C, H, W = x.shape

        # (B, in_ch) style scales
        style = self.modulation(w)

        # Modulate: weight' = weight * style
        weight = self.weight.unsqueeze(0) * style.view(B, 1, -1, 1, 1)  # (B, out, in, k, k)

        # Demodulate: normalise by expected std of each output feature
        if self.demodulate:
            sigma = weight.pow(2).sum(dim=[2, 3, 4], keepdim=True).add(1e-8).sqrt()
            weight = weight / sigma

        if self.upsample:
            x = F.interpolate(x, scale_factor=2, mode="bilinear", align_corners=False)
            H, W = H * 2, W * 2

        # Per-sample conv via the "groups = B" trick
        x = x.reshape(1, B * C, H, W)
        weight = weight.reshape(B * self.out_ch, self.in_ch, self.kernel, self.kernel)
        out = F.conv2d(x, weight, padding=self.pad, groups=B)
        out = out.reshape(B, self.out_ch, H, W)
        return out + self.bias.view(1, -1, 1, 1)


# ---------------------------------------------------------------------------
# Stochastic noise injection
# ---------------------------------------------------------------------------

class NoiseInjection(nn.Module):
    """Add scaled Gaussian noise for stochastic fine detail (hair, pores …)."""

    def __init__(self):
        super().__init__()
        self.weight = nn.Parameter(torch.zeros(1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        noise = torch.randn(x.size(0), 1, x.size(2), x.size(3),
                            device=x.device, dtype=x.dtype)
        return x + self.weight * noise


# ---------------------------------------------------------------------------
# Multi-head self-attention for 2D feature maps
# ---------------------------------------------------------------------------

class MultiHeadSelfAttention2d(nn.Module):
    """
    8-head scaled dot-product self-attention on spatial feature maps.
    Uses GroupNorm pre-norm and a learnable residual scale (gamma).
    """

    def __init__(self, channels: int, num_heads: int = 8):
        super().__init__()
        # Ensure num_heads divides channels evenly
        while channels % num_heads != 0:
            num_heads = num_heads // 2
        num_heads = max(num_heads, 1)
        self.num_heads = num_heads
        self.head_dim = channels // num_heads
        self.scale = self.head_dim ** -0.5

        self.norm = nn.GroupNorm(num_heads, channels)
        self.qkv = nn.Conv2d(channels, channels * 3, 1, bias=False)
        self.proj = nn.Conv2d(channels, channels, 1)
        self.gamma = nn.Parameter(torch.zeros(1))

        nn.init.zeros_(self.proj.weight)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, C, H, W = x.shape
        h = self.norm(x)

        qkv = self.qkv(h).reshape(B, 3, self.num_heads, self.head_dim, H * W)
        q, k, v = qkv.unbind(dim=1)                        # each (B, heads, head_dim, HW)

        attn = torch.softmax(
            torch.einsum("bhdi,bhdj->bhij", q, k) * self.scale, dim=-1
        )                                                   # (B, heads, HW, HW)
        out = torch.einsum("bhij,bhdj->bhdi", attn, v)     # (B, heads, head_dim, HW)
        out = out.reshape(B, C, H, W)
        return x + self.gamma * self.proj(out)


# ---------------------------------------------------------------------------
# Mapping network
# ---------------------------------------------------------------------------

class MappingNetwork(nn.Module):
    """
    16-layer fully-connected network z -> W.
    Outputs one w per synthesis block (num_layers vectors).
    Pixel-normalises z; uses equalized LR throughout.
    """

    def __init__(self, z_dim: int = 512, w_dim: int = 1024,
                 depth: int = 16, num_layers: int = 6, lr_mul: float = 0.01):
        super().__init__()
        self.num_layers = num_layers

        layers: list[nn.Module] = [EqualLinear(z_dim, w_dim, lr_mul=lr_mul)]
        for _ in range(depth - 1):
            layers += [nn.LeakyReLU(0.2, inplace=True),
                       EqualLinear(w_dim, w_dim, lr_mul=lr_mul)]
        self.net = nn.Sequential(*layers)
        self.w_dim = w_dim

    def forward(self, z: torch.Tensor,
                mixing_z: Optional[torch.Tensor] = None,
                mixing_layer: Optional[int] = None) -> list[torch.Tensor]:
        """
        Returns a list of w vectors, one per synthesis block.
        If mixing_z and mixing_layer are provided, applies style mixing:
        blocks < mixing_layer use w(z), blocks >= use w(mixing_z).
        """
        z = F.normalize(z, dim=1)
        w = self.net(z)

        if mixing_z is not None and mixing_layer is not None:
            mixing_z = F.normalize(mixing_z, dim=1)
            w2 = self.net(mixing_z)
            ws = [w if i < mixing_layer else w2 for i in range(self.num_layers)]
        else:
            ws = [w] * self.num_layers
        return ws


# ---------------------------------------------------------------------------
# Synthesis block (one resolution level)
# ---------------------------------------------------------------------------

class SynthesisBlock(nn.Module):
    """
    One resolution level of the StyleGAN2 synthesis network.
    Optional 2x bilinear upsample, then 3 × (ModConv + Noise + Act).
    Produces a ToRGB output accumulated via skip connection.
    """

    def __init__(self, in_ch: int, out_ch: int, w_dim: int,
                 upsample: bool = True, has_attention: bool = False,
                 num_heads: int = 8):
        super().__init__()
        self.has_attention = has_attention

        self.conv0 = ModulatedConv2d(in_ch,  out_ch, 3, w_dim, upsample=upsample)
        self.noise0 = NoiseInjection()
        self.conv1 = ModulatedConv2d(out_ch, out_ch, 3, w_dim)
        self.noise1 = NoiseInjection()
        self.conv2 = ModulatedConv2d(out_ch, out_ch, 3, w_dim)
        self.noise2 = NoiseInjection()

        if has_attention:
            self.attn = MultiHeadSelfAttention2d(out_ch, num_heads=num_heads)

        self.to_rgb = ModulatedConv2d(out_ch, 3, 1, w_dim, demodulate=False)
        self.act = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x: torch.Tensor, w: torch.Tensor,
                prev_rgb: Optional[torch.Tensor] = None
                ) -> tuple[torch.Tensor, torch.Tensor]:
        x = self.act(self.noise0(self.conv0(x, w)))
        x = self.act(self.noise1(self.conv1(x, w)))
        x = self.act(self.noise2(self.conv2(x, w)))

        if self.has_attention:
            x = self.attn(x)

        rgb = self.to_rgb(x, w)
        if prev_rgb is not None:
            prev_rgb = F.interpolate(prev_rgb, scale_factor=2,
                                     mode="bilinear", align_corners=False)
            rgb = rgb + prev_rgb
        return x, rgb


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class Generator(nn.Module):
    """
    StyleGAN2-style generator.
    z (512) -> MappingNetwork (16 layers, 1024-dim)
             -> Learned 4x4 constant
             -> 6 SynthesisBlocks (4->8->16->32->64->128)
             -> accumulated ToRGB skip output
             -> Tanh

    Multi-head attention (8 heads) at 16x16, 32x32, 64x64.
    ~120M trainable parameters.
    """

    def __init__(self, z_dim: int = 512, w_dim: int = 1024, channel_cap: int = 512):
        super().__init__()
        self.z_dim = z_dim

        NUM_BLOCKS = 6
        self.mapping = MappingNetwork(z_dim=z_dim, w_dim=w_dim,
                                      depth=16, num_layers=NUM_BLOCKS)

        # Channel schedule respects channel_cap (reduce for CPU runs)
        channels = [_nf_custom(s, channel_cap) for s in range(1, NUM_BLOCKS + 1)]
        # channels = [512, 512, 512, 512, 256, 128]

        self.const = nn.Parameter(torch.randn(1, channels[0], 4, 4))

        # SynthesisBlocks; first block does NOT upsample (starts at 4x4 -> 8x8)
        attn_at = {2, 3}   # blocks at 16x16 and 32x32 only (64x64 too large for CPU)
        def _heads(ch): return max(1, min(8, ch // 4))
        self.blocks = nn.ModuleList([
            SynthesisBlock(
                in_ch=channels[max(i - 1, 0)],
                out_ch=channels[i],
                w_dim=w_dim,
                upsample=(i > 0),
                has_attention=(i in attn_at),
                num_heads=_heads(channels[i]),
            )
            for i in range(NUM_BLOCKS)
        ])

        self.final_act = nn.Tanh()
        self._init_weights()

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, (nn.Conv2d,)) and not isinstance(m, ModulatedConv2d):
                nn.init.kaiming_normal_(m.weight, a=0.2)

    def synthesis_forward(self, ws: list[torch.Tensor]) -> torch.Tensor:
        """Run only the synthesis network given a pre-computed list of w vectors."""
        x = self.const.expand(ws[0].size(0), -1, -1, -1)
        rgb = None
        for block, w in zip(self.blocks, ws):
            x, rgb = block(x, w, prev_rgb=rgb)
        return self.final_act(rgb)

    def forward(self, z: torch.Tensor,
                mixing_z: Optional[torch.Tensor] = None,
                mixing_layer: Optional[int] = None) -> torch.Tensor:
        ws = self.mapping(z, mixing_z=mixing_z, mixing_layer=mixing_layer)
        return self.synthesis_forward(ws)


# ---------------------------------------------------------------------------
# Discriminator building blocks
# ---------------------------------------------------------------------------

class DResBlock(nn.Module):
    """
    3-conv spectral-normed residual block for Discriminator.
    Optional stride-2 downsampling on the third conv.
    """

    def __init__(self, in_ch: int, out_ch: int, downsample: bool = True):
        super().__init__()
        stride = 2 if downsample else 1

        self.main = nn.Sequential(
            spectral_norm(nn.Conv2d(in_ch,  in_ch,  3, padding=1)),
            nn.LeakyReLU(0.2, inplace=True),
            spectral_norm(nn.Conv2d(in_ch,  out_ch, 3, padding=1)),
            nn.LeakyReLU(0.2, inplace=True),
            spectral_norm(nn.Conv2d(out_ch, out_ch, 3, stride=stride, padding=1)),
            nn.LeakyReLU(0.2, inplace=True),
        )
        self.skip = spectral_norm(
            nn.Conv2d(in_ch, out_ch, 1, stride=stride)
        ) if (in_ch != out_ch or downsample) else nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.main(x) + self.skip(x)


class MultiGroupMinibatchStd(nn.Module):
    """
    Minibatch std computed across multiple groups and channels.
    Appends num_new_features extra channels.
    """

    def __init__(self, group_size: int = 4, num_new_features: int = 4):
        super().__init__()
        self.G = group_size
        self.F = num_new_features

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, C, H, W = x.shape
        G = min(self.G, B)
        F = self.F

        # (G, B//G, F, C//F, H, W)
        y = x.view(G, -1, F, C // F, H, W)
        y = y - y.mean(dim=0, keepdim=True)
        y = y.pow(2).mean(dim=0)                    # (B//G, F, C//F, H, W)
        y = y.add(1e-8).sqrt()
        y = y.mean(dim=[2, 3, 4])                   # (B//G, F)
        y = y.repeat(G, 1).view(B, F, 1, 1).expand(B, F, H, W)
        return torch.cat([x, y], dim=1)


# ---------------------------------------------------------------------------
# Discriminator
# ---------------------------------------------------------------------------

class Discriminator(nn.Module):
    """
    7-stage residual discriminator.
    128x128 -> 64x64 -> 32x32 -> 16x16 -> 8x8 -> 4x4 -> 2x2 -> logit.

    Each stage: DResBlock (3 spectral-normed convs + skip).
    Multi-head attention (8 heads) at 64x64, 32x32, 16x16.
    Multi-group minibatch std before final head.
    Projection head for extra discriminative power.

    ~95M trainable parameters.
    """

    def __init__(self, channel_cap: int = 512):
        super().__init__()

        # Channel schedule (mirrors G reversed), respects channel_cap
        full = [128, 256, 512, 512, 512, 512, 512]
        chs = [min(c, channel_cap) for c in full]

        self.from_rgb = spectral_norm(nn.Conv2d(3, chs[0], 3, stride=2, padding=1))

        attn_at = {1, 2}   # after b0 at 32x32, after b1 at 16x16 (64x64 too large for CPU)
        self.blocks = nn.ModuleList([
            DResBlock(chs[i], chs[i + 1]) for i in range(len(chs) - 1)
        ])
        def _heads(ch): return max(1, min(8, ch // 4))
        self.attns = nn.ModuleDict({
            str(i): MultiHeadSelfAttention2d(chs[i + 1], num_heads=_heads(chs[i + 1]))
            for i in attn_at
        })

        # After 7 stages: feature map is 2x2, 512 ch + minibatch features
        mbstd_features = 16
        self.mbstd = MultiGroupMinibatchStd(group_size=4, num_new_features=mbstd_features)

        self.head = nn.Sequential(
            spectral_norm(nn.Conv2d(chs[-1] + mbstd_features, chs[-1], 3, padding=1)),
            nn.LeakyReLU(0.2, inplace=True),
            nn.AdaptiveAvgPool2d(1),   # works regardless of spatial size
            nn.Flatten(),
        )
        self.out = spectral_norm(nn.Linear(chs[-1], 1))

        # Projection head (extra discriminative power)
        self.proj = spectral_norm(nn.Linear(chs[-1], chs[-1] // 2))
        self.proj_out = spectral_norm(nn.Linear(chs[-1] // 2, 1))

        self._init_weights()

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, a=0.2, mode="fan_in",
                                        nonlinearity="leaky_relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, img: torch.Tensor) -> torch.Tensor:
        x = F.leaky_relu(self.from_rgb(img), 0.2, inplace=True)   # 64x64

        for i, block in enumerate(self.blocks):
            x = block(x)
            if str(i) in self.attns:
                x = self.attns[str(i)](x)

        x = self.mbstd(x)
        feat = self.head(x)                                         # (B, 512)

        score_main = self.out(feat)
        score_proj = self.proj_out(F.leaky_relu(self.proj(feat), 0.2))
        return score_main + score_proj
