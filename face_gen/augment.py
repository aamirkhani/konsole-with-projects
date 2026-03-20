"""
Adaptive Discriminator Augmentation (ADA)
==========================================
Karras et al. "Training Generative Adversarial Networks with Limited Data" (2020).

Applies a configurable suite of *differentiable* augmentations to both real
and fake images before they enter the Discriminator.  Augmentation strength p
is adapted automatically so that the Discriminator does not overfit on the
real training set.

Augmentation operations (all differentiable):
  1. Horizontal flip
  2. Integer translation (grid_sample)
  3. Rotation ±15°  (grid_sample)
  4. Isotropic scaling 0.8–1.25  (grid_sample)
  5. Brightness / contrast / saturation jitter
  6. Hue rotation
  7. Additive Gaussian noise
  8. Cutout (rectangular erase, set to 0)

Adaptive update rule:
  r_t = sign(D(real)).mean()   # should be close to 0 in a balanced GAN
  if r_t > target: increase p   # D too confident on reals → more augmentation
  if r_t < target: decrease p
"""

import math
import torch
import torch.nn as nn
import torch.nn.functional as F


# ---------------------------------------------------------------------------
# Geometric helpers
# ---------------------------------------------------------------------------

def _make_grid(B: int, H: int, W: int, device: torch.device) -> torch.Tensor:
    """Return normalised meshgrid of shape (B, H, W, 2) in [-1, 1]."""
    gy, gx = torch.meshgrid(
        torch.linspace(-1, 1, H, device=device),
        torch.linspace(-1, 1, W, device=device),
        indexing="ij",
    )
    grid = torch.stack([gx, gy], dim=-1).unsqueeze(0).expand(B, -1, -1, -1)
    return grid.clone()


def _apply_grid(x: torch.Tensor, theta: torch.Tensor) -> torch.Tensor:
    """
    Apply an affine transformation theta (B, 2, 3) to image x via grid_sample.
    Pixels that land outside [-1,1] are zero-padded.
    """
    grid = F.affine_grid(theta, x.shape, align_corners=False)
    return F.grid_sample(x, grid, mode="bilinear",
                         padding_mode="zeros", align_corners=False)


def _identity(B: int, device: torch.device) -> torch.Tensor:
    """Return (B, 2, 3) identity affine matrices."""
    return torch.eye(2, 3, device=device).unsqueeze(0).expand(B, -1, -1).clone()


# ---------------------------------------------------------------------------
# AugmentPipe
# ---------------------------------------------------------------------------

class AugmentPipe(nn.Module):
    """
    Differentiable augmentation pipeline with adaptive probability p.

    Usage:
        aug = AugmentPipe(p=0.0)

        # Inside training loop, pass images through before D:
        real_aug  = aug(real_imgs)
        fake_aug  = aug(fake_imgs)

        # After each D step, update p:
        aug.update(r_t=sign(D_real).mean().item())
    """

    def __init__(self, p: float = 0.0, target_rt: float = 0.6,
                 p_step: float = 5e-3):
        super().__init__()
        self.p = p
        self.target_rt = target_rt
        self.p_step = p_step

    # ------------------------------------------------------------------
    # Individual augmentations
    # ------------------------------------------------------------------

    @staticmethod
    def _hflip(x: torch.Tensor, p: float) -> torch.Tensor:
        mask = (torch.rand(x.size(0), 1, 1, 1, device=x.device) < p).float()
        return x * (1 - mask) + x.flip(-1) * mask

    @staticmethod
    def _translate(x: torch.Tensor, p: float, max_frac: float = 0.125) -> torch.Tensor:
        B, _, H, W = x.shape
        theta = _identity(B, x.device)
        active = torch.rand(B, device=x.device) < p
        tx = (torch.rand(B, device=x.device) * 2 - 1) * max_frac
        ty = (torch.rand(B, device=x.device) * 2 - 1) * max_frac
        theta[active, 0, 2] = tx[active]
        theta[active, 1, 2] = ty[active]
        return _apply_grid(x, theta)

    @staticmethod
    def _rotate(x: torch.Tensor, p: float, max_deg: float = 15.0) -> torch.Tensor:
        B = x.size(0)
        theta = _identity(B, x.device)
        active = torch.rand(B, device=x.device) < p
        angle = (torch.rand(B, device=x.device) * 2 - 1) * math.radians(max_deg)
        cos_a, sin_a = torch.cos(angle), torch.sin(angle)
        theta[active, 0, 0] =  cos_a[active]
        theta[active, 0, 1] = -sin_a[active]
        theta[active, 1, 0] =  sin_a[active]
        theta[active, 1, 1] =  cos_a[active]
        return _apply_grid(x, theta)

    @staticmethod
    def _scale(x: torch.Tensor, p: float,
               lo: float = 0.8, hi: float = 1.25) -> torch.Tensor:
        B = x.size(0)
        theta = _identity(B, x.device)
        active = torch.rand(B, device=x.device) < p
        s = lo + torch.rand(B, device=x.device) * (hi - lo)
        theta[active, 0, 0] = 1.0 / s[active]
        theta[active, 1, 1] = 1.0 / s[active]
        return _apply_grid(x, theta)

    @staticmethod
    def _brightness(x: torch.Tensor, p: float, strength: float = 0.2) -> torch.Tensor:
        B = x.size(0)
        active = torch.rand(B, device=x.device) < p
        delta = (torch.rand(B, device=x.device) * 2 - 1) * strength
        delta = delta.view(B, 1, 1, 1) * active.float().view(B, 1, 1, 1)
        return (x + delta).clamp(-1, 1)

    @staticmethod
    def _contrast(x: torch.Tensor, p: float,
                  lo: float = 0.75, hi: float = 1.25) -> torch.Tensor:
        B = x.size(0)
        active = torch.rand(B, device=x.device) < p
        scale = lo + torch.rand(B, device=x.device) * (hi - lo)
        scale = (scale * active.float() + 1.0 * (~active).float()).view(B, 1, 1, 1)
        mu = x.mean(dim=[2, 3], keepdim=True)
        return ((x - mu) * scale + mu).clamp(-1, 1)

    @staticmethod
    def _saturation(x: torch.Tensor, p: float,
                    lo: float = 0.5, hi: float = 1.5) -> torch.Tensor:
        B = x.size(0)
        active = torch.rand(B, device=x.device) < p
        scale = lo + torch.rand(B, device=x.device) * (hi - lo)
        scale = (scale * active.float() + 1.0 * (~active).float()).view(B, 1, 1, 1)
        gray = x.mean(dim=1, keepdim=True)
        return (gray + (x - gray) * scale).clamp(-1, 1)

    @staticmethod
    def _hue(x: torch.Tensor, p: float, max_shift: float = 0.1) -> torch.Tensor:
        """Rotate hue in RGB space via a simple channel shuffle interpolation."""
        B = x.size(0)
        active = torch.rand(B, device=x.device) < p
        shift = (torch.rand(B, device=x.device) * 2 - 1) * max_shift
        shift = (shift * active.float()).view(B, 1, 1, 1)
        # Approximate hue rotation: lerp with cyclic channel shift
        x_roll = torch.roll(x, 1, dims=1)
        return (x + (x_roll - x) * shift.abs()).clamp(-1, 1)

    @staticmethod
    def _gaussian_noise(x: torch.Tensor, p: float,
                        max_std: float = 0.05) -> torch.Tensor:
        B = x.size(0)
        active = torch.rand(B, device=x.device) < p
        std = torch.rand(B, device=x.device) * max_std
        noise = torch.randn_like(x) * (std * active.float()).view(B, 1, 1, 1)
        return (x + noise).clamp(-1, 1)

    @staticmethod
    def _cutout(x: torch.Tensor, p: float, max_frac: float = 0.25) -> torch.Tensor:
        B, C, H, W = x.shape
        active = torch.rand(B, device=x.device) < p
        out = x.clone()
        for b in range(B):
            if not active[b]:
                continue
            ch = int(torch.rand(1).item() * max_frac * H) + 1
            cw = int(torch.rand(1).item() * max_frac * W) + 1
            y0 = int(torch.rand(1).item() * (H - ch))
            x0 = int(torch.rand(1).item() * (W - cw))
            out[b, :, y0:y0 + ch, x0:x0 + cw] = 0.0
        return out

    # ------------------------------------------------------------------
    # Forward
    # ------------------------------------------------------------------

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        if self.p <= 0:
            return x
        p = self.p
        x = self._hflip(x, p)
        x = self._translate(x, p)
        x = self._rotate(x, p)
        x = self._scale(x, p)
        x = self._brightness(x, p)
        x = self._contrast(x, p)
        x = self._saturation(x, p)
        x = self._hue(x, p)
        x = self._gaussian_noise(x, p)
        x = self._cutout(x, p)
        return x

    # ------------------------------------------------------------------
    # Adaptive p update
    # ------------------------------------------------------------------

    def update(self, r_t: float) -> None:
        """
        r_t = sign(D(real)).mean()  — target is self.target_rt (default 0.6).
        Increase p if D is too confident; decrease otherwise.
        """
        if r_t > self.target_rt:
            self.p = min(1.0, self.p + self.p_step)
        else:
            self.p = max(0.0, self.p - self.p_step)
