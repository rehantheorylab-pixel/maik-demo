"""MAIK CLI (Phase G).

Single entry point: ``maik_kernel.cli`` exposes the commands

    python -m maik_kernel.cli solve "Calculate 17 x 23"
    python -m maik_kernel.cli bench [--n N] [--stub]
    python -m maik_kernel.cli status
    python -m maik_kernel.cli init
    python -m maik_kernel.cli flywheel [--revolutions N]

`init` writes an encrypted .env from the template; `solve` runs the full
tiered cascade; `bench` runs TruthBench with correctness judging; `status`
shows the learning/memory/pattern health; `flywheel` closes the loop.
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from tabulate import tabulate

from .bench_truth import TruthBench
from .config import Config
from .flywheel import Flywheel
from .org_chart import OrgChart
from .model_binding import BindingStore
from .prompt_system import PromptSystem
from .notebooks import Notebooks
from .cli_deployer import CLIDeployer
from .threads import ThreadHub
from .learn import LearningSystem
from .memory import MemorySystem
from .pattern_lib import PatternLibrary
from .secrets import ensure_env, get_secret, secrets_audit
from .executor import Executor


def cmd_init(_args: argparse.Namespace) -> int:
    """Create an encrypted .env from the template (first-run setup)."""
    p = ensure_env()
    flags = secrets_audit()
    print(f"Encrypted .env ready at {p}")
    if flags:
        print("Warnings:")
        for f in flags:
            print("  -", f)
    else:
        print("No placeholder values detected in .env.")
    return 0


def cmd_solve(args: argparse.Namespace) -> int:
    """Run the tiered cascade on one problem and print the result."""
    cfg = Config()
    lib = PatternLibrary()
    ex = Executor(cfg, pattern_lib=lib)
    try:
        res = ex.execute(args.problem, max_tokens=args.max_tokens)
    except RuntimeError as e:
        print(f"ERROR: all providers failed — {e}")
        print("Hint: run `python -m maik_kernel.cli init` and place at least "
              "one free or paid key in the encrypted .env, or retry with "
              "MAIK_STUB=1 for offline mode.")
        return 1
    print("MAIK ANSWER")
    print("=" * 40)
    print(res.answer)
    print("=" * 40)
    print(json.dumps({k: v for k, v in res.to_dict().items()
                      if k not in ("solution",)}, indent=1))
    return 0


def cmd_bench(args: argparse.Namespace) -> int:
    """Run the ground-truth benchmark with correctness judging."""
    stub = bool(args.stub) or os.environ.get("MAIK_STUB", "").strip() == "1"
    if stub:
        os.environ["MAIK_STUB"] = "1"
    cfg = Config()
    lib = PatternLibrary()
    mem = MemorySystem()
    learn = LearningSystem()
    bench = TruthBench(config=cfg, pattern_lib=lib, memory=mem, learn=learn)
    problems = (bench.DEFAULTS[: args.n]
                if args.n and 0 < args.n < len(bench.DEFAULTS)
                else bench.DEFAULTS)
    ex = Executor(cfg, pattern_lib=lib)
    rows = bench.run(ex)
    summary = bench.summary(rows)
    print(f"Mode: {'STUB (offline)' if stub else 'LIVE'} | "
          f"{summary['total']} problems")
    print(tabulate(
        [(r.pid, "PASS" if r.correct else "FAIL", r.tier,
          f"${r.cost_usd:.5f}", f"{r.duration_s:.2f}s",
          (r.answer[:40] + "...") if r.answer else "(none)")
         for r in rows],
        headers=["id", "result", "tier", "cost", "time", "answer"],
        tablefmt="simple"))
    print("\nSummary")
    print(json.dumps(summary, indent=1))
    print("\nLearning state")
    print(json.dumps(learn.status(), indent=1))
    return 0 if summary["accuracy"] > 0 else 1


# ----------------------------------------------------------------------
# Phase H — org-chart CLI family (`maik org`)
# ----------------------------------------------------------------------

def _org_data_dir() -> Path:
    return Path(os.environ.get("MAIK_DATA_DIR",
                               str(Path.home() / ".maik")))


def _org_data_path() -> Path:
    return _org_data_dir() / "org.json"


def _lookup_node(org: OrgChart, name: str) -> Optional[object]:
    """Resolve a node by uid OR by (possibly multi-word) name."""
    n = org.node(name)
    if n is not None:
        return n
    return org.find(name)


def _org_seed_path() -> Path:
    return _org_data_dir() / "org_seed.json"


def _load_org_chart() -> OrgChart:
    p = _org_data_path()
    if p.exists():
        return OrgChart.from_json(p.read_text())
    # Stable CEO uids across restarts: reuse the persisted seed, or mint and
    # persist new ones so CLI commands can reference CEOs by name later.
    sp = _org_seed_path()
    seed: dict = {}
    if sp.exists():
        seed = json.loads(sp.read_text())
    from .org_chart import OrgNode, NodeLevel, Powers
    from .config import _default_ceos
    ceos = []
    for c in _default_ceos():
        uid = seed.get(c.name)
        if uid is None:
            uid = OrgChart._new_uid()
            seed[c.name] = uid
        ceos.append(OrgNode(uid, c.name, role=c.domain, domain=c.domain,
                            level=NodeLevel.CEO, model_binding=None,
                            budget_tokens=c.budget_tokens, powers=Powers.ceo()))
    org = OrgChart("maik-org", ceos=ceos)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(seed))
    return org


def _save_org_chart(org: OrgChart) -> None:
    p = _org_data_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(org.to_json())


def cmd_org_status(args: argparse.Namespace) -> int:
    """Show the org chart hierarchy and per-node prompt/model state."""
    org = _load_org_chart()
    print(f"Org: {org.name} — {json.dumps(org.stats())}")
    for n in org.nodes():
        chain = " / ".join(c.name for c in org.chain(n.uid))
        bindings = BindingStore()
        b = bindings.get(n.uid)
        print(f"  [{n.level.value}] {n.name} ({n.role}) — chain: {chain}" +
              (f" | model: {b.model}" if b else ""))
    if args.verbose:
        ps = PromptSystem(org)
        for n in org.nodes():
            print(f"\n--- Prompt of {n.name} ---")
            print(ps.resolve(n)[:400], "...")
    return 0


def cmd_org_add(args: argparse.Namespace) -> int:
    """Deploy a new manager/agent/subagent into the chart."""
    org = _load_org_chart()
    try:
        if args.kind == "manager":
            org.add_manager(args.parent_uid, args.name, args.role,
                            domain=args.domain)
        elif args.kind == "agent":
            org.add_agent(args.parent_uid, args.name, args.role,
                          domain=args.domain,
                          commands=args.allow_commands,
                          files=args.allow_files)
        else:
            org.add_subagent(args.parent_uid, args.name, args.role)
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
    _save_org_chart(org)
    print(f"Deployed {args.kind} '{args.name}' ({args.role}) under "
          f"{org.node(args.parent_uid).name}")
    return 0


def cmd_org_bind(args: argparse.Namespace) -> int:
    """Bind a model (provider/model) to a node, overriding its tier default."""
    store = BindingStore()
    if args.unset:
        store.unset(args.node_uid)
        print(f"Unbound model for {args.node_uid}")
        return 0
    try:
        b = store.set(args.node_uid, args.model, pinned=not args.unpinned)
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
    _save_org_chart(_load_org_chart())
    print(f"Bound {b.model} to {args.node_uid} (pinned={b.pinned})")
    print(json.dumps(store.summary(), indent=1))
    return 0


def cmd_org_prompt(args: argparse.Namespace) -> int:
    """View/edit system prompts; build a guided first-draft prompt."""
    org = _load_org_chart()
    ps = PromptSystem(org)
    if args.action == "guide":
        print(PromptSystem.describe_prompt_guidelines(
            args.role_or_level or "generic_worker"))
        return 0
    if args.action == "build":
        draft = PromptSystem.build_prompt(args.role, mission=args.mission,
                                          output_format=args.output_format)
        print(draft)
        print("\n(Tweak this draft, then `maik org prompt edit` it for a "
              "node.)")
        return 0
    if args.action in ("view", "edit"):
        nm = " ".join(args.node) if isinstance(args.node, list) else (args.node or "")
        node = _lookup_node(org, nm)
        if node is None:
            print(f"ERROR: node '{nm}' not found")
            return 1
    if args.action == "view":
        print(ps.resolve(node))
        return 0
    if args.action == "edit":
        if args.text is None:
            print("ERROR: pass --text with the new prompt text")
            return 1
        sp = ps.get(f"org:{node.uid}")
        ps.update_text(f"org:{node.uid}", args.text, editor="rehan-owner")
        print(f"Updated system prompt for {node.name}. Resolved prompt:")
        print(ps.resolve(node))
        return 0
    return 0


def cmd_org_notebook(args: argparse.Namespace) -> int:
    """Read or write an agent's public or hidden notebook (CEO oversight)."""
    org = _load_org_chart()
    nb = Notebooks(org)
    node = _lookup_node(org, " ".join(args.node) if isinstance(args.node, list) else args.node)
    if node is None:
        print(f"ERROR: node '{args.node}' not found")
        return 1
    if args.mode == "write":
        text = " ".join(args.text) if args.text else ""
        if not text:
            print("ERROR: pass --text to write an entry")
            return 1
        nb.write(node.uid, args.kind, text, author="rehan-owner")
        print(f"Wrote to {node.name}'s {args.kind} notebook.")
    else:
        entries = nb.read(node.uid, args.kind, viewer_uid=node.uid)
        for e in entries:
            print(f"[{e.get('ts','?')}] ({e.get('author','?')}) {e.get('content','')}")
    return 0


def cmd_org_deploy(args: argparse.Namespace) -> int:
    """Spawn an external coding CLI tool for fast work (coding access)."""
    dep = CLIDeployer()
    if args.action == "probe":
        print(json.dumps(dep.probe(args.tool), indent=1))
    elif args.action == "spawn":
        try:
            out = dep.spawn(args.tool, args.task, timeout=args.timeout)
            print(out)
        except RuntimeError as e:
            print(f"ERROR: {e}")
            print("Install the tool first (e.g. pipx install aider) or use "
                  "`maik org deploy probe <tool>` to see why it failed.")
            return 1
    else:
        print(json.dumps(dep.summary(), indent=1))
    return 0


def cmd_org_thread(args: argparse.Namespace) -> int:
    """Manage team chat threads (WhatsApp-style with CEO veto power)."""
    org = _load_org_chart()
    hub = ThreadHub(org)
    if args.action == "create":
        t = hub.create(args.topic, owner_uid=args.owner)
        print(f"Thread created: {t.id}")
    elif args.action == "post":
        t = hub.get(args.thread_id)
        if t is None:
            print("ERROR: thread not found"); return 1
        if not args.text:
            print("ERROR: pass --text to post a message"); return 1
        t.post(args.owner, args.text)
        hub._persist(t)
        print(f"Posted to {t.topic}: {args.text}")
    elif args.action == "list":
        print(json.dumps(hub.summary(), indent=1))
    elif args.action == "veto":
        t = hub.get(args.thread_id)
        if t is None:
            print("ERROR: thread not found"); return 1
        try:
            m = t.veto(args.owner, args.reason)
            hub._persist(t)
            print(f"VETO by {m.author_uid}: {m.text}")
        except ValueError as e:
            print(f"ERROR: {e}"); return 1
    elif args.action == "counter":
        t = hub.get(args.thread_id)
        if t is None:
            print("ERROR: thread not found"); return 1
        if not args.text:
            print("ERROR: pass --text with the counter-argument"); return 1
        m = t.counter_argue(args.owner, args.text)
        hub._persist(t)
        print(f"Counter-argue by {m.author_uid}: {m.text}")
    elif args.action == "consensus":
        t = hub.get(args.thread_id)
        if t is None:
            print("ERROR: thread not found"); return 1
        m = t.close_consensus(args.owner)
        hub._persist(t)
        print(f"CONSENSUS reached: {m.text}")
    return 0


def cmd_org(args: argparse.Namespace) -> int:
    """Dispatch the org-chart family: status/add/bind/prompt/notebook/"""
    """deploy/thread."""
    return args.org_func(args)


def cmd_status(_args: argparse.Namespace) -> int:
    """Show system health: providers, learning, memory, patterns."""
    learn = LearningSystem()
    mem = MemorySystem()
    lib = PatternLibrary()
    audit = secrets_audit()
    print("Key hygiene audit:", "clean" if not audit else "; ".join(audit))
    print("\nLearning state")
    print(json.dumps(learn.status(), indent=1))
    print("\nMemory state")
    print(json.dumps(mem.status(), indent=1))
    print("\nPattern library")
    print(tabulate([(p["name"], p["domain"], p["performance"],
                     p["hits"], p["active"], p["tier_hint"])
                    for p in lib.status()],
                   headers=["pattern", "domain", "perf", "hits",
                            "active", "tier"], tablefmt="simple"))
    fw_path = Path(__file__).resolve().parent.parent / "reroute_rules.json"
    if fw_path.exists():
        d = json.loads(fw_path.read_text())
        print(f"\nFlywheel: revolution {d.get('revolution', 0)}, "
              f"{len(d.get('rules', {}))} reroute rules persisted")
    return 0


def cmd_flywheel(args: argparse.Namespace) -> int:
    """Run the closed learning loop."""
    fw = Flywheel(max_revolution=args.revolutions)
    for _ in range(args.revolutions):
        report = fw.run()
        print(f"\nRevolution {report.revolution}: "
              f"{report.accuracy_before:.3f} -> {report.accuracy_after:.3f} | "
              f"rules changed {report.rules_changed}, patterns tuned "
              f"{report.patterns_tuned}, contradictions mined "
              f"{report.contradictions_mined}")
    print("\nPersisted rules:", json.dumps(fw.reroute_rules, indent=1))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="maik",
        description="MAIK Kernel v3 — multi-agent orchestration CLI")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("solve", help="Solve one problem with the cascade")
    s.add_argument("problem", help="The problem text")
    s.add_argument("--max-tokens", type=int, default=2048)
    s.set_defaults(func=cmd_solve)

    b = sub.add_parser("bench", help="Run the ground-truth benchmark")
    b.add_argument("--n", type=int, default=None,
                   help="Run only the first N problems")
    b.add_argument("--stub", action="store_true",
                   help="Force offline stub mode (no LLM calls)")
    b.set_defaults(func=cmd_bench)

    st = sub.add_parser("status", help="Show system health and learning state")
    st.set_defaults(func=cmd_status)

    o = sub.add_parser("org", help="Phase H org-chart: status/add/bind/"
                                   "prompt/notebook/deploy/thread")
    osub = o.add_subparsers(dest="org_command", required=True)

    os_ = osub.add_parser("status", help="Show org chart and bindings")
    os_.add_argument("-v", "--verbose", action="store_true",
                     help="Also print each node's resolved prompt")
    os_.set_defaults(org_func=cmd_org_status)

    oa = osub.add_parser("add", help="Deploy a manager/agent/subagent")
    oa.add_argument("kind", choices=["manager", "agent", "subagent"])
    oa.add_argument("parent_uid", help="CEO/manager/agent uid to attach under")
    oa.add_argument("name")
    oa.add_argument("role")
    oa.add_argument("--domain", default="")
    oa.add_argument("--allow-commands", action="store_true",
                    help="Grant command_run power (agents/subagents only)")
    oa.add_argument("--allow-files", action="store_true",
                    help="Grant file_create power (agents/subagents only)")
    oa.set_defaults(org_func=cmd_org_add)

    ob = osub.add_parser("bind", help="Bind a model to a node (tier override)")
    ob.add_argument("node_uid")
    ob.add_argument("model", nargs="?", default=None)
    ob.add_argument("--unset", action="store_true",
                    help="Remove the node's binding")
    ob.add_argument("--unpinned", action="store_true",
                    help="Non-pinned binding (tier can still override)")
    ob.set_defaults(org_func=cmd_org_bind)

    op = osub.add_parser("prompt", help="View/edit prompts, guide, build")
    op.add_argument("action", choices=["guide", "build", "view", "edit"])
    op.add_argument("--role-or-level", default=None)
    op.add_argument("--role", default="generic_worker")
    op.add_argument("--mission", default=None)
    op.add_argument("--output-format", default="direct answer")
    op.add_argument("--node", nargs="*", default=None)
    op.add_argument("--text", default=None)
    op.set_defaults(org_func=cmd_org_prompt)

    onb = osub.add_parser("notebook", help="Read/write agent notebooks")
    onb.add_argument("mode", choices=["read", "write"])
    onb.add_argument("node", nargs="+")
    onb.add_argument("kind", choices=["public", "hidden"])
    onb.add_argument("--text", nargs="*", default=[],
                     help="Text to write (space-separated; wraps into one entry)")
    onb.set_defaults(org_func=cmd_org_notebook)

    od = osub.add_parser("deploy", help="Spawn external coding CLI tools")
    od.add_argument("action", choices=["probe", "spawn", "summary"])
    od.add_argument("tool", nargs="?", default=None)
    od.add_argument("--task", default=None)
    od.add_argument("--timeout", type=int, default=120)
    od.set_defaults(org_func=cmd_org_deploy)

    ot = osub.add_parser("thread", help="Team chat threads with CEO veto")
    ot.add_argument("action", choices=["create", "post", "list", "veto",
                                       "counter", "consensus"])
    ot.add_argument("--topic", default=None)
    ot.add_argument("--owner", default=None)
    ot.add_argument("--thread-id", default=None)
    ot.add_argument("--text", default=None)
    ot.add_argument("--reason", default=None)
    ot.set_defaults(org_func=cmd_org_thread)

    o.set_defaults(func=cmd_org)

    i = sub.add_parser("init", help="Create encrypted .env (first-run setup)")
    i.set_defaults(func=cmd_init)

    f = sub.add_parser("flywheel", help="Run the closed learning loop")
    f.add_argument("--revolutions", type=int, default=1,
                   help="Number of loop revolutions (default 1)")
    f.set_defaults(func=cmd_flywheel)

    return p


def cli(argv: Optional[list] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(cli())
