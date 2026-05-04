"""Small local filesystem tool backend used when Deep Agents is unavailable."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class FileSystemTools:
    root: Path
    allow_traversal: bool = False

    def __post_init__(self) -> None:
        self.root = self.root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, path: str | Path) -> Path:
        candidate = (self.root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if not self.allow_traversal and candidate != self.root and self.root not in candidate.parents:
            raise PermissionError(f"path is outside workspace: {path}")
        return candidate

    def ls(self, path: str = ".") -> str:
        try:
            target = self.resolve(path)
            if not target.exists():
                raise FileNotFoundError(target)
            if target.is_file():
                return target.name
            return "\n".join(sorted(item.name + ("/" if item.is_dir() else "") for item in target.iterdir()))
        except Exception as exc:
            return _tool_error(exc)

    def read_file(self, path: str) -> str:
        try:
            return self.resolve(path).read_text(encoding="utf-8")
        except Exception as exc:
            return _tool_error(exc)

    def write_file(self, path: str, content: str) -> str:
        try:
            target = self.resolve(path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            return f"wrote {target.relative_to(self.root)}"
        except Exception as exc:
            return _tool_error(exc)

    def edit_file(self, path: str, old: str, new: str, *, count: int = 1) -> str:
        try:
            target = self.resolve(path)
            text = target.read_text(encoding="utf-8")
            if old not in text:
                raise ValueError("old text not found")
            target.write_text(text.replace(old, new, count), encoding="utf-8")
            return f"edited {target.relative_to(self.root)}"
        except Exception as exc:
            return _tool_error(exc)

    def glob(self, pattern: str, path: str = ".") -> str:
        try:
            target = self.resolve(path)
            matches = sorted(p.relative_to(self.root).as_posix() if self.root in p.parents else str(p) for p in target.glob(pattern))
            return "\n".join(matches)
        except Exception as exc:
            return _tool_error(exc)

    def grep(self, pattern: str, glob: str = "**/*", path: str = ".") -> str:
        try:
            target = self.resolve(path)
            lines: list[str] = []
            for p in sorted(target.rglob("*")):
                rel = p.relative_to(self.root).as_posix() if self.root in p.parents else str(p)
                if not p.is_file() or not fnmatch.fnmatch(rel, glob) and not fnmatch.fnmatch(p.name, glob):
                    continue
                try:
                    for number, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
                        if pattern in line:
                            lines.append(f"{rel}:{number}:{line}")
                except UnicodeDecodeError:
                    continue
            return "\n".join(lines)
        except Exception as exc:
            return _tool_error(exc)


def _tool_error(exc: Exception) -> str:
    return f"Tool error ({type(exc).__name__}): {exc}"
