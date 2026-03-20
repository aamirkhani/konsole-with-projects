"""
Training loop for the Face Generation GAN — Heavy Edition
==========================================================

Upgrades over v1:
  * WGAN-GP loss (Wasserstein + gradient penalty) — far more stable than BCE
  * n_critic = 5  (train D 5x per G step, standard WGAN schedule)
  * Two-timescale update rule (TTUR): D lr=1e-4, G lr=4e-4
  * EMA (Exponential Moving Average) of Generator weights -> better samples
  * Mixed-precision training (torch.cuda.amp) for speed on GPU
  * Cosine-annealing LR schedulers on both G and D
  * Default 300 epochs

Usage:
    python train.py --data_dir ./data/faces --epochs 300 --save_dir ./checkpoints
"""

import argparse
import copy
import os
from pathlib import Path

import torch
import torch.optim as optim
from torch import autograd
from torch.cuda.amp import GradScaler, autocast
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
        transforms.RandomHorizontalFlip(),          # free data augmentation
        transforms.ColorJitter(0.05, 0.05, 0.05),  # subtle colour aug
        transforms.ToTensor(),
        transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),  # -> [-1, 1]
    ])
    dataset = datasets.ImageFolder(root=data_dir, transform=transform)
    return DataLoader(dataset, batch_size=batch_size, shuffle=True,
                      num_workers=4, pin_memory=True, drop_last=True)


def gradient_penalty(D: Discriminator, real: torch.Tensor,
                     fake: torch.Tensor, device: torch.device,
                     lambda_gp: float = 10.0) -> torch.Tensor:
    """WGAN-GP gradient penalty (Gulrajani et al. 2017)."""
    B = real.size(0)
    alpha = torch.rand(B, 1, 1, 1, device=device)
    interp = (alpha * real + (1 - alpha) * fake).requires_grad_(True)
    d_interp = D(interp)
    grads = autograd.grad(
        outputs=d_interp,
        inputs=interp,
        grad_outputs=torch.ones_like(d_interp),
        create_graph=True,
        retain_graph=True,
    )[0]
    grads = grads.view(B, -1)
    penalty = ((grads.norm(2, dim=1) - 1) ** 2).mean()
    return lambda_gp * penalty


class EMA:
    """Exponential moving average of model weights."""

    def __init__(self, model: torch.nn.Module, decay: float = 0.999):
        self.model = copy.deepcopy(model).eval()
        self.decay = decay

    @torch.no_grad()
    def update(self, model: torch.nn.Module) -> None:
        for ema_p, p in zip(self.model.parameters(), model.parameters()):
            ema_p.data.mul_(self.decay).add_(p.data, alpha=1 - self.decay)

    def generate(self, noise: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            return self.model(noise)


def save_checkpoint(state: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    torch.save(state, path)
    print(f"  Checkpoint saved → {path}")


def count_params(model: torch.nn.Module) -> str:
    n = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return f"{n / 1e6:.1f}M"


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(args: argparse.Namespace) -> None:
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = device.type == "cuda"
    print(f"Device: {device}  |  AMP: {use_amp}")

    # Models
    G = Generator(latent_dim=args.latent_dim, base_channels=args.base_channels).to(device)
    D = Discriminator(base_channels=args.base_channels).to(device)
    print(f"Generator params : {count_params(G)}")
    print(f"Discriminator params: {count_params(D)}")

    # EMA copy of Generator
    G_ema = EMA(G, decay=args.ema_decay)

    # Resume
    start_epoch = 0
    if args.resume:
        ckpt = torch.load(args.resume, map_location=device)
        G.load_state_dict(ckpt["G"])
        D.load_state_dict(ckpt["D"])
        if "G_ema" in ckpt:
            G_ema.model.load_state_dict(ckpt["G_ema"])
        start_epoch = ckpt.get("epoch", 0) + 1
        print(f"Resumed from epoch {start_epoch - 1}")

    # Two-timescale optimisers (TTUR)
    opt_G = optim.Adam(G.parameters(), lr=args.lr_G, betas=(0.0, 0.99))
    opt_D = optim.Adam(D.parameters(), lr=args.lr_D, betas=(0.0, 0.99))

    # Cosine annealing LR schedulers
    sched_G = optim.lr_scheduler.CosineAnnealingLR(opt_G, T_max=args.epochs, eta_min=1e-6)
    sched_D = optim.lr_scheduler.CosineAnnealingLR(opt_D, T_max=args.epochs, eta_min=1e-6)

    # Mixed precision scalers
    scaler_G = GradScaler(enabled=use_amp)
    scaler_D = GradScaler(enabled=use_amp)

    dataloader = get_dataloader(args.data_dir, image_size=128, batch_size=args.batch_size)

    sample_dir = Path(args.save_dir) / "samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    fixed_noise = torch.randn(64, args.latent_dim, device=device)

    print(f"Training for {args.epochs} epochs, n_critic={args.n_critic} …\n")

    for epoch in range(start_epoch, args.epochs):
        G.train()
        D.train()

        loss_D_accum = 0.0
        loss_G_accum = 0.0
        g_steps = 0

        data_iter = iter(dataloader)

        # We iterate based on the number of G updates per epoch
        batches_per_epoch = len(dataloader) // (args.n_critic + 1)

        for _ in range(batches_per_epoch):

            # ---- Train Discriminator n_critic times ----
            for _ in range(args.n_critic):
                try:
                    real_imgs, _ = next(data_iter)
                except StopIteration:
                    data_iter = iter(dataloader)
                    real_imgs, _ = next(data_iter)

                real_imgs = real_imgs.to(device)
                B = real_imgs.size(0)
                noise = torch.randn(B, args.latent_dim, device=device)

                opt_D.zero_grad()
                with autocast(enabled=use_amp):
                    fake_imgs = G(noise).detach()
                    # WGAN loss: maximise E[D(real)] - E[D(fake)]
                    loss_real = -D(real_imgs).mean()
                    loss_fake =  D(fake_imgs).mean()
                    gp = gradient_penalty(D, real_imgs, fake_imgs, device, args.lambda_gp)
                    loss_D = loss_real + loss_fake + gp

                scaler_D.scale(loss_D).backward()
                scaler_D.step(opt_D)
                scaler_D.update()
                loss_D_accum += loss_D.item()

            # ---- Train Generator once ----
            try:
                real_imgs, _ = next(data_iter)
            except StopIteration:
                data_iter = iter(dataloader)
                real_imgs, _ = next(data_iter)

            B = real_imgs.size(0)
            noise = torch.randn(B, args.latent_dim, device=device)

            opt_G.zero_grad()
            with autocast(enabled=use_amp):
                fake_imgs = G(noise)
                loss_G = -D(fake_imgs).mean()  # minimise -E[D(fake)]

            scaler_G.scale(loss_G).backward()
            scaler_G.step(opt_G)
            scaler_G.update()

            G_ema.update(G)
            loss_G_accum += loss_G.item()
            g_steps += 1

        sched_G.step()
        sched_D.step()

        avg_D = loss_D_accum / max(g_steps * args.n_critic, 1)
        avg_G = loss_G_accum / max(g_steps, 1)
        lr_g = sched_G.get_last_lr()[0]
        lr_d = sched_D.get_last_lr()[0]
        print(
            f"Epoch [{epoch:4d}/{args.epochs}]  "
            f"Loss_D: {avg_D:+.4f}  Loss_G: {avg_G:+.4f}  "
            f"lr_G: {lr_g:.2e}  lr_D: {lr_d:.2e}"
        )

        # Sample grid from EMA generator
        G.eval()
        samples = G_ema.generate(fixed_noise)
        grid_path = sample_dir / f"epoch_{epoch:04d}.png"
        utils.save_image(samples, grid_path, normalize=True, value_range=(-1, 1))

        # Save checkpoint
        if (epoch + 1) % args.save_every == 0 or epoch == args.epochs - 1:
            ckpt_path = str(Path(args.save_dir) / f"ckpt_epoch_{epoch:04d}.pt")
            save_checkpoint({
                "epoch": epoch,
                "G": G.state_dict(),
                "D": D.state_dict(),
                "G_ema": G_ema.model.state_dict(),
                "opt_G": opt_G.state_dict(),
                "opt_D": opt_D.state_dict(),
            }, ckpt_path)

    print("\nTraining complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train heavy face-generation GAN")
    parser.add_argument("--data_dir", type=str, required=True,
                        help="Root folder of face images (ImageFolder layout)")
    parser.add_argument("--epochs", type=int, default=300,
                        help="Total training epochs (default: 300)")
    parser.add_argument("--batch_size", type=int, default=16,
                        help="Batch size (reduce if GPU OOM)")
    parser.add_argument("--latent_dim", type=int, default=256,
                        help="Latent noise dimension")
    parser.add_argument("--base_channels", type=int, default=128,
                        help="Base channel multiplier (128 ~34M G params)")
    parser.add_argument("--lr_G", type=float, default=4e-4,
                        help="Generator learning rate (TTUR)")
    parser.add_argument("--lr_D", type=float, default=1e-4,
                        help="Discriminator learning rate (TTUR)")
    parser.add_argument("--n_critic", type=int, default=5,
                        help="D updates per G update (WGAN schedule)")
    parser.add_argument("--lambda_gp", type=float, default=10.0,
                        help="Gradient penalty coefficient")
    parser.add_argument("--ema_decay", type=float, default=0.999,
                        help="EMA decay for Generator weights")
    parser.add_argument("--save_dir", type=str, default="./checkpoints")
    parser.add_argument("--save_every", type=int, default=10,
                        help="Save checkpoint every N epochs")
    parser.add_argument("--resume", type=str, default=None,
                        help="Path to checkpoint to resume from")
    return parser.parse_args()


if __name__ == "__main__":
    train(parse_args())
