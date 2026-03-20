"""
Generate face images from a trained Ultra checkpoint.

Usage:
    # 16 random faces
    python generate.py --checkpoint checkpoints/ckpt_epoch_0499.pt

    # Reproducible
    python generate.py --checkpoint checkpoints/ckpt_epoch_0499.pt --seed 42 --count 4

    # Style mixing: blend two latent codes at layer 3
    python generate.py --checkpoint checkpoints/ckpt_epoch_0499.pt --mixing --mix_layer 3

    # Custom noise (.npy, shape [N, z_dim])
    python generate.py --checkpoint checkpoints/ckpt_epoch_0499.pt --noise_file my_noise.npy

    # Latent interpolation between two random faces (10 steps)
    python generate.py --checkpoint checkpoints/ckpt_epoch_0499.pt --interpolate --steps 10
"""

import argparse

import numpy as np
import torch
from torchvision import utils

from model import Generator


def load_generator(checkpoint_path: str, z_dim: int, w_dim: int,
                   device: torch.device) -> Generator:
    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    G = Generator(z_dim=z_dim, w_dim=w_dim).to(device)
    key = "G_ema" if "G_ema" in ckpt else "G"
    G.load_state_dict(ckpt[key])
    print(f"Loaded weights from '{key}' (checkpoint epoch {ckpt.get('epoch', '?')})")
    G.eval()
    return G


def generate(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    G = load_generator(args.checkpoint, args.z_dim, args.w_dim, device)

    if args.seed is not None:
        torch.manual_seed(args.seed)

    # ---- Build noise input ----
    if args.noise_file:
        arr = np.load(args.noise_file)
        z = torch.tensor(arr, dtype=torch.float32, device=device)
        print(f"Loaded z from {args.noise_file}, shape {z.shape}")
    else:
        z = torch.randn(args.count, args.z_dim, device=device)

    # ---- Latent interpolation mode ----
    if args.interpolate:
        z_a = torch.randn(1, args.z_dim, device=device)
        z_b = torch.randn(1, args.z_dim, device=device)
        ts  = torch.linspace(0, 1, args.steps, device=device)
        z   = torch.stack([z_a + t * (z_b - z_a) for t in ts]).squeeze(1)
        print(f"Interpolating {args.steps} steps between two latent codes")

    # ---- Style mixing ----
    mix_z, mix_layer = None, None
    if args.mixing:
        mix_z = torch.randn_like(z)
        mix_layer = args.mix_layer
        print(f"Style mixing at layer {mix_layer}")

    with torch.no_grad():
        images = G(z, mixing_z=mix_z, mixing_layer=mix_layer)

    out = args.output
    utils.save_image(images, out, normalize=True, value_range=(-1, 1),
                     nrow=max(1, int(images.size(0) ** 0.5)))
    print(f"Saved {images.size(0)} face(s) -> {out}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--checkpoint",  type=str, required=True)
    p.add_argument("--z_dim",       type=int, default=512)
    p.add_argument("--w_dim",       type=int, default=1024)
    p.add_argument("--count",       type=int, default=16)
    p.add_argument("--seed",        type=int, default=None)
    p.add_argument("--noise_file",  type=str, default=None)
    p.add_argument("--output",      type=str, default="generated_faces.png")
    p.add_argument("--interpolate", action="store_true",
                   help="Generate a latent interpolation strip")
    p.add_argument("--steps",       type=int, default=10,
                   help="Number of interpolation steps")
    p.add_argument("--mixing",      action="store_true",
                   help="Apply style mixing between two random latent codes")
    p.add_argument("--mix_layer",   type=int, default=3,
                   help="Synthesis block index where style crossover happens")
    return p.parse_args()


if __name__ == "__main__":
    generate(parse_args())
