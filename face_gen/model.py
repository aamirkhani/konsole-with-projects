"""
Face Generation GAN Model
Generates unique 128x128 face images from noise input.
"""

import torch
import torch.nn as nn


class Generator(nn.Module):
    """
    Takes a latent noise vector and generates a 128x128 RGB face image.
    Input:  (batch, latent_dim)
    Output: (batch, 3, 128, 128) in range [-1, 1]
    """

    def __init__(self, latent_dim: int = 128, base_channels: int = 64):
        super().__init__()
        self.latent_dim = latent_dim

        # Project and reshape: latent_dim -> 8x8 feature map
        self.project = nn.Sequential(
            nn.Linear(latent_dim, base_channels * 8 * 8 * 8),
            nn.LeakyReLU(0.2, inplace=True),
        )

        # Upsample: 8 -> 16 -> 32 -> 64 -> 128
        self.conv_blocks = nn.Sequential(
            # 8x8 -> 16x16
            self._block(base_channels * 8, base_channels * 8),
            # 16x16 -> 32x32
            self._block(base_channels * 8, base_channels * 4),
            # 32x32 -> 64x64
            self._block(base_channels * 4, base_channels * 2),
            # 64x64 -> 128x128
            self._block(base_channels * 2, base_channels),
            # Final conv to RGB
            nn.Conv2d(base_channels, 3, kernel_size=3, padding=1),
            nn.Tanh(),
        )

        self.base_channels = base_channels

    @staticmethod
    def _block(in_ch: int, out_ch: int) -> nn.Sequential:
        return nn.Sequential(
            nn.Upsample(scale_factor=2, mode="nearest"),
            nn.Conv2d(in_ch, out_ch, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(out_ch, out_ch, kernel_size=3, padding=1),
            nn.BatchNorm2d(out_ch),
            nn.LeakyReLU(0.2, inplace=True),
        )

    def forward(self, z: torch.Tensor) -> torch.Tensor:
        x = self.project(z)
        x = x.view(x.size(0), self.base_channels * 8, 8, 8)
        return self.conv_blocks(x)


class Discriminator(nn.Module):
    """
    Classifies whether a 128x128 RGB image is real or generated.
    Input:  (batch, 3, 128, 128)
    Output: (batch, 1) — raw logit
    """

    def __init__(self, base_channels: int = 64):
        super().__init__()

        self.net = nn.Sequential(
            # 128x128 -> 64x64
            self._block(3, base_channels, normalize=False),
            # 64x64 -> 32x32
            self._block(base_channels, base_channels * 2),
            # 32x32 -> 16x16
            self._block(base_channels * 2, base_channels * 4),
            # 16x16 -> 8x8
            self._block(base_channels * 4, base_channels * 8),
            # 8x8 -> 1x1
            nn.Conv2d(base_channels * 8, 1, kernel_size=8),
        )

    @staticmethod
    def _block(in_ch: int, out_ch: int, normalize: bool = True) -> nn.Sequential:
        layers: list[nn.Module] = [
            nn.Conv2d(in_ch, out_ch, kernel_size=4, stride=2, padding=1),
        ]
        if normalize:
            layers.append(nn.InstanceNorm2d(out_ch, affine=True))
        layers.append(nn.LeakyReLU(0.2, inplace=True))
        return nn.Sequential(*layers)

    def forward(self, img: torch.Tensor) -> torch.Tensor:
        return self.net(img).view(img.size(0), -1)
