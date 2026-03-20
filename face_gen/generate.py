"""
Generate face images from a trained checkpoint.

Usage:
    # Generate 16 random faces
    python generate.py --checkpoint checkpoints/ckpt_epoch_0099.pt --count 16

    # Generate from a specific seed for reproducibility
    python generate.py --checkpoint checkpoints/ckpt_epoch_0099.pt --seed 42 --count 4

    # Supply your own noise tensor (numpy .npy file, shape [N, 128])
    python generate.py --checkpoint checkpoints/ckpt_epoch_0099.pt --noise_file my_noise.npy
"""

import argparse

import numpy as np
import torch
from torchvision import utils

from model import Generator


def load_generator(checkpoint_path: str, latent_dim: int, device: torch.device) -> Generator:
    ckpt = torch.load(checkpoint_path, map_location=device)
    G = Generator(latent_dim=latent_dim).to(device)
    # Prefer EMA weights when available (better quality)
    key = "G_ema" if "G_ema" in ckpt else "G"
    G.load_state_dict(ckpt[key])
    print(f"Loaded weights from checkpoint key '{key}'")
    G.eval()
    return G


def generate(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")

    G = load_generator(args.checkpoint, args.latent_dim, device)

    # Build noise input
    if args.noise_file:
        arr = np.load(args.noise_file)
        noise = torch.tensor(arr, dtype=torch.float32, device=device)
        print(f"Loaded noise from {args.noise_file}, shape: {noise.shape}")
    else:
        if args.seed is not None:
            torch.manual_seed(args.seed)
        noise = torch.randn(args.count, args.latent_dim, device=device)
        print(f"Generated random noise, shape: {noise.shape}")

    with torch.no_grad():
        images = G(noise)  # (N, 3, 128, 128) in [-1, 1]

    out_path = args.output
    utils.save_image(images, out_path, normalize=True, value_range=(-1, 1),
                     nrow=max(1, int(images.size(0) ** 0.5)))
    print(f"Saved {images.size(0)} face(s) → {out_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate faces from trained GAN")
    parser.add_argument("--checkpoint", type=str, required=True,
                        help="Path to .pt checkpoint file")
    parser.add_argument("--latent_dim", type=int, default=256)
    parser.add_argument("--count", type=int, default=16,
                        help="Number of faces to generate (ignored if --noise_file given)")
    parser.add_argument("--seed", type=int, default=None,
                        help="Random seed for reproducibility")
    parser.add_argument("--noise_file", type=str, default=None,
                        help="Optional .npy file with custom noise vectors (shape [N, latent_dim])")
    parser.add_argument("--output", type=str, default="generated_faces.png")
    return parser.parse_args()


if __name__ == "__main__":
    generate(parse_args())
