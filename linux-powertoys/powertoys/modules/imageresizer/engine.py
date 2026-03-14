"""ImageResizer core engine - batch image resizing with Pillow."""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple, Callable

# Pillow is required; gracefully fail so the rest of the app still loads
try:
    from PIL import Image, ImageFilter
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False


SUPPORTED_FORMATS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tiff", ".tif", ".webp", ".ico"}

FIT_MODES = ["Fit (keep aspect ratio)", "Fill (crop to fit)", "Stretch (ignore aspect)", "Width only", "Height only"]


@dataclass
class ResizePreset:
    name: str
    width: int
    height: int
    fit: str = "Fit (keep aspect ratio)"

    def __str__(self):
        return f"{self.name} ({self.width}×{self.height})"


DEFAULT_PRESETS: List[ResizePreset] = [
    ResizePreset("Small",     854,  480,  "Fit (keep aspect ratio)"),
    ResizePreset("Medium",   1280,  720,  "Fit (keep aspect ratio)"),
    ResizePreset("Large",    1920, 1080,  "Fit (keep aspect ratio)"),
    ResizePreset("Phone",     750, 1334,  "Fit (keep aspect ratio)"),
    ResizePreset("Thumbnail", 256,  256,  "Fill (crop to fit)"),
    ResizePreset("Icon",       64,   64,  "Fill (crop to fit)"),
    ResizePreset("4K",        3840, 2160, "Fit (keep aspect ratio)"),
]


@dataclass
class ResizeResult:
    source: Path
    output: Path
    original_size: Tuple[int, int] = (0, 0)
    new_size: Tuple[int, int] = (0, 0)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


def _compute_new_size(orig_w: int, orig_h: int, target_w: int, target_h: int, fit: str) -> Tuple[int, int]:
    if fit == "Stretch (ignore aspect)":
        return target_w, target_h
    if fit == "Width only":
        ratio = target_w / orig_w
        return target_w, max(1, int(orig_h * ratio))
    if fit == "Height only":
        ratio = target_h / orig_h
        return max(1, int(orig_w * ratio)), target_h
    # Fit and Fill both start with aspect-ratio computation
    ratio_w = target_w / orig_w
    ratio_h = target_h / orig_h
    if fit == "Fill (crop to fit)":
        ratio = max(ratio_w, ratio_h)
    else:  # "Fit"
        ratio = min(ratio_w, ratio_h)
    return max(1, int(orig_w * ratio)), max(1, int(orig_h * ratio))


def _make_output_path(source: Path, suffix: str, output_dir: Optional[str]) -> Path:
    new_name = source.stem + suffix + source.suffix
    if output_dir:
        return Path(output_dir) / new_name
    return source.parent / new_name


class ImageResizerEngine:
    def __init__(
        self,
        preset: Optional[ResizePreset] = None,
        custom_width: int = 0,
        custom_height: int = 0,
        fit_mode: str = "Fit (keep aspect ratio)",
        output_suffix: str = "_resized",
        output_dir: Optional[str] = None,
        output_format: str = "same",  # "same", "jpg", "png", "webp"
        quality: int = 90,
        keep_originals: bool = True,
        sharpen: bool = False,
    ):
        self.preset = preset
        self.custom_width = custom_width
        self.custom_height = custom_height
        self.fit_mode = fit_mode
        self.output_suffix = output_suffix
        self.output_dir = output_dir
        self.output_format = output_format
        self.quality = quality
        self.keep_originals = keep_originals
        self.sharpen = sharpen

    @property
    def target_width(self) -> int:
        return self.preset.width if self.preset else self.custom_width

    @property
    def target_height(self) -> int:
        return self.preset.height if self.preset else self.custom_height

    @property
    def active_fit(self) -> str:
        return self.preset.fit if self.preset else self.fit_mode

    def resize_image(self, source: Path) -> ResizeResult:
        if not HAS_PILLOW:
            return ResizeResult(source, source, error="Pillow is not installed. Run: pip3 install Pillow")

        if source.suffix.lower() not in SUPPORTED_FORMATS:
            return ResizeResult(source, source, error=f"Unsupported format: {source.suffix}")

        # Determine output extension
        ext = source.suffix if self.output_format == "same" else f".{self.output_format}"
        out_name = source.stem + self.output_suffix + ext
        if self.output_dir:
            os.makedirs(self.output_dir, exist_ok=True)
            output = Path(self.output_dir) / out_name
        else:
            output = source.parent / out_name

        try:
            with Image.open(source) as img:
                orig_size = img.size
                orig_w, orig_h = orig_size

                tw, th = self.target_width, self.target_height
                if tw <= 0 and th <= 0:
                    return ResizeResult(source, output, orig_size, orig_size, "Invalid target dimensions")

                new_w, new_h = _compute_new_size(orig_w, orig_h, tw or orig_w, th or orig_h, self.active_fit)

                if self.active_fit == "Fill (crop to fit)":
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                    # Center-crop to exact target
                    left = (new_w - tw) // 2
                    top = (new_h - th) // 2
                    img = img.crop((left, top, left + tw, top + th))
                    new_w, new_h = tw, th
                else:
                    img = img.resize((new_w, new_h), Image.LANCZOS)

                if self.sharpen:
                    img = img.filter(ImageFilter.SHARPEN)

                # Convert RGBA → RGB for JPEG
                save_img = img
                if ext.lower() in (".jpg", ".jpeg") and img.mode in ("RGBA", "LA", "P"):
                    bg = Image.new("RGB", img.size, (255, 255, 255))
                    bg.paste(img, mask=img.split()[-1] if img.mode in ("RGBA", "LA") else None)
                    save_img = bg

                save_kwargs = {}
                if ext.lower() in (".jpg", ".jpeg", ".webp"):
                    save_kwargs["quality"] = self.quality
                    save_kwargs["optimize"] = True
                elif ext.lower() == ".png":
                    save_kwargs["optimize"] = True

                save_img.save(output, **save_kwargs)

                if not self.keep_originals and output != source:
                    source.unlink()

                return ResizeResult(source, output, orig_size, (new_w, new_h))

        except Exception as e:
            return ResizeResult(source, output, error=str(e))

    def resize_batch(
        self,
        sources: List[Path],
        progress_cb: Optional[Callable[[int, int, ResizeResult], None]] = None,
    ) -> List[ResizeResult]:
        results = []
        for i, src in enumerate(sources):
            result = self.resize_image(src)
            results.append(result)
            if progress_cb:
                progress_cb(i + 1, len(sources), result)
        return results
