"""
Training loop — Ultra Edition (StyleGAN2-inspired)
===================================================

Loss and regularisation stack:
  ┌─ Discriminator ──────────────────────────────────────────────────────┐
  │  Non-saturating logistic loss (StyleGAN2)                            │
  │  R1 gradient penalty — lazy, every r1_interval steps                │
  │    loss_r1 = (r1_gamma / 2) * ||∇D(real)||²                          │
  │  Adaptive Discriminator Augmentation (ADA) on real + fake            │
  │  Perceptual feature-matching loss (VGG16 relu layers)                │
  └──────────────────────────────────────────────────────────────────────┘
  ┌─ Generator ───────────────────────────────────────────────────────────┐
  │  Non-saturating logistic loss  (softplus(-D(fake)))                   │
  │  Path-length penalty — lazy, every pl_interval steps                  │
  │    encourages smooth mapping: ||J^T y||₂ ≈ constant                  │
  │  Style-mixing regularisation — 50% of batches use two latent codes    │
  └──────────────────────────────────────────────────────────────────────┘
  ┌─ Optimiser ───────────────────────────────────────────────────────────┐
  │  Adam(β₁=0, β₂=0.99) — standard for spectral-normed GANs             │
  │  TTUR: lr_D=1e-4, lr_G=2e-4                                          │
  │  Lazy regularisation: scale G/D lr by reg_interval for Adam          │
  │  Cosine-annealing with 1000-step linear warmup                        │
  │  EMA (decay=0.9999) of Generator weights                              │
  │  Mixed-precision (torch.cuda.amp)                                     │
  └──────────────────────────────────────────────────────────────────────┘

Default: 500 epochs.

Usage:
    python train.py --data_dir ./data/faces --epochs 500 --save_dir ./checkpoints
"""

import argparse
import copy
import os
from pathlib import Path
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch import autograd
from torch.cuda.amp import GradScaler, autocast
from torch.utils.data import DataLoader
from torchvision import datasets, models, transforms, utils

from augment import AugmentPipe
from model import Discriminator, Generator


# ---------------------------------------------------------------------------
# VGG perceptual feature extractor
# ---------------------------------------------------------------------------

class VGGPerceptual(nn.Module):
    """
    Extract features from VGG16 relu2_2 and relu3_3 for feature-matching loss.
    Input: images in [-1, 1].
    """

    LAYERS = {"relu2_2": 9, "relu3_3": 16}

    def __init__(self):
        super().__init__()
        vgg = models.vgg16(weights=models.VGG16_Weights.DEFAULT)
        self.feat = nn.ModuleDict()
        features = list(vgg.features.children())
        for name, idx in self.LAYERS.items():
            self.feat[name] = nn.Sequential(*features[:idx + 1])
        for p in self.parameters():
            p.requires_grad_(False)
        # ImageNet normalisation
        self.register_buffer("mean", torch.tensor([0.485, 0.456, 0.406]).view(1, 3, 1, 1))
        self.register_buffer("std",  torch.tensor([0.229, 0.224, 0.225]).view(1, 3, 1, 1))

    def _norm(self, x: torch.Tensor) -> torch.Tensor:
        return (x * 0.5 + 0.5 - self.mean) / self.std

    def forward(self, x: torch.Tensor) -> list[torch.Tensor]:
        x = self._norm(x)
        return [block(x) for block in self.feat.values()]


# ---------------------------------------------------------------------------
# EMA helper
# ---------------------------------------------------------------------------

class EMA:
    def __init__(self, model: nn.Module, decay: float = 0.9999):
        self.model = copy.deepcopy(model).eval()
        self.decay = decay

    @torch.no_grad()
    def update(self, model: nn.Module) -> None:
        for ep, p in zip(self.model.parameters(), model.parameters()):
            ep.data.lerp_(p.data, 1.0 - self.decay)

    def generate(self, z: torch.Tensor) -> torch.Tensor:
        with torch.no_grad():
            return self.model(z)


# ---------------------------------------------------------------------------
# Regularisation
# ---------------------------------------------------------------------------

def r1_penalty(D: nn.Module, real: torch.Tensor) -> torch.Tensor:
    """R1 gradient penalty (Mescheder et al. 2018)."""
    real = real.requires_grad_(True)
    score = D(real).sum()
    grads = autograd.grad(score, real, create_graph=True)[0]
    return grads.pow(2).sum(dim=[1, 2, 3]).mean()


def path_length_penalty(fake_imgs: torch.Tensor,
                        ws: list[torch.Tensor],
                        pl_mean: torch.Tensor,
                        pl_decay: float = 0.01
                        ) -> tuple[torch.Tensor, torch.Tensor]:
    """
    Path-length penalty (Karras et al. 2020).
    Encourages equal-length steps in W-space to produce equal changes in image.
    """
    # Take gradient of a random projection of the output w.r.t. each w
    noise = torch.randn_like(fake_imgs) / (fake_imgs.size(2) * fake_imgs.size(3)) ** 0.5
    # We need the gradient w.r.t. the first w vector
    w0 = ws[0].requires_grad_(True)
    pl_grads = autograd.grad(
        outputs=(fake_imgs * noise).sum(),
        inputs=w0,
        create_graph=True,
    )[0]
    pl_lengths = pl_grads.pow(2).sum(dim=1).sqrt()
    pl_mean_new = pl_mean.lerp(pl_lengths.mean().detach(), pl_decay)
    pl_penalty = (pl_lengths - pl_mean_new).pow(2).mean()
    return pl_penalty, pl_mean_new


def perceptual_loss(vgg: VGGPerceptual,
                    real: torch.Tensor,
                    fake: torch.Tensor) -> torch.Tensor:
    with torch.no_grad():
        feats_real = vgg(real)
    feats_fake = vgg(fake)
    loss = sum(F.l1_loss(fr, ff) for fr, ff in zip(feats_real, feats_fake))
    return loss


# ---------------------------------------------------------------------------
# Dataloader
# ---------------------------------------------------------------------------

def get_dataloader(data_dir: str, image_size: int, batch_size: int) -> DataLoader:
    transform = transforms.Compose([
        transforms.Resize(image_size),
        transforms.CenterCrop(image_size),
        transforms.ToTensor(),
        transforms.Normalize([0.5, 0.5, 0.5], [0.5, 0.5, 0.5]),
    ])
    dataset = datasets.ImageFolder(root=data_dir, transform=transform)
    use_gpu = torch.cuda.is_available()
    return DataLoader(dataset, batch_size=batch_size, shuffle=True,
                      num_workers=4 if use_gpu else 0,
                      pin_memory=use_gpu, drop_last=True)


# ---------------------------------------------------------------------------
# LR schedule: linear warmup + cosine annealing
# ---------------------------------------------------------------------------

def get_scheduler(optimizer: optim.Optimizer, warmup_steps: int,
                  total_steps: int) -> optim.lr_scheduler.LambdaLR:
    def lr_lambda(step: int) -> float:
        if step < warmup_steps:
            return step / max(warmup_steps, 1)
        progress = (step - warmup_steps) / max(total_steps - warmup_steps, 1)
        return 0.5 * (1.0 + math.cos(math.pi * progress))

    import math
    return optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def save_checkpoint(state: dict, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    torch.save(state, path)
    print(f"  [ckpt] {path}")


def count_params(m: nn.Module) -> str:
    n = sum(p.numel() for p in m.parameters() if p.requires_grad)
    return f"{n / 1e6:.1f}M"


# ---------------------------------------------------------------------------
# Training
# ---------------------------------------------------------------------------

def train(args: argparse.Namespace) -> None:
    import math

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    use_amp = device.type == "cuda"
    print(f"Device: {device}  AMP: {use_amp}")

    # ---- Models ----
    G = Generator(z_dim=args.z_dim, w_dim=args.w_dim, channel_cap=args.channel_cap).to(device)
    D = Discriminator(channel_cap=args.channel_cap).to(device)
    print(f"G params: {count_params(G)}  |  D params: {count_params(D)}")

    G_ema = EMA(G, decay=args.ema_decay)

    # VGG for perceptual loss
    vgg: Optional[VGGPerceptual] = None
    if args.lambda_percep > 0:
        try:
            vgg = VGGPerceptual().to(device).eval()
            print("VGG perceptual loss: enabled")
        except Exception as e:
            print(f"VGG perceptual loss disabled ({e})")

    # ADA augmentation pipeline
    aug = AugmentPipe(p=0.0, target_rt=args.ada_target, p_step=args.ada_step)

    # ---- Optimisers (lazy reg: scale lr by reg_interval) ----
    r1_c = args.r1_interval / (args.r1_interval + 1)
    pl_c = args.pl_interval / (args.pl_interval + 1)
    opt_D = optim.Adam(D.parameters(), lr=args.lr_D * r1_c,
                       betas=(0.0 ** r1_c, 0.99 ** r1_c))
    opt_G = optim.Adam(G.parameters(), lr=args.lr_G * pl_c,
                       betas=(0.0 ** pl_c, 0.99 ** pl_c))

    # ---- Resume ----
    start_epoch = 0
    pl_mean = torch.zeros([], device=device)
    global_step = 0

    if args.resume:
        ckpt = torch.load(args.resume, map_location=device)
        G.load_state_dict(ckpt["G"])
        D.load_state_dict(ckpt["D"])
        if "G_ema" in ckpt:
            G_ema.model.load_state_dict(ckpt["G_ema"])
        if "pl_mean" in ckpt:
            pl_mean = ckpt["pl_mean"].to(device)
        if "aug_p" in ckpt:
            aug.p = ckpt["aug_p"]
        start_epoch = ckpt.get("epoch", 0) + 1
        global_step = ckpt.get("global_step", 0)
        print(f"Resumed from epoch {start_epoch - 1}  (aug_p={aug.p:.3f})")

    dataloader = get_dataloader(args.data_dir, 128, args.batch_size)
    steps_per_epoch = len(dataloader)
    total_steps = steps_per_epoch * args.epochs

    # Warmup + cosine LR (applied per step)
    sched_G = get_scheduler(opt_G, args.warmup_steps, total_steps)
    sched_D = get_scheduler(opt_D, args.warmup_steps, total_steps)

    scaler_G = GradScaler(enabled=use_amp)
    scaler_D = GradScaler(enabled=use_amp)

    sample_dir = Path(args.save_dir) / "samples"
    sample_dir.mkdir(parents=True, exist_ok=True)
    fixed_z = torch.randn(64, args.z_dim, device=device)

    print(f"\nTraining {args.epochs} epochs  |  r1_gamma={args.r1_gamma}"
          f"  pl_weight={args.pl_weight}  percep={args.lambda_percep}\n")

    for epoch in range(start_epoch, args.epochs):
        G.train()
        D.train()

        loss_D_sum = loss_G_sum = r1_sum = pl_sum = 0.0
        n_steps = 0
        max_steps = args.steps_per_epoch if args.steps_per_epoch > 0 else len(dataloader)

        for step_i, (real_imgs, _) in enumerate(dataloader):
            if step_i >= max_steps:
                break
            real_imgs = real_imgs.to(device)
            B = real_imgs.size(0)

            # ================================================================
            # Discriminator step
            # ================================================================
            opt_D.zero_grad()

            z = torch.randn(B, args.z_dim, device=device)

            with autocast(enabled=use_amp):
                # Style mixing: 50% chance use two latent codes
                mix_z = None
                mix_layer = None
                if args.style_mixing and torch.rand(1).item() < 0.5:
                    mix_z = torch.randn(B, args.z_dim, device=device)
                    mix_layer = torch.randint(1, G.mapping.num_layers, (1,)).item()

                fake_imgs = G(z, mixing_z=mix_z, mixing_layer=mix_layer).detach()

                # ADA augmentation
                real_aug = aug(real_imgs)
                fake_aug = aug(fake_imgs)

                # Non-saturating logistic loss
                real_score = D(real_aug)
                fake_score = D(fake_aug)
                loss_D = F.softplus(-real_score).mean() + F.softplus(fake_score).mean()

                # Perceptual feature-matching on D's discriminated features
                if vgg is not None:
                    loss_D = loss_D + args.lambda_percep * perceptual_loss(vgg, real_imgs, fake_imgs)

            scaler_D.scale(loss_D).backward()

            # Lazy R1 regularisation
            r1_val = 0.0
            if global_step % args.r1_interval == 0:
                opt_D.zero_grad()
                with autocast(enabled=use_amp):
                    r1 = r1_penalty(D, real_imgs)
                    loss_r1 = (args.r1_gamma / 2) * r1 * args.r1_interval
                scaler_D.scale(loss_r1).backward()
                r1_val = r1.item()

            scaler_D.step(opt_D)
            scaler_D.update()
            sched_D.step()

            # Adaptive augmentation update
            with torch.no_grad():
                r_t = real_score.sign().mean().item()
            aug.update(r_t)

            # ================================================================
            # Generator step
            # ================================================================
            opt_G.zero_grad()

            z = torch.randn(B, args.z_dim, device=device)

            with autocast(enabled=use_amp):
                mix_z = None
                mix_layer = None
                if args.style_mixing and torch.rand(1).item() < 0.5:
                    mix_z = torch.randn(B, args.z_dim, device=device)
                    mix_layer = torch.randint(1, G.mapping.num_layers, (1,)).item()

                fake_imgs_g = G(z, mixing_z=mix_z, mixing_layer=mix_layer)
                fake_aug_g  = aug(fake_imgs_g)
                fake_score_g = D(fake_aug_g)
                loss_G = F.softplus(-fake_score_g).mean()

            scaler_G.scale(loss_G).backward(retain_graph=(global_step % args.pl_interval == 0))

            # Lazy path-length penalty
            pl_val = 0.0
            if global_step % args.pl_interval == 0:
                opt_G.zero_grad()
                z2 = torch.randn(B, args.z_dim, device=device)
                # Compute ws with grad enabled, then run synthesis on same graph
                ws2 = G.mapping(z2)
                ws2[0] = ws2[0].requires_grad_(True)
                with autocast(enabled=use_amp):
                    fake_for_pl = G.synthesis_forward(ws2)
                pl_pen, pl_mean = path_length_penalty(fake_for_pl, ws2, pl_mean)
                loss_pl = pl_pen * args.pl_weight * args.pl_interval
                scaler_G.scale(loss_pl).backward()
                pl_val = pl_pen.item()

            scaler_G.step(opt_G)
            scaler_G.update()
            sched_G.step()

            G_ema.update(G)

            loss_D_sum += loss_D.item()
            loss_G_sum += loss_G.item()
            r1_sum     += r1_val
            pl_sum     += pl_val
            n_steps    += 1
            global_step += 1

        # ------------------------------------------------------------------
        # End-of-epoch logging
        # ------------------------------------------------------------------
        avg = lambda s, n=n_steps: s / max(n, 1)
        print(
            f"Epoch [{epoch:4d}/{args.epochs}]  "
            f"D={avg(loss_D_sum):+.4f}  G={avg(loss_G_sum):+.4f}  "
            f"R1={avg(r1_sum):.4f}  PL={avg(pl_sum):.4f}  "
            f"aug_p={aug.p:.3f}  "
            f"lr_G={sched_G.get_last_lr()[0]:.2e}"
        )

        G.eval()
        samples = G_ema.generate(fixed_z)
        utils.save_image(samples, sample_dir / f"epoch_{epoch:04d}.png",
                         normalize=True, value_range=(-1, 1))

        if (epoch + 1) % args.save_every == 0 or epoch == args.epochs - 1:
            save_checkpoint({
                "epoch": epoch,
                "global_step": global_step,
                "G": G.state_dict(),
                "D": D.state_dict(),
                "G_ema": G_ema.model.state_dict(),
                "opt_G": opt_G.state_dict(),
                "opt_D": opt_D.state_dict(),
                "pl_mean": pl_mean,
                "aug_p": aug.p,
            }, str(Path(args.save_dir) / f"ckpt_epoch_{epoch:04d}.pt"))

    print("\nTraining complete.")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train ultra face-generation GAN")
    p.add_argument("--data_dir",    type=str, required=True)
    p.add_argument("--epochs",      type=int,   default=500)
    p.add_argument("--batch_size",  type=int,   default=8,
                   help="Reduce if GPU OOM (heavy model)")
    p.add_argument("--z_dim",        type=int,   default=512,
                   help="Latent z dimension")
    p.add_argument("--w_dim",        type=int,   default=1024,
                   help="Intermediate W dimension")
    p.add_argument("--channel_cap",  type=int,   default=512,
                   help="Max channels per layer (use 32-64 for CPU runs)")
    p.add_argument("--lr_G",        type=float, default=2e-4)
    p.add_argument("--lr_D",        type=float, default=1e-4)
    # R1 regularisation
    p.add_argument("--r1_gamma",    type=float, default=10.0,
                   help="R1 penalty weight")
    p.add_argument("--r1_interval", type=int,   default=16,
                   help="Apply R1 every N steps (lazy)")
    # Path-length penalty
    p.add_argument("--pl_weight",   type=float, default=2.0)
    p.add_argument("--pl_interval", type=int,   default=4,
                   help="Apply PL penalty every N steps (lazy)")
    # Style mixing
    p.add_argument("--style_mixing", action="store_true", default=True)
    # ADA
    p.add_argument("--ada_target",  type=float, default=0.6,
                   help="r_t target for ADA (0.6 = slight D advantage)")
    p.add_argument("--ada_step",    type=float, default=5e-3)
    # Perceptual loss
    p.add_argument("--lambda_percep", type=float, default=0.1,
                   help="VGG perceptual feature-matching weight (0=disabled)")
    # EMA / schedule
    p.add_argument("--ema_decay",   type=float, default=0.9999)
    p.add_argument("--warmup_steps",type=int,   default=1000)
    # Misc
    p.add_argument("--save_dir",    type=str,   default="./checkpoints")
    p.add_argument("--save_every",      type=int,   default=10)
    p.add_argument("--resume",          type=str,   default=None)
    p.add_argument("--steps_per_epoch", type=int,   default=0,
                   help="Cap steps per epoch (0=full epoch). Use for CPU runs.")
    return p.parse_args()


if __name__ == "__main__":
    train(parse_args())
