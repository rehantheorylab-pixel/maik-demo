"""Dual notebooks (Phase H4).

Every org node keeps two append-only notebooks:
- `public`  — chain-of-thought visible to siblings, its manager, and all
              ancestors (the shared-work surface).
- `hidden`  — private thoughts, readable only by the node itself and the
              CEOs in its chain of command (oversight, not surveillance:
              CEOs read hidden notes to catch contradictions and risk).

Entries are JSONL under MAIK_DATA_DIR/notebooks/{node_uid}/{kind}.jsonl.
"""

import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from .org_chart import NodeLevel, OrgChart

KINDS = ("public", "hidden")


class NotebookError(ValueError):
    pass


class Notebooks:
    def __init__(self, org: Optional[OrgChart] = None,
                 base: Optional[Path] = None):
        self.org = org
        self.base = Path(base) if base else Path(
            os.environ.get("MAIK_DATA_DIR", ".")) / "notebooks"
        self.base.mkdir(parents=True, exist_ok=True)
        self._locks: Dict[str, threading.RLock] = {}
        self._lock = threading.RLock()

    # -- core ----------------------------------------------------------
    def write(self, node_uid: str, kind: str, content: str,
              author: str = "self") -> dict:
        if kind not in KINDS:
            raise NotebookError(f"Unknown notebook kind: {kind}")
        entry = {"ts": time.time(), "author": author, "content": content}
        with self._get_lock(node_uid):
            self._append(node_uid, kind, entry)
        return entry

    def read(self, node_uid: str, kind: str,
             viewer_uid: Optional[str] = None) -> List[dict]:
        if kind not in KINDS:
            raise NotebookError(f"Unknown notebook kind: {kind}")
        if not self._may_read(node_uid, kind, viewer_uid):
            raise NotebookError(
                f"{viewer_uid} may not read the {kind} notebook of {node_uid}")
        return list(self._entries(node_uid, kind))

    def _may_read(self, target_uid: str, kind: str,
                  viewer_uid: Optional[str]) -> bool:
        if viewer_uid is None:
            return True  # system/internal reads allowed
        if viewer_uid == target_uid:
            return True
        if self.org is None:
            return kind == "public"
        tgt = self.org.node(target_uid)
        if tgt is None or self.org.node(viewer_uid) is None:
            return False
        if tgt.level is NodeLevel.CEO:
            # CEOs' hidden notebooks are private to them
            return kind == "public"
        # hidden visible to CEOs above the target
        if kind == "hidden":
            return any(a.level is NodeLevel.CEO
                       for a in self.org.ancestors(target_uid)
                       if a.uid == viewer_uid)
        return True  # public: siblings + managers + ancestors allowed

    # -- internals -----------------------------------------------------
    def _path(self, node_uid: str, kind: str) -> Path:
        d = self.base / node_uid
        d.mkdir(parents=True, exist_ok=True)
        return d / f"{kind}.jsonl"

    def _get_lock(self, node_uid: str) -> threading.RLock:
        with self._lock:
            if node_uid not in self._locks:
                self._locks[node_uid] = threading.RLock()
            return self._locks[node_uid]

    def _append(self, node_uid: str, kind: str, entry: dict) -> None:
        with open(self._path(node_uid, kind), "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _entries(self, node_uid: str, kind: str) -> List[dict]:
        p = self._path(node_uid, kind)
        if not p.exists():
            return []
        out = []
        for line in p.read_text().splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return out

    def summary(self) -> dict:
        per_node = {}
        for d in self.base.iterdir():
            if d.is_dir():
                sizes = {}
                for kind in KINDS:
                    p = d / f"{kind}.jsonl"
                    sizes[kind] = len(self._entries(d.name, kind)) if p.exists() else 0
                if any(sizes.values()):
                    per_node[d.name] = sizes
        return {"nodes_with_notes": len(per_node), "per_node": per_node}
