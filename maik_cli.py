#!/usr/bin/env python3
"""MAIK CLI — Use MAIK from terminal, like claude or opencode.

Usage:
  maik ask "write a sorting function in Rust"
  maik route "solve 2x+5=13"
  maik execute "design a microservice" --domain planning
  maik learn "problem" --solution "answer" --outcome success
  maik status
  maik council
  maik safety status
  maik thought "Eureka: agents could use shared memory"
  maik memory recall "rust ownership"
  maik schedule enqueue "fix bug" --urgency 0.9
  maik evolve
  maik interactive

Build standalone .exe:
  pyinstaller --onefile --name maik maik_cli.py
"""

import sys
import os
import time
import json
import argparse
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import TokenBudget, cfg, corp, experts, council
from blackboard import blackboard, internal_notes
from router_engine import route, clear_cache, cache_stats, ceo_routing_log
from tree_engine import execute, get_execution_log, ceo_execution_breakdown
from learn_engine import learn, get_stats
from scheduler_engine import scheduler
from cognitive_engine import incubation, abductor, analogizer, wanderer
from memory_engine import thought_vdb, l1_memory
from evolution_engine import pbt
from boolean_engine import voter
from safety_engine import stop_light
from purity_filter import purity as purity_check

def cmd_ask(args):
    budget = TokenBudget(total=args.budget)
    r = route(args.problem, args.domain, budget)
    print(f"[{r['ceo_name']}] {r['expert']} (conf={r['confidence']:.0%})")
    if not args.route_only:
        result = execute(args.problem, args.domain, budget)
        print(f"\n{result['solution'][:2000]}")
        print(f"\n[conf={result['confidence']:.0%} depth={result['depth']} agents={len(result['agents_used'])}]")
        if args.learn:
            learn(args.problem, result['solution'][:2000], "success",
                  result['agents_used'], result['confidence'], 0, 0)

def cmd_route(args):
    budget = TokenBudget(total=args.budget)
    r = route(args.problem, args.domain, budget)
    print(f"CEO:       {r['ceo_name']} ({r['ceo']})")
    print(f"Expert:    {r['expert']}")
    print(f"Type:      {r['problem_type']}")
    print(f"Model:     {r['model']} ({r['model_full']})")
    print(f"Conf:      {r['confidence']:.0%}")
    print(f"Budget:    {r['budget']}")
    print(f"Cached:    {r['cached']}")

def cmd_execute(args):
    budget = TokenBudget(total=args.budget)
    r = execute(args.problem, args.domain, budget, args.depth)
    print(r['solution'][:2000])
    print(f"\n[CEO: {r.get('ceo', '?')} conf={r['confidence']:.0%} depth={r['depth']} agents={len(r['agents_used'])}]")
    if args.verbose:
        for a in r['agents_used']:
            print(f"  agent: {a['role']} state={a['state']} tokens={a['tokens']}")

def cmd_learn(args):
    result = learn(args.problem, args.solution, args.outcome,
                   [{"role": r} for r in args.roles], args.confidence, args.tokens, args.duration)
    print(f"learned={result['learned']} run_id={result['run_id']}")
    print(f"ELO: {json.dumps(result['elo_updated'], indent=2)}")
    print(f"replay_queue={result['replay_queue_size']} total_runs={result['total_runs']}")

def cmd_status(args):
    stats = get_stats()
    print(f"Runs:         {stats['total_runs']}")
    print(f"Success rate: {stats['success_rate']:.0%}")
    print(f"Avg conf:     {stats['avg_confidence']:.0%}")
    print(f"Avg tokens:   {stats['avg_tokens']:.0f}")
    print(f"ELO ratings:  {len(stats['elo_ratings'])} agents")
    print(f"Replay queue: {stats['replay_queue']}")
    cs = cache_stats()
    print(f"Cache:        {cs['size']} entries ({cs['hit_rate']:.0%} hit rate)")
    print(f"Schedule:     {scheduler.stats()['queue_size']} queued / {scheduler.stats()['completed']} completed")
    print(f"PBT gen:      {pbt.stats()['generation']}")
    print(f"Stop light:   {stop_light.status()}")
    print(f"Council:      {council.num_ceos} CEOs ({council.profile} profile)")
    ceo_breakdown = ceo_execution_breakdown()
    if ceo_breakdown:
        print(f"CEO usage:    {json.dumps(ceo_breakdown)}")

def cmd_council(args):
    print(f"Profile: {council.profile} ({council.num_ceos} CEOs)")
    print()
    for c in council.list_ceos():
        print(f"  {c['id']:<18} {c['name']:<25} {c['managers']} managers  {c['api_count']} APIs  {c['budget']}")

def cmd_thought(args):
    thought_vdb.inject("cli", args.thought, args.tags or [])
    print(f"Thought injected: {args.thought[:60]}...")
    if args.query:
        results = thought_vdb.query(args.query)
        print(f"\nRelated thoughts ({len(results)}):")
        for r in results:
            print(f"  [{r['confidence']:.0%}] {r['thought'][:100]}")

def cmd_memory(args):
    if args.action == "recall":
        l1r = l1_memory.recall(args.query)
        print(f"L1 results ({len(l1r)}):")
        for r in l1r:
            print(f"  [{r['score']:.2f}] {r['value'][:100]}")
        tvdb = thought_vdb.query(args.query)
        print(f"\nThoughts ({len(tvdb)}):")
        for r in tvdb:
            print(f"  [{r['confidence']:.0%}] {r['thought'][:100]}")
    else:
        l1_memory.store(args.key, args.value)
        print(f"Stored: {args.key}")

def cmd_schedule(args):
    if args.action == "enqueue":
        tid = scheduler.enqueue(args.description, args.agent_type, args.cost, args.urgency)
        print(f"Enqueued: {tid} (queue: {scheduler.stats()['queue_size']})")
    elif args.action == "status":
        s = scheduler.stats()
        print(f"Queue: {s['queue_size']}  Running: {s['running']}  Completed: {s['completed']}")
        print(f"Budget spent: {s['budget_spent']:.0f}")
    elif args.action == "next":
        for t in scheduler.next_up(5):
            print(f"  [{t['urgency']:.1f}] {t['desc']} ({t['agent']})")

def cmd_evolve(args):
    gen = pbt.evolve()
    s = pbt.stats()
    print(f"Generation {gen}: pop={s['population']} best={s['best_fitness']:.3f} avg={s['avg_fitness']:.3f}")

def cmd_safety(args):
    if args.action == "status":
        print(f"Stop light:   {stop_light.status()}")
        print(f"Kill switch:  false")
        from safety_engine import purity as pf
        print(f"Violations:   {pf.violation_count()}")
    elif args.action == "pause":
        stop_light.set_red()
        print("Paused (red light)")
    elif args.action == "resume":
        stop_light.set_green()
        print("Resumed (green light)")

def cmd_interactive(args):
    print("MAIK Interactive — type 'exit' or 'quit' to stop.")
    print("Prefix commands: /route, /execute, /learn, /status, /council, /help")
    while True:
        try:
            line = input("\nmaik> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not line:
            continue
        if line.lower() in ("exit", "quit"):
            break
        if line.startswith("/"):
            parts = line[1:].split(maxsplit=1)
            sub = parts[0].lower() if parts else ""
            rest = parts[1] if len(parts) > 1 else ""
            if sub == "route" and rest:
                r = route(rest)
                print(f"[{r['ceo_name']}] {r['expert']} conf={r['confidence']:.0%}")
            elif sub == "execute" and rest:
                result = execute(rest)
                print(result['solution'][:1000])
            elif sub == "status":
                cmd_status(args)
            elif sub == "council":
                cmd_council(args)
            elif sub == "help":
                print("Commands: /route <q>, /execute <q>, /learn <q> <outcome>, /status, /council, exit")
            else:
                print(f"Unknown: /{sub}")
        else:
            budget = TokenBudget(total=args.budget)
            r = route(line, "", budget)
            result = execute(line, "", budget)
            print(f"[{r['ceo_name']} → {r['expert']}]")
            print(result['solution'][:1000])
            learn(line, result['solution'][:500], "success", result['agents_used'], result['confidence'], 0, 0)

def main():
    parser = argparse.ArgumentParser(description="MAIK — Multi-Agent Intelligence Kernel CLI",
                                     formatter_class=argparse.RawDescriptionHelpFormatter,
                                     epilog="""Examples:
  maik ask "write quicksort in Rust"
  maik route "solve 2x+5=13" --domain math
  maik execute "design microservice" --domain planning --verbose
  maik status
  maik council
  maik interactive
""")
    parser.add_argument("--budget", type=int, default=100000, help="Token budget")
    sub = parser.add_subparsers(dest="command")

    p_ask = sub.add_parser("ask", help="Ask a question (route + execute)")
    p_ask.add_argument("problem", help="Your question")
    p_ask.add_argument("--domain", "-d", default="", help="Domain hint")
    p_ask.add_argument("--route-only", action="store_true", help="Only route, don't execute")
    p_ask.add_argument("--learn", action="store_true", help="Learn from the result")

    p_route = sub.add_parser("route", help="Route a problem to the best expert")
    p_route.add_argument("problem", help="Problem description")
    p_route.add_argument("--domain", "-d", default="", help="Domain hint")

    p_exec = sub.add_parser("execute", help="Execute a problem through the agent tree")
    p_exec.add_argument("problem", help="Problem to solve")
    p_exec.add_argument("--domain", "-d", default="")
    p_exec.add_argument("--depth", type=int, default=0)
    p_exec.add_argument("--verbose", "-v", action="store_true")

    p_learn = sub.add_parser("learn", help="Record a learning experience")
    p_learn.add_argument("problem")
    p_learn.add_argument("--solution", "-s", default="")
    p_learn.add_argument("--outcome", "-o", default="success", choices=["success","failure","partial"])
    p_learn.add_argument("--roles", "-r", nargs="*", default=["agent"])
    p_learn.add_argument("--confidence", "-c", type=float, default=0.75)
    p_learn.add_argument("--tokens", type=int, default=0)
    p_learn.add_argument("--duration", type=int, default=0)

    sub.add_parser("status", help="Show system status")
    sub.add_parser("council", help="Show Executive Council info")
    sub.add_parser("interactive", help="Interactive REPL mode")

    p_thought = sub.add_parser("thought", help="Inject or query thoughts")
    p_thought.add_argument("thought", help="Thought content")
    p_thought.add_argument("--tags", "-t", nargs="*", default=[])
    p_thought.add_argument("--query", "-q", default="", help="Query related thoughts")

    p_mem = sub.add_parser("memory", help="Memory operations")
    p_mem.add_argument("action", choices=["recall", "store"])
    p_mem.add_argument("--query", "-q", default="")
    p_mem.add_argument("--key", "-k", default="")
    p_mem.add_argument("--value", "-v", default="")

    p_sched = sub.add_parser("schedule", help="Schedule operations")
    p_sched.add_argument("action", choices=["enqueue", "status", "next"])
    p_sched.add_argument("--description", "-d", default="")
    p_sched.add_argument("--agent-type", default="general")
    p_sched.add_argument("--cost", type=float, default=100.0)
    p_sched.add_argument("--urgency", "-u", type=float, default=0.5)

    sub.add_parser("evolve", help="Run one PBT evolution generation")

    p_safety = sub.add_parser("safety", help="Safety operations")
    p_safety.add_argument("action", choices=["status", "pause", "resume"])

    args = parser.parse_args()

    if args.command == "ask":
        cmd_ask(args)
    elif args.command == "route":
        cmd_route(args)
    elif args.command == "execute":
        cmd_execute(args)
    elif args.command == "learn":
        cmd_learn(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "council":
        cmd_council(args)
    elif args.command == "thought":
        cmd_thought(args)
    elif args.command == "memory":
        cmd_memory(args)
    elif args.command == "schedule":
        cmd_schedule(args)
    elif args.command == "evolve":
        cmd_evolve(args)
    elif args.command == "safety":
        cmd_safety(args)
    elif args.command == "interactive":
        cmd_interactive(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
