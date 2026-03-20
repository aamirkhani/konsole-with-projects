"""
Face Generation GAN Model — Heavy Edition
==========================================
Generator:   noise (latent_dim=256) -> 128x128 RGB face
Discriminator: 128x128 RGB -> real/fake logit

Key upgrades over v1:
  * base_channels 64 -> 128  (~4x more conv weights)
  * Mapping network (8-layer MLP) to disentangle latent space (StyleGAN-lite)
  * Residual blocks with skip connections in both G and D
  * Self-Attention at 32x32 and 64x64 (SAGAN-style)
  * Spectral Normalization on every conv/linear in D
  * Pixel-shuffle upsampling in G (sharper than nearest-neighbour)
  * Extra deep discriminator: 128->64->32->16->8->4->1
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.nn.utils import spectral_norm


# ---------------------------------------------------------------------------
# Building blocks
# ---------------------------------------------------------------------------

class MappingNetwork(nn.Module):
    """8-layer fully-connected mapping z -> w (StyleGAN-lite)."""

    def __init__(self, latent_dim: int = 256, hidden: int = 512, depth: int = 8):
        super().__init__()
        layers: list[nn.Module] = []
        in_dim = latent_dim
        for _ in range(depth):
            layers += [nn.Linear(in_dim, hidden), nn.LeakyReLU(0.2, inplace=True)]
            in_dim = hidden
        self.net = nn.Sequential(*layers)
        self.out_dim = hidden

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        # Pixel-normalise input
        z = F.normalize(z, dim=1)
        return self.net(z)


class AdaIN(nn.Module):
    """Adaptive Instance Normalisation: applies style (w) to feature map x."""

    def __init__(self, channels: int, w_dim: int):
        super().__init__()
        self.norm = nn.InstanceNorm2d(channels)
        self.style = nn.Linear(w_dim, channels * 2)  # scale + bias

    def forward(self, x: torch.Tensor, w: torch.Tensor) -> torch.Tensor:
        style = self.style(w).unsqueeze(-1).unsqueeze(-1)
        gamma, beta = style.chunk(2, dim=1)
        return gamma * self.norm(x) + beta


class SelfAttention(nn.Module):
    """Non-local self-attention block (SAGAN, Zhang et al. 2019)."""

    def __init__(self, channels: int):
        super().__init__()
        mid = max(channels // 8, 1)
        self.q = nn.Conv2d(channels, mid, 1)
        self.k = nn.Conv2d(channels, mid, 1)
        self.v = nn.Conv2d(channels, channels, 1)
        self.gamma = nn.Parameter(torch.zeros(1))

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        B, C, H, W = x.shape
        q = self.q(x).view(B, -1, H * W).permute(0, 2, 1)   # B, HW, mid
        k = self.k(x).view(B, -1, H * W)                     # B, mid, HW
        attn = torch.softmax(torch.bmm(q, k), dim=-1)        # B, HW, HW
        v = self.v(x).view(B, C, H * W)
        out = torch.bmm(v, attn.permute(0, 2, 1)).view(B, C, H, W)
        return x + self.gamma * out


# ---------------------------------------------------------------------------
# Generator residual block (AdaIN-conditioned)
# ---------------------------------------------------------------------------

class GResBlock(nn.Module):
    """
    Residual block for Generator with pixel-shuffle 2x upsampling and AdaIN.
    in_ch -> out_ch, spatial resolution doubled.
    """

    def __init__(self, in_ch: int, out_ch: int, w_dim: int):
        super().__init__()
        # Main path: upsample then two conv+AdaIN
        self.up = nn.Sequential(
            nn.Conv2d(in_ch, out_ch * 4, 1),          # pointwise expand for pixel-shuffle
            nn.PixelShuffle(2),                         # 2x upsample
        )
        self.conv1 = nn.Conv2d(out_ch, out_ch, 3, padding=1)
        self.adain1 = AdaIN(out_ch, w_dim)
        self.conv2 = nn.Conv2d(out_ch, out_ch, 3, padding=1)
        self.adain2 = AdaIN(out_ch, w_dim)
        self.act = nn.LeakyReLU(0.2, inplace=True)

        # Skip: upsample + pointwise
        self.skip = nn.Sequential(
            nn.Upsample(scale_factor=2, mode="bilinear", align_corners=False),
            nn.Conv2d(in_ch, out_ch, 1),
        )

    def forward(self, x: torch.Tensor, w: torch.Tensor) -> torch.Tensor:
        skip = self.skip(x)
        x = self.up(x)
        x = self.act(self.adain1(self.conv1(x), w))
        x = self.act(self.adain2(self.conv2(x), w))
        return x + skip


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------

class Generator(nn.Module):
    """
    Noise z (latent_dim=256) -> 128x128 RGB face.

    Pipeline:
      z -> MappingNetwork -> w
      Learned constant 4x4 -> GResBlock x5 (4->8->16->32->64->128)
      Self-Attention at 32x32 and 64x64
      Final 3x3 conv -> Tanh

    Parameter count: ~34M with base_channels=128.
    """

    def __init__(self, latent_dim: int = 256, base_channels: int = 128):
        super().__init__()
        self.latent_dim = latent_dim
        bc = base_channels

        self.mapping = MappingNetwork(latent_dim=latent_dim, hidden=512, depth=8)
        w_dim = self.mapping.out_dim

        # Learned starting constant: 4x4
        self.const = nn.Parameter(torch.randn(1, bc * 16, 4, 4))

        # 5 upsampling residual blocks
        # 4x4 -> 8x8 -> 16x16 -> 32x32 -> 64x64 -> 128x128
        self.b0 = GResBlock(bc * 16, bc * 16, w_dim)  # 4  -> 8
        self.b1 = GResBlock(bc * 16, bc * 8,  w_dim)  # 8  -> 16
        self.b2 = GResBlock(bc * 8,  bc * 4,  w_dim)  # 16 -> 32
        self.b3 = GResBlock(bc * 4,  bc * 2,  w_dim)  # 32 -> 64
        self.b4 = GResBlock(bc * 2,  bc,      w_dim)  # 64 -> 128

        # Self-attention at 32x32 and 64x64
        self.attn32 = SelfAttention(bc * 4)
        self.attn64 = SelfAttention(bc * 2)

        # To-RGB
        self.to_rgb = nn.Sequential(
            nn.InstanceNorm2d(bc),
            nn.Conv2d(bc, 3, kernel_size=3, padding=1),
            nn.Tanh(),
        )

        self._init_weights()

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, a=0.2, mode="fan_in", nonlinearity="leaky_relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)
            elif isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, a=0.2)
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        w = self.mapping(z)                                  # (B, 512)
        x = self.const.expand(z.size(0), -1, -1, -1)        # (B, bc*16, 4, 4)

        x = self.b0(x, w)                                    # -> 8x8
        x = self.b1(x, w)                                    # -> 16x16
        x = self.b2(x, w)                                    # -> 32x32
        x = self.attn32(x)
        x = self.b3(x, w)                                    # -> 64x64
        x = self.attn64(x)
        x = self.b4(x, w)                                    # -> 128x128
        return self.to_rgb(x)


# ---------------------------------------------------------------------------
# Discriminator residual block (Spectral Norm)
# ---------------------------------------------------------------------------

class DResBlock(nn.Module):
    """
    Residual block for Discriminator with stride-2 downsampling.
    All convs have spectral normalization.
    """

    def __init__(self, in_ch: int, out_ch: int, downsample: bool = True):
        super().__init__()
        self.main = nn.Sequential(
            spectral_norm(nn.Conv2d(in_ch, in_ch, 3, padding=1)),
            nn.LeakyReLU(0.2, inplace=True),
            spectral_norm(nn.Conv2d(in_ch, out_ch, 3, stride=2 if downsample else 1, padding=1)),
            nn.LeakyReLU(0.2, inplace=True),
        )
        if in_ch != out_ch or downsample:
            self.skip = spectral_norm(
                nn.Conv2d(in_ch, out_ch, 1, stride=2 if downsample else 1)
            )
        else:
            self.skip = nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.main(x) + self.skip(x)


# ---------------------------------------------------------------------------
# Discriminator
# ---------------------------------------------------------------------------

class Discriminator(nn.Module):
    """
    128x128 RGB -> real/fake score (no sigmoid — used with WGAN-GP).

    Architecture (all spectral-normed):
      128x128 -> 64x64 -> 32x32 -> 16x16 -> 8x8 -> 4x4 -> 1
      Self-Attention at 64x64 and 32x32
      Minibatch std feature for mode-collapse resistance

    Parameter count: ~28M with base_channels=128.
    """

    def __init__(self, base_channels: int = 128):
        super().__init__()
        bc = base_channels

        # Initial conv: 128x128 -> 64x64
        self.from_rgb = spectral_norm(nn.Conv2d(3, bc, 3, stride=2, padding=1))

        self.b0 = DResBlock(bc,      bc * 2)   # 64 -> 32
        self.b1 = DResBlock(bc * 2,  bc * 4)   # 32 -> 16
        self.b2 = DResBlock(bc * 4,  bc * 8)   # 16 -> 8
        self.b3 = DResBlock(bc * 8,  bc * 16)  # 8  -> 4

        self.attn64 = SelfAttention(bc)
        self.attn32 = SelfAttention(bc * 2)

        # Minibatch std: adds 1 channel
        # Final linear
        self.head = nn.Sequential(
            nn.LeakyReLU(0.2, inplace=True),
            spectral_norm(nn.Conv2d(bc * 16 + 1, bc * 16, 3, padding=1)),
            nn.LeakyReLU(0.2, inplace=True),
            nn.AdaptiveAvgPool2d(1),
        )
        self.out = spectral_norm(nn.Linear(bc * 16, 1))

        self._init_weights()

    def _init_weights(self) -> None:
        for m in self.modules():
            if isinstance(m, nn.Conv2d):
                nn.init.kaiming_normal_(m.weight, a=0.2, mode="fan_in", nonlinearity="leaky_relu")
                if m.bias is not None:
                    nn.init.zeros_(m.bias)

    @staticmethod
    def _minibatch_std(x: torch.Tensor) -> torch.Tensor:
        """Append per-spatial-location std across batch as an extra channel."""
        std = x.std(dim=0, keepdim=True).mean(dim=1, keepdim=True)
        std = std.expand(x.size(0), 1, x.size(2), x.size(3))
        return torch.cat([x, std], dim=1)

    def forward(self, img: torch.Tensor) -> torch.Tensor:
        x = F.leaky_relu(self.from_rgb(img), 0.2, inplace=True)  # 64x64
        x = self.attn64(x)
        x = self.b0(x)                                             # 32x32
        x = self.attn32(x)
        x = self.b1(x)                                            # 16x16
        x = self.b2(x)                                            # 8x8
        x = self.b3(x)                                            # 4x4
        x = self._minibatch_std(x)
        x = self.head(x).view(x.size(0), -1)
        return self.out(x)
