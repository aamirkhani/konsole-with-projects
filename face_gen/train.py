"""
Training loop for the Face Generation GAN.

Usage:
    python train.py --data_dir ./data/faces --epochs 100 --save_dir ./checkpoints
"""

import argparse
import os
from pathlib import Path

import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader
from torchvision import datasets, transforms, utils

from model import Discriminator, Generator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_dataloader(data_dir: str, image_size: int, batch_size: int) -> DataLoader:
    transform = transforms.Compose([
        transforms.Resize(image_size),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),  # -> [-1, 1]
    ])
    dataset = datasets.ImageFolder(root=data_dir, transform=transform)
    return DataLoader(dataset, batch_size=batch_size, shuffle=True,
                      num_workers=4, pin_memory=True, drop_last=True)


def weights_init(m: nn.Module) -> None:
    """Apply sensible weight initialisation (from DCGAN paper)."""
    classname = type(m).__name__
    if "Conv" in classname:
        nn.init.normal_(m.weight.data, 0.0, 0.02)
    elif "BatchNorm" in classname:
        nn.init.normal_(m.weight.data, 1.0, 0.02)
        nn.init.constant_(m.bias.data, 0)


def save_checkpoint(state: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    torch.save(state, path)
    print(f"  Checkpoint saved → {path}")


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}")

    # Models
    G = Generator(latent_dim=args.latent_dim).to(device)
    D = Discriminator().to(device)
    G.apply(weights_init)
    D.apply(weights_init)

    # Optionally resume
    start_epoch = 0
    if args.resume:
        ckpt = torch.load(args.resume, map_location=device)
        G.load_state_dict(ckpt["G"])
        D.load_state_dict(ckpt["D"])
        start_epoch = ckpt.get("epoch", 0) + 1
        print(f"Resumed from epoch {start_epoch - 1}")

    # Optimisers (Adam with β1=0.5 as recommended for GANs)
    opt_G = optim.Adam(G.parameters(), lr=args.lr, betas=(0.5, 0.999))
    opt_D = optim.Adam(D.parameters(), lr=args.lr, betas=(0.5, 0.999))

    criterion = nn.BCEWithLogitsLoss()

    dataloader = get_dataloader(args.data_dir, image_size=128, batch_size=args.batch_size)

    # Fixed noise for progress visualisation
    sample_dir = Path(args.save_dir) / "samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    fixed_noise = torch.randn(64, args.latent_dim, device=device)

    print(f"Starting training for {args.epochs} epochs …")

    for epoch in range(start_epoch, args.epochs):
        G.train()
        D.train()

        for batch_idx, (real_imgs, _) in enumerate(dataloader):
            real_imgs = real_imgs.to(device)
            batch_size = real_imgs.size(0)

            real_labels = torch.ones(batch_size, 1, device=device)
            fake_labels = torch.zeros(batch_size, 1, device=device)

            # ---- Train Discriminator ----
            opt_D.zero_grad()
            noise = torch.randn(batch_size, args.latent_dim, device=device)
            fake_imgs = G(noise).detach()

            loss_D = (
                criterion(D(real_imgs), real_labels)
                + criterion(D(fake_imgs), fake_labels)
            ) / 2
            loss_D.backward()
            opt_D.step()

            # ---- Train Generator ----
            opt_G.zero_grad()
            noise = torch.randn(batch_size, args.latent_dim, device=device)
            fake_imgs = G(noise)
            loss_G = criterion(D(fake_imgs), real_labels)  # fool D
            loss_G.backward()
            opt_G.step()

            if batch_idx % 100 == 0:
                print(
                    f"Epoch [{epoch}/{args.epochs}] "
                    f"Batch [{batch_idx}/{len(dataloader)}]  "
                    f"Loss_D: {loss_D.item():.4f}  Loss_G: {loss_G.item():.4f}"
                )

        # Save sample grid at end of each epoch
        G.eval()
        with torch.no_grad():
            samples = G(fixed_noise)
        grid_path = sample_dir / f"epoch_{epoch:04d}.png"
        utils.save_image(samples, grid_path, normalize=True, value_range=(-1, 1))

        # Save checkpoint
        if (epoch + 1) % args.save_every == 0 or epoch == args.epochs - 1:
            ckpt_path = str(Path(args.save_dir) / f"ckpt_epoch_{epoch:04d}.pt")
            save_checkpoint({"epoch": epoch, "G": G.state_dict(), "D": D.state_dict()}, ckpt_path)

    print("Training complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train face-generation GAN")
    parser.add_argument("--data_dir", type=str, required=True,
                        help="Root folder of face images (ImageFolder layout)")
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--batch_size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--latent_dim", type=int, default=128,
                        help="Size of the noise/latent vector")
    parser.add_argument("--save_dir", type=str, default="./checkpoints")
    parser.add_argument("--save_every", type=int, default=10,
                        help="Save checkpoint every N epochs")
    parser.add_argument("--resume", type=str, default=None,
                        help="Path to checkpoint to resume from")
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
