"""PasteAsPlainText engine - strip formatting from clipboard content."""

import subprocess
import re
from typing import Optional


def get_clipboard_text() -> Optional[str]:
    """Read current clipboard content as plain text."""
    for tool in [
        ["xclip", "-selection", "clipboard", "-o"],
        ["xsel", "--clipboard", "--output"],
    ]:
        try:
            r = subprocess.run(tool, capture_output=True, text=True, timeout=3)
            if r.returncode == 0 and r.stdout:
                return r.stdout
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def set_clipboard_text(text: str) -> bool:
    """Write plain text to clipboard."""
    for tool in [
        ["xclip", "-selection", "clipboard"],
        ["xsel", "--clipboard", "--input"],
    ]:
        try:
            r = subprocess.run(
                tool, input=text, capture_output=True, text=True, timeout=3
            )
            if r.returncode == 0:
                return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return False


def strip_html(text: str) -> str:
    """Remove HTML tags from text."""
    # Replace block-level tags with newlines
    text = re.sub(r"<(br|p|div|h[1-6]|li|tr|td|th)[^>]*>", "\n", text, flags=re.IGNORECASE)
    # Remove all remaining tags
    text = re.sub(r"<[^>]+>", "", text)
    # Decode common HTML entities
    entities = {
        "&amp;": "&", "&lt;": "<", "&gt;": ">",
        "&quot;": '"', "&#39;": "'", "&nbsp;": " ",
        "&mdash;": "—", "&ndash;": "–", "&hellip;": "…",
    }
    for entity, char in entities.items():
        text = text.replace(entity, char)
    return text


def strip_markdown(text: str) -> str:
    """Remove common Markdown formatting markers."""
    # Headers
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Bold/italic
    text = re.sub(r"\*{1,3}(.+?)\*{1,3}", r"\1", text)
    text = re.sub(r"_{1,3}(.+?)_{1,3}", r"\1", text)
    # Inline code
    text = re.sub(r"`(.+?)`", r"\1", text)
    # Links
    text = re.sub(r"\[(.+?)\]\(.+?\)", r"\1", text)
    # Blockquotes
    text = re.sub(r"^>\s+", "", text, flags=re.MULTILINE)
    return text


def normalize_whitespace(text: str, collapse_lines: bool = False) -> str:
    """Normalize whitespace: strip trailing spaces, collapse blank lines."""
    lines = [line.rstrip() for line in text.splitlines()]
    if collapse_lines:
        # Collapse multiple blank lines into one
        result = []
        blank = 0
        for line in lines:
            if line == "":
                blank += 1
                if blank <= 1:
                    result.append(line)
            else:
                blank = 0
                result.append(line)
        return "\n".join(result).strip()
    return "\n".join(lines).strip()


class PastePlainEngine:
    def __init__(self):
        self.strip_html_tags: bool = True
        self.strip_markdown_syntax: bool = False
        self.collapse_blank_lines: bool = True
        self.trim_whitespace: bool = True

    def process(self, text: str) -> str:
        """Apply configured stripping to text."""
        if self.strip_html_tags:
            text = strip_html(text)
        if self.strip_markdown_syntax:
            text = strip_markdown(text)
        if self.trim_whitespace or self.collapse_blank_lines:
            text = normalize_whitespace(text, collapse_lines=self.collapse_blank_lines)
        return text

    def get_and_strip(self) -> Optional[tuple]:
        """
        Read clipboard, strip formatting, return (original, stripped).
        Returns None if clipboard is empty.
        """
        original = get_clipboard_text()
        if original is None:
            return None
        stripped = self.process(original)
        return original, stripped

    def paste_plain(self) -> bool:
        """Read clipboard, strip formatting, write plain text back."""
        result = self.get_and_strip()
        if result is None:
            return False
        _, stripped = result
        return set_clipboard_text(stripped)
