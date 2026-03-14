"""TextExtractor engine - OCR using tesseract and screenshot capture."""

import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional, List


class TextExtractorEngine:
    """Extract text from screen regions using tesseract OCR."""

    LANGUAGES = ["eng", "fra", "deu", "spa", "ita", "por", "rus", "jpn", "zho", "ara"]

    def __init__(self, language: str = "eng"):
        self.language = language
        self._has_tesseract = self._check_tesseract()
        self._has_scrot = self._check_tool("scrot")
        self._has_gnome_ss = self._check_tool("gnome-screenshot")
        self._has_import = self._check_tool("import")  # ImageMagick

    @staticmethod
    def _check_tool(name: str) -> bool:
        try:
            subprocess.run([name, "--version"], capture_output=True, timeout=3)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _check_tesseract(self) -> bool:
        try:
            result = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=3)
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def get_available_languages(self) -> List[str]:
        """Get list of installed tesseract language packs."""
        if not self._has_tesseract:
            return []
        try:
            result = subprocess.run(
                ["tesseract", "--list-langs"],
                capture_output=True, text=True, timeout=5,
            )
            lines = result.stdout.splitlines() + result.stderr.splitlines()
            langs = [l.strip() for l in lines if l.strip() and not l.startswith("List")]
            return langs if langs else ["eng"]
        except Exception:
            return ["eng"]

    def capture_region(self, x: int, y: int, w: int, h: int) -> Optional[str]:
        """Capture a screen region to a temp file, return path."""
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()

        if self._has_scrot:
            try:
                subprocess.run(
                    ["scrot", "-a", f"{x},{y},{w},{h}", tmp.name],
                    timeout=10, check=True,
                )
                return tmp.name
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

        if self._has_import:
            try:
                subprocess.run(
                    ["import", "-window", "root", "-crop", f"{w}x{h}+{x}+{y}", tmp.name],
                    timeout=10, check=True,
                )
                return tmp.name
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
                pass

        # Try GNOME screenshot via dbus
        try:
            subprocess.run(
                ["gnome-screenshot", "-a", f"--file={tmp.name}"],
                timeout=30,
            )
            if Path(tmp.name).exists() and Path(tmp.name).stat().st_size > 0:
                return tmp.name
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        os.unlink(tmp.name)
        return None

    def capture_full_screenshot(self) -> Optional[str]:
        """Capture full screen to a temp file."""
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()

        if self._has_scrot:
            try:
                subprocess.run(["scrot", tmp.name], timeout=10, check=True)
                return tmp.name
            except Exception:
                pass

        if self._has_import:
            try:
                subprocess.run(["import", "-window", "root", tmp.name], timeout=10, check=True)
                return tmp.name
            except Exception:
                pass

        os.unlink(tmp.name)
        return None

    def ocr_file(self, image_path: str, preprocess: bool = True) -> str:
        """Run OCR on an image file, return extracted text."""
        if not self._has_tesseract:
            return "Error: tesseract is not installed.\nInstall with: sudo apt install tesseract-ocr"

        if not Path(image_path).exists():
            return "Error: Image file not found."

        # Preprocess: upscale for better OCR if small
        processed_path = image_path
        if preprocess:
            processed_path = self._preprocess(image_path)

        try:
            result = subprocess.run(
                ["tesseract", processed_path, "stdout", "-l", self.language, "--oem", "3", "--psm", "6"],
                capture_output=True, text=True, timeout=30,
            )
            if processed_path != image_path:
                os.unlink(processed_path)
            return result.stdout.strip() if result.stdout.strip() else "(No text detected)"
        except subprocess.TimeoutExpired:
            return "Error: OCR timed out"
        except Exception as e:
            return f"Error: {e}"

    def _preprocess(self, image_path: str) -> str:
        """Enhance image for better OCR (scale, grayscale)."""
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        tmp.close()
        try:
            from PIL import Image, ImageFilter, ImageEnhance
            with Image.open(image_path) as img:
                # Scale up if small
                w, h = img.size
                if w < 300 or h < 100:
                    scale = max(300 / w, 100 / h, 2)
                    img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
                # Grayscale + contrast boost
                img = img.convert("L")
                img = ImageEnhance.Contrast(img).enhance(2.0)
                img.save(tmp.name)
            return tmp.name
        except ImportError:
            return image_path
        except Exception:
            return image_path

    def ocr_clipboard_image(self) -> str:
        """Try to OCR an image from clipboard."""
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            tmp.close()
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-t", "image/png", "-o"],
                capture_output=True, timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                with open(tmp.name, "wb") as f:
                    f.write(result.stdout)
                return self.ocr_file(tmp.name)
            os.unlink(tmp.name)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
        return "No image found in clipboard."
