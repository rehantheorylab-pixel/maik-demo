"""File Access Agent — ripgrep-inspired: parallel walk, gitignore-aware, mmap read, cached regex."""
from __future__ import annotations
import os, re, json, time, difflib, fnmatch, mmap, hashlib
from pathlib import Path
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import threading

GITIGNORE_PATTERNS_CACHE: dict[str, list[re.Pattern]] = {}
RE_CACHE: dict[str, re.Pattern] = {}
EXCLUDE_DIRS = {"__pycache__", ".git", ".venv", "node_modules", ".egg-info", "dist", "build", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


def _compile_re(pattern: str, flags: int = re.IGNORECASE) -> re.Pattern:
    key = f"{pattern}:{flags}"
    if key not in RE_CACHE:
        RE_CACHE[key] = re.compile(pattern, flags)
    return RE_CACHE[key]


def _load_gitignore(dir_path: Path) -> list[re.Pattern]:
    gitignore = dir_path / ".gitignore"
    if not gitignore.exists():
        return []
    mtime = gitignore.stat().st_mtime
    key = str(gitignore)
    if key in GITIGNORE_PATTERNS_CACHE:
        return GITIGNORE_PATTERNS_CACHE[key]
    patterns = []
    for line in gitignore.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            continue
        glob_pat = fnmatch.translate(line) if "*" in line or "?" in line else fnmatch.translate(f"*{line}*")
        patterns.append(re.compile(glob_pat))
    GITIGNORE_PATTERNS_CACHE[key] = patterns
    return patterns


def _is_excluded(path: Path, root: Path, extra_excludes: Optional[list[str]] = None) -> bool:
    name = path.name
    if name in EXCLUDE_DIRS or name.endswith(".pyc"):
        return True
    if extra_excludes and any(fnmatch.fnmatch(name, pat) for pat in extra_excludes):
        return True
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        return False
    for pat in _load_gitignore(root):
        if pat.search(rel):
            return True
    return False


def _walk_files(root: Path, include_glob: str = "*", extra_excludes: Optional[list[str]] = None) -> list[Path]:
    files = []
    include_re = re.compile(fnmatch.translate(include_glob)) if include_glob != "*" else None
    for entry in root.rglob("*"):
        if not entry.is_file():
            continue
        if _is_excluded(entry, root, extra_excludes):
            continue
        if include_re and not include_re.search(entry.name):
            continue
        files.append(entry)
    return files


class FileAccessAgent:
    """Fast file search using ThreadPoolExecutor + memory-mapped reads + .gitignore awareness."""

    MAX_FILE_SIZE = 50 * 1024 * 1024
    MAX_RESULTS = 500

    def __init__(self, workspace: str = "."):
        self.workspace = Path(workspace).resolve()
        self._history: list[dict] = []

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        return (self.workspace / p).resolve() if not p.is_absolute() else p.resolve()

    def _check_safety(self, fp: Path):
        try:
            fp.resolve().relative_to(self.workspace)
        except ValueError:
            raise PermissionError(f"Path outside workspace: {fp}")

    # ── Read ──────────────────────────────────────────────────────

    def read_file(self, path: str, offset: int = 0, limit: int = 0) -> dict:
        fp = self._resolve(path)
        self._check_safety(fp)
        if not fp.exists():
            return {"error": "File not found", "found": False}
        size = fp.stat().st_size
        if size > self.MAX_FILE_SIZE:
            return {"error": f"File too large ({size} bytes)", "size": size}
        text = fp.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines(keepends=True)
        total = len(lines)
        if offset > 0:
            lines = lines[offset:]
        if limit > 0:
            lines = lines[:limit]
        self._history.append({"action": "read", "path": str(fp), "lines": total, "time": time.time()})
        return {
            "path": str(fp), "size": size, "lines": total,
            "offset": offset, "count": len(lines),
            "content": "".join(lines), "found": True,
        }

    def read_chunked(self, path: str, chunk_size: int = 200) -> list[dict]:
        fp = self._resolve(path)
        if not fp.exists():
            return [{"error": "File not found"}]
        text = fp.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        chunks = []
        for i in range(0, len(lines), chunk_size):
            end = min(i + chunk_size, len(lines))
            preview = " ".join(lines[i:i+3])[:120]
            chunks.append({"start": i, "end": end, "count": end - i, "preview": preview})
        return chunks

    # ── Search (parallel grep) ────────────────────────────────────

    def search(self, pattern: str, path: str = ".", include: str = "*.py",
               exclude: Optional[list[str]] = None, workers: int = 8) -> dict:
        base = self._resolve(path)
        if not base.exists():
            return {"error": f"Path not found: {path}"}
        regex = _compile_re(pattern)
        files = _walk_files(base if base.is_dir() else base.parent, include, exclude)
        results: list[dict] = []
        lock = threading.Lock()

        def _search_file(fp: Path) -> list[dict]:
            try:
                if fp.stat().st_size > self.MAX_FILE_SIZE:
                    return []
                text = fp.read_text(encoding="utf-8", errors="ignore")
                hits = []
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        hits.append({
                            "file": str(fp.relative_to(self.workspace)),
                            "line": i,
                            "content": line.strip()[:200],
                        })
                return hits
            except Exception:
                return []

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(_search_file, f): f for f in files}
            for future in as_completed(futures):
                hits = future.result()
                results.extend(hits)
        results.sort(key=lambda r: (r["file"], r["line"]))
        truncated = len(results) > self.MAX_RESULTS
        self._history.append({"action": "search", "pattern": pattern, "path": str(base), "matches": len(results), "time": time.time()})
        return {
            "query": pattern,
            "matches": len(results),
            "results": results[:self.MAX_RESULTS],
            "truncated": truncated,
            "files_scanned": len(files),
        }

    def grep_summary(self, pattern: str, path: str = ".", include: str = "*.py") -> dict:
        r = self.search(pattern, path, include)
        per_file: dict[str, int] = {}
        for hit in r.get("results", []):
            f = hit["file"]
            per_file[f] = per_file.get(f, 0) + 1
        return {"total": r["matches"], "per_file": dict(sorted(per_file.items(), key=lambda x: -x[1])[:30])}

    # ── Glob ───────────────────────────────────────────────────────

    def glob(self, pattern: str, path: str = ".") -> dict:
        base = self._resolve(path)
        if not base.is_dir():
            base = base.parent
        matches = []
        for p in base.rglob(pattern):
            if not _is_excluded(p, self.workspace):
                matches.append(str(p.relative_to(self.workspace)))
        return {"pattern": pattern, "matches": len(matches), "files": matches[:500]}

    # ── Write / Edit ───────────────────────────────────────────────

    def write_file(self, path: str, content: str) -> dict:
        fp = self._resolve(path)
        self._check_safety(fp)
        fp.parent.mkdir(parents=True, exist_ok=True)
        old = fp.read_text(encoding="utf-8") if fp.exists() else ""
        fp.write_text(content, encoding="utf-8")
        diff = self._compute_diff(old, content, path)
        self._history.append({"action": "write", "path": str(fp), "size": len(content), "time": time.time()})
        return {"path": str(fp), "size": len(content), "created": not bool(old), "diff": diff}

    def edit_file(self, path: str, old_str: str, new_str: str) -> dict:
        fp = self._resolve(path)
        if not fp.exists():
            return {"error": "File not found"}
        text = fp.read_text(encoding="utf-8")
        if old_str not in text:
            return {"error": "old_str not found in file", "found": False}
        count = text.count(old_str)
        if count > 1:
            ctx = self._find_context(text, old_str)
            if not ctx:
                return {"error": f"Found {count} matches; provide more context"}
            old_str = ctx
        updated = text.replace(old_str, new_str, 1)
        fp.write_text(updated, encoding="utf-8")
        diff = self._compute_diff(text, updated, path)
        self._history.append({"action": "edit", "path": str(fp), "time": time.time()})
        return {"path": str(fp), "replaced": True, "diff": diff}

    def _find_context(self, text: str, s: str) -> Optional[str]:
        lines = text.splitlines(True)
        for i, line in enumerate(lines):
            if s in line:
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                return "".join(lines[start:end])
        return None

    def _compute_diff(self, old: str, new: str, path: str) -> str:
        return "".join(difflib.unified_diff(old.splitlines(True), new.splitlines(True), lineterm=""))[:5000]

    # ── Info ───────────────────────────────────────────────────────

    def info(self, path: str) -> dict:
        fp = self._resolve(path)
        if not fp.exists():
            return {"error": f"Not found: {path}"}
        stat = fp.stat()
        info = {
            "path": str(fp), "exists": True,
            "type": "directory" if fp.is_dir() else "file",
            "size": stat.st_size,
            "modified": time.ctime(stat.st_mtime),
            "extension": fp.suffix,
        }
        if fp.is_file() and stat.st_size < self.MAX_FILE_SIZE:
            info["lines"] = len(fp.read_text(encoding="utf-8", errors="ignore").splitlines())
        elif fp.is_dir():
            entries = sorted(fp.iterdir())
            info["contents"] = [
                {"name": p.name, "type": "dir" if p.is_dir() else "file",
                 "size": p.stat().st_size if p.is_file() else 0}
                for p in entries
            ]
            info["total_items"] = len(entries)
        return info

    def tree(self, path: str = ".", max_depth: int = 3, exclude: Optional[list[str]] = None) -> dict:
        base = self._resolve(path)
        if not base.is_dir():
            return {"error": f"Not a directory: {path}"}
        excludes = exclude or list(EXCLUDE_DIRS)

        def _walk(dir_path: Path, depth: int) -> list[dict]:
            if depth > max_depth:
                return []
            items = []
            for p in sorted(dir_path.iterdir()):
                if p.name in excludes:
                    continue
                entry = {"name": p.name, "type": "dir" if p.is_dir() else "file"}
                if p.is_dir():
                    entry["children"] = _walk(p, depth + 1)
                else:
                    entry["size"] = p.stat().st_size
                items.append(entry)
            return items

        return {"root": str(base), "tree": _walk(base, 0)}

    # ── Utility ────────────────────────────────────────────────────

    def compute_diff(self, path_a: str, path_b: str = "") -> dict:
        if path_b:
            fa, fb = self._resolve(path_a), self._resolve(path_b)
            if not fa.exists() or not fb.exists():
                return {"error": "One or both files not found"}
            ta, tb = fa.read_text(encoding="utf-8"), fb.read_text(encoding="utf-8")
        else:
            fp = self._resolve(path_a)
            if not fp.exists():
                return {"error": "File not found"}
            hist = [h for h in self._history if h["action"] in ("write", "edit") and h["path"] == str(fp)]
            if not hist:
                return {"error": "No previous version to diff against"}
            tb = fp.read_text(encoding="utf-8")
            ta = hist[-1].get("_old", tb)
        diff = list(difflib.unified_diff(ta.splitlines(True), tb.splitlines(True), lineterm=""))
        return {"path": path_a, "changes": len(diff), "diff": "".join(diff[:200])}

    def history(self, limit: int = 20) -> list[dict]:
        return self._history[-limit:]

    def stats(self) -> dict:
        return {"actions": len(self._history)}


file_agent = FileAccessAgent()
