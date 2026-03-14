"""PowerRename core engine - regex/find-replace batch file renaming."""

import re
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Callable


CASE_TRANSFORMS = {
    "None": None,
    "UPPERCASE": str.upper,
    "lowercase": str.lower,
    "Title Case": str.title,
    "snake_case": lambda s: re.sub(r"[\s\-]+", "_", s).lower(),
    "kebab-case": lambda s: re.sub(r"[\s_]+", "-", s).lower(),
    "camelCase": lambda s: re.sub(r"[\s_\-]+(\w)", lambda m: m.group(1).upper(), s[:1].lower() + s[1:]),
    "PascalCase": lambda s: re.sub(r"[\s_\-]+(\w)", lambda m: m.group(1).upper(), s[:1].upper() + s[1:]).lstrip("_-"),
}


@dataclass
class RenameResult:
    original: Path
    new_name: str
    error: Optional[str] = None

    @property
    def new_path(self) -> Path:
        return self.original.parent / self.new_name

    @property
    def changed(self) -> bool:
        return self.original.name != self.new_name

    @property
    def success(self) -> bool:
        return self.error is None


class PowerRenameEngine:
    """Core rename engine supporting regex, case transforms and enumeration."""

    def __init__(
        self,
        search: str = "",
        replace: str = "",
        use_regex: bool = False,
        case_sensitive: bool = False,
        case_transform: str = "None",
        apply_to_extension: bool = False,
        enumerate_files: bool = False,
        enum_start: int = 1,
        enum_padding: int = 0,
        enum_separator: str = "_",
    ):
        self.search = search
        self.replace = replace
        self.use_regex = use_regex
        self.case_sensitive = case_sensitive
        self.case_transform = case_transform
        self.apply_to_extension = apply_to_extension
        self.enumerate_files = enumerate_files
        self.enum_start = enum_start
        self.enum_padding = enum_padding
        self.enum_separator = enum_separator

    def _compile_pattern(self) -> Optional[re.Pattern]:
        if not self.search:
            return None
        flags = 0 if self.case_sensitive else re.IGNORECASE
        if self.use_regex:
            return re.compile(self.search, flags)
        return re.compile(re.escape(self.search), flags)

    def _do_replace(self, text: str, pattern: Optional[re.Pattern]) -> str:
        if pattern is None:
            return text
        return pattern.sub(self.replace, text)

    def _do_case_transform(self, text: str) -> str:
        fn = CASE_TRANSFORMS.get(self.case_transform)
        return fn(text) if fn else text

    def compute_new_name(self, path: Path, index: int = 0) -> str:
        """Compute the new filename for a single path."""
        stem, suffix = path.stem, path.suffix

        try:
            pattern = self._compile_pattern()
        except re.error:
            return path.name  # bad regex - no change

        if self.apply_to_extension:
            full = self._do_replace(path.name, pattern)
            # split for case/enum
            p2 = Path(full)
            new_stem, new_suffix = p2.stem, p2.suffix
        else:
            new_stem = self._do_replace(stem, pattern)
            new_suffix = suffix

        new_stem = self._do_case_transform(new_stem)
        if self.apply_to_extension:
            new_suffix = self._do_case_transform(new_suffix)

        if self.enumerate_files:
            num = self.enum_start + index
            fmt = f"{{:0{self.enum_padding}d}}" if self.enum_padding else "{}"
            new_stem += self.enum_separator + fmt.format(num)

        return new_stem + new_suffix

    def preview(self, paths: List[Path]) -> List[RenameResult]:
        """Return preview of renames without modifying anything."""
        results = []
        try:
            self._compile_pattern()  # validate early
        except re.error as e:
            return [RenameResult(p, p.name, f"Invalid regex: {e}") for p in paths]

        for i, path in enumerate(paths):
            new_name = self.compute_new_name(path, i)
            result = RenameResult(path, new_name)
            # Check collision
            if new_name != path.name and (path.parent / new_name).exists():
                result.error = "Target already exists"
            results.append(result)
        return results

    def apply(self, paths: List[Path], progress_cb: Optional[Callable] = None) -> List[RenameResult]:
        """Apply renames and return results."""
        results = self.preview(paths)
        for i, result in enumerate(results):
            if not result.changed or not result.success:
                continue
            try:
                result.original.rename(result.new_path)
            except OSError as e:
                result.error = str(e)
            if progress_cb:
                progress_cb(i + 1, len(results))
        return results

    def scan_directory(
        self,
        directory: str,
        recursive: bool = False,
        include_dirs: bool = False,
        glob_filter: str = "*",
    ) -> List[Path]:
        """Collect paths from a directory."""
        root = Path(directory)
        if not root.is_dir():
            return []
        fn = root.rglob if recursive else root.glob
        paths = []
        for p in sorted(fn(glob_filter)):
            if p.is_file() or (include_dirs and p.is_dir()):
                paths.append(p)
        return paths
