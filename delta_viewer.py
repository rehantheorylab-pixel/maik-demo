"""Delta-style side-by-side diff viewer.

Absorbs:
  - delta: syntax-highlighted diffs, side-by-side, line numbers
  - bat: syntax highlighting with git gutter
Improves:
  - AI diff explanation integration
"""

import difflib, os, re
from pathlib import Path


def highlight_line(line, language=None):
    """Simple ANSI syntax highlighting for diff output."""
    if line.startswith("+++") or line.startswith("---"):
        return f"\033[1;36m{line}\033[0m"  # cyan bold
    if line.startswith("@@"):
        return f"\033[35m{line}\033[0m"  # magenta
    if line.startswith("+"):
        return f"\033[32m{line}\033[0m"  # green
    if line.startswith("-"):
        return f"\033[31m{line}\033[0m"  # red
    return line


def unified_diff(file_a, file_b=None, context=3, text_a=None, text_b=None):
    """Generate syntax-highlighted unified diff (delta-style)."""
    if text_a is None:
        with open(file_a, "r", encoding="utf-8", errors="replace") as f:
            text_a = f.read()
    if text_b is None and file_b:
        with open(file_b, "r", encoding="utf-8", errors="replace") as f:
            text_b = f.read()
    elif text_b is None:
        text_b = text_a

    lines_a = text_a.splitlines()
    lines_b = text_b.splitlines()

    diff = list(difflib.unified_diff(
        lines_a, lines_b,
        fromfile=f"a/{file_a}", tofile=f"b/{file_b or file_a}",
        lineterm="", n=context
    ))
    return diff


def side_by_side_diff(file_a, file_b=None, context=3, width=None):
    """Generate side-by-side diff (delta-style)."""
    try:
        from rich.console import Console
        from rich.table import Table
        from rich.syntax import Syntax
        from rich import box
    except ImportError:
        return unified_diff(file_a, file_b, context)

    diff_lines = unified_diff(file_a, file_b, context)
    if not diff_lines:
        return []

    console = Console()
    table = Table(box=box.SIMPLE, padding=(0, 1), show_header=False, width=width)
    table.add_column("Left", style="dim", no_wrap=True)
    table.add_column("Right", style="dim", no_wrap=True)

    left_panel = []
    right_panel = []
    in_header = True

    for line in diff_lines:
        if in_header:
            if line.startswith("@@"):
                in_header = False
            continue

        if line.startswith("-"):
            left_panel.append(f"\033[31m{line}\033[0m")
            right_panel.append("")
        elif line.startswith("+"):
            left_panel.append("")
            right_panel.append(f"\033[32m{line}\033[0m")
        else:
            left_panel.append(line[1:] if line.startswith(" ") else line)
            right_panel.append(line[1:] if line.startswith(" ") else line)

    # Balance
    max_len = max(len(left_panel), len(right_panel))
    left_panel += [""] * (max_len - len(left_panel))
    right_panel += [""] * (max_len - len(right_panel))

    return (left_panel, right_panel)


def diff_stats(file_a, file_b=None):
    """Return diff statistics: insertions, deletions, files changed."""
    diff = unified_diff(file_a, file_b)
    insertions = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
    deletions = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
    return {
        "insertions": insertions,
        "deletions": deletions,
        "total": insertions + deletions,
        "files_changed": 1,
        "chunks": sum(1 for l in diff if l.startswith("@@")),
    }


def git_diff(repo_path=".", staged=False):
    """Get git diff output."""
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--cached")
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_path, timeout=30)
        return result.stdout
    except Exception as e:
        return f"Error: {e}"


# Import subprocess here since git_diff uses it
import subprocess


delta_viewer = type("DeltaViewer", (), {
    "diff": unified_diff,
    "side_by_side": side_by_side_diff,
    "stats": diff_stats,
    "git_diff": git_diff,
    "highlight": highlight_line,
})()
