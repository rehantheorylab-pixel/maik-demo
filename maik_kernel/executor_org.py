"""Org-aware execution bridge (Phase H7).

Wires the Phase H layers (org chart, prompt system, model binding,
notebooks, CLI deployer) into the Executor without disturbing the existing
kernel flow. When an OrgChart is configured on the Config, each run:

    1. Selects the responsible CEO + resolves a worker node from the chart
       (manager picks the best-fit role for the problem).
    2. Builds the worker's full system prompt (resolution order + SELF block).
    3. Logs the run to the worker's public notebook (siblings/CEO visibility).
    4. Resolves the concrete model: per-node binding wins, else tier default.

With no org chart, everything degrades gracefully to the plain kernel
(existing behavior) — all old tests keep passing.
"""

import time
from typing import Any, Dict, List, Optional

from .cli_deployer import CLIDeployer
from .config import Config
from .model_binding import BindingStore, ModelCatalog
from .notebooks import Notebooks
from .org_chart import NodeLevel, OrgChart, OrgNode
from .prompt_system import PromptSystem


class OrgBridge:
    """Facade over all Phase H layers for the executor."""

    def __init__(self, config: Config, org: Optional[OrgChart] = None,
                 prompts: Optional[PromptSystem] = None,
                 bindings: Optional[BindingStore] = None,
                 notebooks: Optional[Notebooks] = None,
                 deployer: Optional[CLIDeployer] = None):
        self.config = config
        self.org = org
        self.prompts = prompts or PromptSystem(org)
        self.bindings = bindings or BindingStore()
        self.notebooks = notebooks or Notebooks(org)
        self.deployer = deployer or CLIDeployer()
        self.catalog = ModelCatalog()
        self._lock = None

    @property
    def active(self) -> bool:
        return self.org is not None

    def select_worker(self, problem_type: str, domain: str) -> Optional[OrgNode]:
        """Pick a worker node: best-fit agent by domain/role; else CEO."""
        if not self.active:
            return None
        ceo = self.config.ceo_for_domain(domain) or self.org.ceos()[0]
        # prefer an agent whose domain matches
        best: Optional[OrgNode] = None
        for node in self.org._nodes.values():
            if node.level is NodeLevel.AGENT and node.domain == domain:
                best = node
                break
        return best or ceo

    def build_system_prompt(self, node: OrgNode,
                            problem_type: str) -> str:
        return self.prompts.resolve(node)

    def resolve_model(self, node_uid: str, tier: "ModelTier") -> str:
        return self.bindings.resolve(node_uid, tier, self.catalog)

    def note_run(self, node_uid: str, run_id: str, problem: str,
                 answer: str) -> None:
        try:
            self.notebooks.write(node_uid, "public",
                                 f"run {run_id}: problem={problem[:150]!r} answer={answer[:200]!r}",
                                 author="executor")
        except Exception:
            pass  # notebook write must never break a run

    def summary(self) -> dict:
        return {
            "org_active": self.active,
            "nodes": self.org.stats() if self.org else None,
            "bindings": self.bindings.summary(),
            "notebooks": self.notebooks.summary(),
            "cli_tools": self.deployer.summary()["tools"],
            "prompts": self.prompts.summary(),
        }
