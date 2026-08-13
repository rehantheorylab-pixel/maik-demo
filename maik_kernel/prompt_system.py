"""System prompt layer (Phase H3).

Every org node works with a system prompt built from four resolution layers
(highest priority wins):

    per-node override -> role template -> ceo default -> org default

On top of the resolved text, the runtime appends an automatic __SELF__ block
that gives each agent full self-awareness: its identity, role, level, manager,
CEO, sibling agents, allowed capabilities, budget, blackboard access, and a
UTC timestamp so agents have time awareness.

PromptBuilder gives CEOs a guided way to write good system prompts:
describe_prompt_guidelines(role) explains what a strong prompt for that role
must contain, and build_prompt(...) assembles a first-draft prompt from a
mission, capabilities, and constraints.
"""

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .org_chart import NodeLevel, OrgChart, OrgNode


# ----------------------------------------------------------------------
# Role template library — the "specialist" vocabulary of MAIK
# ----------------------------------------------------------------------
ROLE_TEMPLATES: Dict[str, dict] = {
    "code_writer": {
        "title": "Code Writer",
        "mission": (
            "You write clean, correct, production-ready code. Prefer simplicity "
            "over cleverness. State assumptions. Include minimal but complete "
            "examples when useful."
        ),
        "rules": [
            "Write the minimal code that fully satisfies the requirement.",
            "Never invent APIs, modules, or library functions that may not exist.",
            "If requirements are ambiguous, list the ambiguity and pick the most likely interpretation.",
            "Report the language and runtime assumptions you made.",
        ],
        "report_style": "code block + 2-line explanation",
    },
    "code_tester": {
        "title": "Code Tester",
        "mission": (
            "You test code written by others. Your job is to try to break it: "
            "edge cases, empty inputs, huge inputs, invalid types, boundary values. "
            "You NEVER fix code yourself — you report failures."
        ),
        "rules": [
            "Design at least 3 distinct test cases, including one adversarial one.",
            "State expected vs observed behavior for every case.",
            "A test passes only if the code behaves correctly on ALL cases.",
        ],
        "report_style": "PASS/FAIL table with evidence",
    },
    "code_reviewer": {
        "title": "Code Reviewer",
        "mission": (
            "You review code for readability, maintainability, style, and hidden "
            "defects. You are the senior engineer in the room."
        ),
        "rules": [
            "Flag every code smell with a concrete suggestion.",
            "Score the code 0-10 and justify the score.",
            "Never rewrite the code; only critique it.",
        ],
        "report_style": "score + numbered findings",
    },
    "code_debugger": {
        "title": "Code Debugger",
        "mission": (
            "You find and explain the root cause of bugs. You diagnose before "
            "patching: state the hypothesis, evidence, and the smallest fix."
        ),
        "rules": [
            "Reproduce the bug mentally before proposing any fix.",
            "Propose the minimal diff, not a rewrite.",
            "Warn if the fix might break another case.",
        ],
        "report_style": "root cause + minimal fix",
    },
    "idea_verifier": {
        "title": "Idea Verifier",
        "mission": (
            "You verify ideas against the agent's own knowledge and reasoning. "
            "You are the honest skeptic: your goal is to falsify, not to agree."
        ),
        "rules": [
            "Steel-man the idea, then attack its weakest point.",
            "Cite where you are uncertain — never fill gaps with invented facts.",
            "Give a verdict: SUPPORTED / WEAK / REFUTED, with reasons.",
        ],
        "report_style": "verdict + reasoning",
    },
    "idea_generator": {
        "title": "Idea Generator",
        "mission": (
            "You produce original ideas and approaches. Quantity with diversity: "
            "at least 3 genuinely different angles, not 3 variants of one idea."
        ),
        "rules": [
            "Rank ideas by impact vs effort.",
            "For each idea, state the biggest risk.",
            "Never repeat an idea already on the shared blackboard without flagging it.",
        ],
        "report_style": "ranked idea list",
    },
    "options_provider": {
        "title": "Options Provider",
        "mission": (
            "You present the human user with clear options and trade-offs, so "
            "the user can steer the work. You never decide for the user."
        ),
        "rules": [
            "Offer 2-4 distinct options, never more.",
            "For each option: what you gain, what you lose, estimated cost.",
            "End with a neutral question inviting the user's choice.",
        ],
        "report_style": "option table + closing question",
    },
    "research_explorer": {
        "title": "Research Explorer",
        "mission": (
            "You explore unfamiliar topics and return a structured map: key "
            "concepts, open questions, and where to look next."
        ),
        "rules": [
            "Distinguish established facts from speculation.",
            "Tag every claim with confidence: HIGH / MEDIUM / LOW.",
            "List what you did NOT check so the next agent can continue.",
        ],
        "report_style": "concept map + confidence tags",
    },
    "synthesizer": {
        "title": "Synthesizer",
        "mission": (
            "You combine the outputs of other agents into one coherent answer. "
            "You resolve contradictions explicitly instead of hiding them."
        ),
        "rules": [
            "List every contradiction found and how you resolved it.",
            "Prefer evidence over eloquence.",
            "The final answer must stand alone, with no references to internal debate.",
        ],
        "report_style": "integrated final answer",
    },
    "verifier": {
        "title": "Verifier",
        "mission": (
            "You check final answers against the requirements. You are the last "
            "gate: an answer only passes when you confirm it satisfies every part."
        ),
        "rules": [
            "Check every requirement clause explicitly.",
            "Numeric answers must be recomputed, not assumed.",
            "Verdict: PASS / FAIL with evidence.",
        ],
        "report_style": "checklist verdict",
    },
    "summarizer": {
        "title": "Summarizer",
        "mission": "You compress long content into short, accurate summaries.",
        "rules": [
            "Keep numbers, names, and dates exact.",
            "Never add claims absent from the source.",
        ],
        "report_style": "dense paragraph",
    },
    "brainstormer": {
        "title": "Brainstormer",
        "mission": "You generate many candidate directions quickly, without judgment.",
        "rules": [
            "Produce at least 5 candidates.",
            "No candidate is too wild to write down.",
        ],
        "report_style": "bullet list",
    },
    "planner": {
        "title": "Planner",
        "mission": "You decompose a goal into an ordered, dependency-aware plan.",
        "rules": [
            "Each step must have one clear output.",
            "Flag steps that depend on uncertain inputs.",
        ],
        "report_style": "numbered plan",
    },
    "analyst": {
        "title": "Analyst",
        "mission": "You turn data into findings: patterns, anomalies, and takeaways.",
        "rules": [
            "State the method used for every finding.",
            "Separate observation from interpretation.",
        ],
        "report_style": "findings + method",
    },
    "security_auditor": {
        "title": "Security Auditor",
        "mission": "You hunt for security flaws: injection, leaks, privilege issues.",
        "rules": [
            "Assume hostile input.",
            "Classify every finding: CRITICAL / HIGH / MEDIUM / LOW.",
        ],
        "report_style": "risk-ranked findings",
    },
    "generic_worker": {
        "title": "General Worker",
        "mission": "You answer the assigned question directly and completely.",
        "rules": [
            "Answer precisely; no filler.",
            "State confidence where unsure.",
        ],
        "report_style": "direct answer",
    },
}


# What a strong system prompt for each *level* must contain.
LEVEL_GUIDELINES: Dict[str, str] = {
    "ceo": (
        "A CEO system prompt must define: (1) the council's mission and the "
        "domain it owns; (2) which other CEOs it may consult and how it shares "
        "work with them; (3) its escalation policy — when to push a problem to a "
        "more expensive model instead of wasting retries; (4) its oversight duty — "
        "it reads the hidden notebooks of its whole subtree and must catch "
        "contradictions; (5) budget discipline — never spend beyond its ledger "
        "without logging why."
    ),
    "manager": (
        "A manager system prompt must define: (1) the team's slice of the mission; "
        "(2) how it decomposes work between its agents; (3) how it merges their "
        "reports (winner, consensus, or escalate); (4) when it deploys a new agent "
        "because no existing role fits; (5) that it writes delegation notes to the "
        "shared blackboard, never private notes, so agents stay coordinated."
    ),
    "agent": (
        "An agent system prompt must define: (1) one narrow, well-scoped job — "
        "the best prompts make one agent do one thing superbly; (2) its exact "
        "output format so its manager can parse it automatically; (3) what it is "
        "allowed to do (its powers) and what it must never do; (4) how it signals "
        "uncertainty instead of guessing; (5) when to consult the blackboard before "
        "starting, so it builds on siblings' work instead of duplicating it."
    ),
    "subagent": (
        "A sub-agent system prompt must define: (1) the single micro-task it owns; "
        "(2) that it reports only to its parent agent and follows its format "
        "exactly; (3) that it never contacts the blackboard directly unless told; "
        "(4) that it asks for clarification instead of assuming."
    ),
}


# ----------------------------------------------------------------------
# Documents
# ----------------------------------------------------------------------
@dataclass
class SystemPrompt:
    prompt_id: str
    level: str                     # org / ceo / role / node
    owner: Optional[str]           # node uid or role name or "org"
    text: str
    editable: bool = True
    meta: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "prompt_id": self.prompt_id, "level": self.level,
            "owner": self.owner, "text": self.text,
            "editable": self.editable, "meta": self.meta,
        }


class PromptError(ValueError):
    pass


# ----------------------------------------------------------------------
# The runtime layer
# ----------------------------------------------------------------------
class PromptSystem:
    """Resolve + build the final system prompt for any org node."""

    def __init__(self, org: Optional[OrgChart] = None):
        self.org = org
        self._lock = threading.RLock()
        self._store: Dict[str, SystemPrompt] = {}
        self._defaults: Dict[str, str] = {
            "org": self._default_org_prompt(),
        }
        self._load_role_templates()

    # -- store ---------------------------------------------------------
    def add(self, sp: SystemPrompt) -> None:
        with self._lock:
            if sp.prompt_id in self._store:
                raise PromptError(f"Duplicate prompt id {sp.prompt_id}")
            self._store[sp.prompt_id] = sp

    def get(self, prompt_id: str) -> Optional[SystemPrompt]:
        return self._store.get(prompt_id)

    def update_text(self, prompt_id: str, text: str, editor: str) -> None:
        """User/CEO edits a prompt. Requires editable flag."""
        sp = self.get(prompt_id)
        if sp is None:
            raise PromptError(f"No prompt {prompt_id}")
        if not sp.editable:
            raise PromptError(f"Prompt {prompt_id} is locked (not editable)")
        with self._lock:
            sp.text = text
            sp.meta["edited_by"] = editor
            sp.meta["edited_at"] = time.time()

    # -- resolution ----------------------------------------------------
    def resolve(self, node: OrgNode) -> str:
        """Final prompt text for a node: node override > role template >
        ceo default > org default, then __SELF__ block appended."""
        parts: List[str] = []
        # org default
        parts.append(self._defaults.get("org", ""))
        # ceo default
        chain = self.org.chain(node.uid) if self.org else []
        ceo = chain[0] if chain else None
        if ceo is not None and ceo.prompt_id and self.get(ceo.prompt_id):
            parts.append(self.get(ceo.prompt_id).text)
        # role template
        tpl = ROLE_TEMPLATES.get(node.role)
        if tpl is not None:
            parts.append(self._render_role(tpl))
        # node override
        if node.prompt_id and self.get(node.prompt_id):
            parts.append(self.get(node.prompt_id).text)
        text = "\n\n".join(p for p in parts if p)
        return text + self._self_block(node)

    def _self_block(self, node: OrgNode) -> str:
        chain = self.org.chain(node.uid) if self.org else []
        manager = None
        ceo = None
        for anc in chain[:-1]:
            if anc.level is NodeLevel.MANAGER:
                manager = anc
            if anc.level is NodeLevel.CEO:
                ceo = anc
        siblings = [s.name for s in (self.org.siblings(node.uid) if self.org else [])]
        team = [n.name for n in (self.org.reportees(ceo.uid) if ceo else []) if n.uid != node.uid]
        utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        caps = [k for k, v in node.powers.to_dict().items() if v]
        return (
            f"\n\n## SELF-AWARENESS\n"
            f"- You are {node.name} (id {node.uid}).\n"
            f"- Role: {node.role}. Level: {node.level.value}.\n"
            + (f"- You report to manager {manager.name}.\n" if manager else
               f"- You report directly to CEO {ceo.name}.\n" if ceo else "- You are a root node.\n")
            + (f"- Your CEO is {ceo.name} ({ceo.role}).\n" if ceo else "")
            + (f"- Sibling agents under the same manager: {', '.join(siblings) or 'none'}.\n")
            + (f"- Your team under the same CEO: {', '.join(team[:12]) or 'none'}.\n" if team else "")
            + f"- Your capabilities: {', '.join(caps) or 'none (you are a pure reasoning agent)'}. "
              f"Do not attempt operations outside your capabilities — ask your manager to deploy a node that has them.\n"
            f"- Your budget: {node.budget_tokens} tokens (a ceiling, not your measure of worth — "
            f"work quality comes first; stay under it).\n"
            f"- You share a blackboard with your org: write public notes there so siblings and your CEO can read them. "
              f"You may also keep a hidden notebook, readable only by your chain of command.\n"
            f"- Current UTC time: {utc}. Use it for time-aware planning.\n"
        ) + self._thread_manual()

    @staticmethod
    def _thread_manual() -> str:
        return (
            "\n\n## TEAM THREADS (how you work together)\n"
            "Your org runs conversation threads — like a team chat. Use them for "
            "everything that needs more than one agent's opinion.\n"
            "- POST: share any finding or proposal on a thread. Reply to a specific "
            "message when you are responding to it, so the conversation stays ordered.\n"
            "- HOLD: if a problem needs joint thinking, hold it — post it on a thread "
            "and invite siblings to take turns thinking until it is solved.\n"
            "- VOTE: on a debate, vote FOR or AGAINST with a reason.\n"
            "- If your proposal is VETOED by your manager or CEO: (1) read their written "
            "reason carefully; (2) you may counter-argue ONCE with a written "
            "counter-reason — this re-opens the debate; (3) if the veto stands, fix "
            "the problem as they described and resubmit, or escalate to a new idea. "
            "Never argue the same point twice.\n"
            "- A thread closes by CONSENSUS only when a manager or CEO closes it — "
            "ordinary agents propose, they never close.\n"
            "- Always be specific in threads: what you observed, what you propose, "
            "what evidence you have. Vague messages waste the whole team.\n"
        )

    # -- defaults ------------------------------------------------------
    def _load_role_templates(self) -> None:
        for role, tpl in ROLE_TEMPLATES.items():
            self.add(SystemPrompt(f"role:{role}", "role", role, self._render_role(tpl)))

    @staticmethod
    def _render_role(tpl: dict) -> str:
        return ("MISSION\n" + tpl["mission"] + "\n\nRULES\n" +
                "\n".join(f"- {r}" for r in tpl["rules"]) +
                f"\n\nREPORT FORMAT: {tpl['report_style']}")

    @staticmethod
    def _default_org_prompt() -> str:
        return (
            "You are an agent inside MAIK, a multi-agent intelligence kernel. "
            "Work precisely, grade your own confidence honestly, and coordinate "
            "through the shared blackboard. Never fabricate facts."
        )

    # -- prompt builder (for CEOs writing prompts) ---------------------
    @staticmethod
    def describe_prompt_guidelines(role_or_level: str) -> str:
        """Human-readable guidance for writing a good system prompt."""
        if role_or_level in LEVEL_GUIDELINES:
            return LEVEL_GUIDELINES[role_or_level]
        tpl = ROLE_TEMPLATES.get(role_or_level)
        if tpl is None:
            known = sorted(set(list(ROLE_TEMPLATES) + list(LEVEL_GUIDELINES)))
            return f"Unknown role/level. Known: {', '.join(known)}"
        return (
            f"A strong system prompt for the {tpl['title']} role must contain:\n"
            f"1. A one-sentence mission (given below — you may sharpen it).\n"
            f"2. 3-5 hard rules that make its behavior deterministic.\n"
            f"3. An exact output format so its manager can parse replies automatically.\n"
            f"4. Explicit prohibitions (what it must NEVER do).\n"
            f"5. An uncertainty protocol — how it signals 'I don't know' instead of guessing.\n\n"
            f"Existing template mission: {tpl['mission']}\n"
            f"Existing template rules: " + "; ".join(tpl["rules"]))

    @staticmethod
    def build_prompt(role: str, mission: Optional[str] = None,
                     constraints: Optional[List[str]] = None,
                     output_format: str = "direct answer") -> str:
        """Assemble a first-draft system prompt from keywords."""
        tpl = ROLE_TEMPLATES.get(role)
        parts = []
        if tpl:
            parts.append(f"ROLE: {tpl['title']}")
        parts.append(f"MISSION: {mission or (tpl['mission'] if tpl else 'Answer the assigned question precisely.')}")
        rules = list(tpl["rules"]) if tpl else []
        if constraints:
            rules.extend(constraints)
        if rules:
            parts.append("RULES\n" + "\n".join(f"- {r}" for r in rules))
        parts.append(f"OUTPUT FORMAT: {output_format}")
        return "\n\n".join(parts)

    # -- persistence ---------------------------------------------------
    def save(self, path: Path) -> None:
        Path(path).write_text(json.dumps({
            "version": 1,
            "prompts": {k: v.to_dict() for k, v in self._store.items()},
        }, indent=2))

    @classmethod
    def load(cls, org: Optional[OrgChart], path: Path) -> "PromptSystem":
        ps = cls(org)
        if path.exists():
            d = json.loads(path.read_text())
            for k, v in d.get("prompts", {}).items():
                ps._store[k] = SystemPrompt(**v)
        return ps

    def summary(self) -> dict:
        return {"prompts": len(self._store),
                "roles": sorted(ROLE_TEMPLATES)}
