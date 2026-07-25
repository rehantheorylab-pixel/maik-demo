#!/usr/bin/env python3
"""MAIK CLI — best-in-class terminal UI with Rich."""
import sys, os, json, time, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.layout import Layout
from rich.columns import Columns
from rich.text import Text
from rich import box
from rich.live import Live
from rich.tree import Tree
from rich.align import Align
from rich.prompt import Prompt as RichPrompt

from config import TokenBudget, council
from router_engine import route, clear_cache, cache_stats
from tree_engine import execute, ceo_execution_breakdown
from learn_engine import learn, get_stats
from scheduler_engine import scheduler
from cognitive_engine import incubation
from memory_engine import thought_vdb, l1_memory
from evolution_engine import pbt
from safety_engine import stop_light
from boolean_engine import voter

console = Console(legacy_windows=True)

MAIK_LOGO = """
[bold cyan]  __  __      _   _   _  __  ___ _  _   _   [/bold cyan]
[bold cyan] |  \\/  |__ _| |_(_)_(_)/ _|/ __| || | /_\\  [/bold cyan]
[bold cyan] | |\\/| / _`|  _| | | |  _| (__| __ |/ _ \\ [/bold cyan]
[bold cyan] |_|  |_\\__,_|\\__|_|_|_|_|  \\___|_||_/_/ \\_\\\\[/bold cyan]
"""

def make_header():
    return Panel(
        Text.from_markup(f"{MAIK_LOGO}\n[dim]Multi-Agent Intelligence Kernel  •  {council.num_ceos} CEOs  •  {council.profile} profile[/dim]"),
        box=box.ASCII, border_style="cyan", padding=(0, 2)
    )

def status_tag(condition, ok_text="active", fail_text="inactive"):
    return f"[green]{ok_text}[/green]" if condition else f"[red]{fail_text}[/red]"

def print_header():
    console.print(make_header())

@click.group(invoke_without_command=True)
@click.option("--budget", default=100000, help="Token budget")
@click.pass_context
def cli(ctx, budget):
    ctx.ensure_object(dict)
    ctx.obj["budget"] = budget
    if ctx.invoked_subcommand is None:
        ctx.invoke(interactive)

@cli.command()
@click.argument("problem")
@click.option("--domain", "-d", default="", help="Domain hint")
@click.option("--learn/--no-learn", default=True, help="Auto-learn from result")
@click.pass_context
def ask(ctx, problem, domain, learn):
    """Ask MAIK: route + execute + learn in one shot."""
    print_header()
    budget = TokenBudget(total=ctx.obj["budget"])

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console, transient=True) as p:
        p.add_task("[cyan]Routing...", total=None)
        r = route(problem, domain, budget)
        p.add_task(f"[green]{r['ceo_name']}[/green] -> [bold]{r['expert']}[/bold]", total=None)

    console.print(Panel(
        Text.from_markup(f"[bold]{r['ceo_name']}[/bold]  ->  [cyan]{r['expert']}[/cyan]  (conf={r['confidence']:.0%})"),
        box=box.ASCII, border_style="blue", padding=(0, 1)
    ))

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console, transient=True) as p:
        task = p.add_task("[cyan]Executing agent tree...", total=None)
        result = execute(problem, domain, budget)
        p.update(task, description="[green]Done[/green]")

    md = Markdown(result['solution'][:5000] or "(no output)")
    console.print(Panel(md, box=box.ASCII, border_style="green", title="[bold]Response[/bold]"))
    console.print(f"[dim]conf={result['confidence']:.0%}  depth={result['depth']}  agents={len(result['agents_used'])}  CEO: {result.get('ceo','?')}[/dim]")

    if learn:
        learn(problem, result['solution'][:500], "success", result['agents_used'], result['confidence'], 0, 0)

@cli.command()
@click.argument("problem")
@click.option("--domain", "-d", default="")
@click.pass_context
def route_cmd(ctx, problem, domain):
    """Route a problem to the best expert & CEO."""
    print_header()
    budget = TokenBudget(total=ctx.obj["budget"])
    with console.status("[cyan]Routing...[/cyan]", spinner="dots"):
        r = route(problem, domain, budget)

    table = Table(box=box.ASCII, border_style="blue")
    table.add_column("Property", style="bold cyan")
    table.add_column("Value")
    table.add_row("CEO", f"{r['ceo_name']} [dim]({r['ceo']})[/dim]")
    table.add_row("Expert", r['expert'])
    table.add_row("Problem Type", r['problem_type'])
    table.add_row("Confidence", f"{r['confidence']:.0%}")
    table.add_row("Model", f"{r['model']} [dim]({r['model_full']})[/dim]")
    table.add_row("Budget", str(r['budget']))
    table.add_row("CEO Budget", r.get('ceo_budget', 'N/A'))
    table.add_row("Cached", status_tag(r['cached'], "cached", "miss"))
    table.add_row("Cache Hit Rate", f"{r['cache_stats']['hit_rate']:.0%}")
    console.print(table)

@cli.command()
@click.argument("problem")
@click.option("--domain", "-d", default="")
@click.option("--depth", default=0)
@click.pass_context
def execute_cmd(ctx, problem, domain, depth):
    """Execute a problem through the agent tree."""
    print_header()
    budget = TokenBudget(total=ctx.obj["budget"])
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console, transient=True) as p:
        p.add_task("[cyan]Executing...", total=None)
        result = execute(problem, domain, budget, depth)

    md = Markdown(result['solution'][:5000] or "(no output)")
    console.print(Panel(md, box=box.ASCII, border_style="green", title="[bold]Solution[/bold]"))
    console.print(f"[dim]conf={result['confidence']:.0%}  depth={result['depth']}  agents={len(result['agents_used'])}[/dim]")

@cli.command()
@click.argument("problem")
@click.option("--solution", "-s", default="")
@click.option("--outcome", "-o", default="success", type=click.Choice(["success","failure","partial"]))
@click.option("--confidence", "-c", default=0.75, type=float)
@click.pass_context
def learn_cmd(ctx, problem, solution, outcome, confidence):
    """Record a learning experience."""
    print_header()
    result = learn(problem, solution, outcome, [], confidence, 0, 0)
    table = Table(box=box.ASCII, border_style="yellow")
    table.add_column("Metric", style="bold yellow")
    table.add_column("Value")
    table.add_row("Learned", status_tag(result['learned']))
    table.add_row("Run ID", result['run_id'][:12])
    table.add_row("Total Runs", str(result['total_runs']))
    table.add_row("Replay Queue", str(result['replay_queue_size']))
    console.print(table)
    if result['elo_updated']:
        elo_table = Table(box=box.ASCII, border_style="dim", title="ELO Ratings")
        elo_table.add_column("Agent", style="cyan")
        elo_table.add_column("Rating")
        for agent, rating in list(result['elo_updated'].items())[:5]:
            elo_table.add_row(agent, f"{rating:.0f}")
        console.print(elo_table)

@cli.command()
def status():
    """Show system health & stats."""
    print_header()
    stats = get_stats()
    cs = cache_stats()
    s = scheduler.stats()
    ps = pbt.stats()
    ceo_counts = ceo_execution_breakdown()

    grid = Table.grid(padding=1)
    grid.add_column(style="bold cyan", width=18)
    grid.add_column(width=30)
    grid.add_column(style="bold cyan", width=18)
    grid.add_column(width=30)

    grid.add_row(
        "Runs", str(stats['total_runs']),
        "Cache", f"{cs['size']} entries ({cs['hit_rate']:.0%} hit)"
    )
    grid.add_row(
        "Success Rate", f"{stats['success_rate']:.0%}",
        "Schedule", f"{s['queue_size']} queued, {s['completed']} done"
    )
    grid.add_row(
        "Avg Confidence", f"{stats['avg_confidence']:.0%}",
        "PBT Gen", str(ps['generation'])
    )
    grid.add_row(
        "Avg Tokens", f"{stats['avg_tokens']:.0f}",
        "Stop Light", status_tag(stop_light.status() == "green", "green", stop_light.status())
    )
    grid.add_row(
        "ELO Agents", str(len(stats['elo_ratings'])),
        "Council", f"{council.num_ceos} CEOs ({council.profile})"
    )
    grid.add_row(
        "Replay Queue", str(stats['replay_queue']),
        "Budget", "active" if stats['total_runs'] > 0 else "idle"
    )
    console.print(Panel(grid, box=box.ASCII, border_style="cyan", title="[bold]System Status[/bold]"))

    if ceo_counts:
        t = Table(box=box.ASCII, border_style="dim", title="CEO Execution Breakdown")
        t.add_column("CEO", style="cyan")
        t.add_column("Calls")
        for ceo_id, count in sorted(ceo_counts.items(), key=lambda x: -x[1]):
            t.add_row(ceo_id, str(count))
        console.print(t)

@cli.command()
def council_cmd():
    """Show the Executive Council (12 CEOs)."""
    print_header()
    console.print(Panel(
        Text.from_markup(f"[bold]{council.num_ceos} CEOs[/bold]  •  [dim]{council.profile} profile[/dim]"),
        box=box.ASCII, border_style="cyan"
    ))
    table = Table(box=box.ASCII, border_style="blue", title="Executive Council")
    table.add_column("CEO", style="bold cyan", no_wrap=True)
    table.add_column("Name", style="white")
    table.add_column("Managers")
    table.add_column("APIs")
    table.add_column("Budget")
    for c in council.list_ceos():
        table.add_row(
            c['id'], c['name'],
            str(c['managers']), str(c['api_count']),
            c['budget']
        )
    console.print(table)

@cli.command()
@click.argument("thought")
@click.option("--tags", "-t", multiple=True, help="Tags")
@click.option("--query", "-q", default="", help="Query related thoughts")
def thought(thought, tags, query):
    """Inject a thought into the Thought VDB."""
    print_header()
    thought_vdb.inject("cli", thought, list(tags) if tags else [])
    console.print(Panel(
        Text.from_markup(f"[green]+[/green] Thought injected: [italic]{thought[:80]}[/italic]"),
        box=box.ASCII, border_style="green"
    ))
    if query:
        results = thought_vdb.query(query)
        if results:
            t = Table(box=box.ASCII, border_style="dim", title="Related Thoughts")
            t.add_column("Confidence")
            t.add_column("Thought")
            for r in results:
                t.add_row(f"{r['confidence']:.0%}", r['thought'][:80])
            console.print(t)

@cli.command()
@click.option("--query", "-q", default="", help="Search query")
def memory(query):
    """Query L1 memory & Thought VDB."""
    print_header()
    l1r = l1_memory.recall(query or "general")
    tvdb = thought_vdb.query(query or "general")

    if l1r:
        t = Table(box=box.ASCII, border_style="cyan", title="L1 Memory")
        t.add_column("Score")
        t.add_column("Content")
        for r in l1r:
            t.add_row(f"{r['score']:.2f}", r['value'][:80])
        console.print(t)

    if tvdb:
        t = Table(box=box.ASCII, border_style="magenta", title="Thought VDB")
        t.add_column("Conf.")
        t.add_column("Thought")
        t.add_column("Tags")
        for r in tvdb:
            tags_str = ", ".join(r.get('tags', [])[:2]) if r.get('tags') else ""
            t.add_row(f"{r['confidence']:.0%}", r['thought'][:80], tags_str)
        console.print(t)

@cli.command()
@click.option("--description", "-d", default="", help="Task description")
@click.option("--urgency", "-u", default=0.5, type=float)
def schedule_cmd(description, urgency):
    """Enqueue or view scheduled tasks."""
    print_header()
    if description:
        tid = scheduler.enqueue(description, "general", 100, urgency)
        console.print(Panel(
            Text.from_markup(f"[green]+[/green] Enqueued: [cyan]{tid}[/cyan] (queue: {scheduler.stats()['queue_size']})"),
            box=box.ASCII, border_style="green"
        ))
    s = scheduler.stats()
    t = Table(box=box.ASCII, border_style="yellow", title="Scheduler")
    t.add_column("Metric")
    t.add_column("Value")
    t.add_row("Queued", str(s['queue_size']))
    t.add_row("Running", str(s['running']))
    t.add_row("Completed", str(s['completed']))
    t.add_row("Budget Spent", f"{s['budget_spent']:.0f}")
    console.print(t)
    next_tasks = scheduler.next_up(5)
    if next_tasks:
        n = Table(box=box.ASCII, border_style="dim", title="Next Up")
        n.add_column("Urgency")
        n.add_column("Task")
        n.add_column("Agent")
        for nt in next_tasks:
            n.add_row(f"{nt['urgency']:.1f}", nt['desc'], nt['agent'])
        console.print(n)

@cli.command()
def evolve():
    """Run one PBT evolution generation."""
    print_header()
    with console.status("[cyan]Evolving...[/cyan]", spinner="dots"):
        gen = pbt.evolve()
    s = pbt.stats()
    console.print(Panel(
        Text.from_markup(
            f"[bold]Generation {gen}[/bold]\n"
            f"Population: [cyan]{s['population']}[/cyan]\n"
            f"Best Fitness: [green]{s['best_fitness']:.3f}[/green]\n"
            f"Avg Fitness: [yellow]{s['avg_fitness']:.3f}[/yellow]"
        ),
        box=box.ASCII, border_style="green", title="[bold]Evolution[/bold]"
    ))

@cli.command()
@click.option("--action", type=click.Choice(["status","pause","resume"]), default="status")
def safety(action):
    """Safety system controls."""
    print_header()
    if action == "status":
        from safety_engine import purity as pf
        table = Table(box=box.ASCII, border_style="red")
        table.add_column("System", style="bold red")
        table.add_column("Status")
        table.add_row("Stop Light", status_tag(stop_light.status() == "green", stop_light.status(), stop_light.status()))
        table.add_row("Violations", str(pf.violation_count()))
        table.add_row("Kill Switch", "(inactive)")
        console.print(table)
    elif action == "pause":
        stop_light.set_red()
        console.print("[red]Paused (red light)[/red]")
    elif action == "resume":
        stop_light.set_green()
        console.print("[green]Resumed (green light)[/green]")

@cli.command()
def interactive():
    """Interactive REPL mode with Rich UI."""
    print_header()
    console.print(Panel(
        "[bold cyan]Interactive Mode[/bold cyan]\n"
        "Type any question to ask MAIK.\n"
        "[dim]Commands: /route, /execute, /status, /council, /evolve, /memory, /thought, /help, exit[/dim]",
        box=box.ASCII, border_style="cyan"
    ))
    while True:
        try:
            line = RichPrompt.ask("[bold cyan]maik[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Goodbye![/yellow]")
            break
        if not line:
            continue
        if line.lower() in ("exit", "quit", "q"):
            break
        if line.startswith("/"):
            parts = line[1:].split(maxsplit=1)
            sub = parts[0].lower() if parts else ""
            rest = parts[1] if len(parts) > 1 else ""
            if sub == "route" and rest:
                budget = TokenBudget(total=100000)
                r = route(rest, "", budget)
                console.print(Panel(
                    Text.from_markup(f"[bold]{r['ceo_name']}[/bold]  ->  [cyan]{r['expert']}[/cyan]  ({r['confidence']:.0%})"),
                    box=box.ASCII, border_style="blue"
                ))
            elif sub == "execute" and rest:
                with console.status("[cyan]Executing...[/cyan]"):
                    result = execute(rest)
                md = Markdown(result['solution'][:2000])
                console.print(Panel(md, box=box.ASCII, border_style="green"))
            elif sub in ("status", "st"):
                stats = get_stats()
                grid = Table.grid(padding=1)
                grid.add_row("Runs", str(stats['total_runs']), "Success", f"{stats['success_rate']:.0%}")
                grid.add_row("Cache", f"{cache_stats()['size']} entries", "Council", f"{council.num_ceos} CEOs")
                console.print(Panel(grid, box=box.ASCII, border_style="cyan"))
            elif sub == "council":
                for c in council.list_ceos():
                    console.print(f"  [cyan]{c['id']:<18}[/cyan] {c['name']:<25} [dim]{c['managers']} mgrs[/dim]")
            elif sub == "evolve":
                gen = pbt.evolve()
                console.print(f"[green]Generation {gen}[/green]")
            elif sub in ("memory", "mem"):
                l1r = l1_memory.recall(rest or "general")
                for r in l1r[:3]:
                    console.print(f"  [dim]{r['score']:.2f}[/dim] {r['value'][:80]}")
            elif sub == "thought" and rest:
                thought_vdb.inject("interactive", rest)
                console.print("[green]Thought injected[/green]")
            elif sub == "help":
                console.print("[cyan]/route[/cyan] <q>  [cyan]/execute[/cyan] <q>  [cyan]/status[/cyan]  [cyan]/council[/cyan]  [cyan]/evolve[/cyan]  [cyan]/thought[/cyan]  [cyan]/memory[/cyan]")
            else:
                console.print(f"[red]Unknown: /{sub}[/red]")
        else:
            budget = TokenBudget(total=100000)
            with console.status("[cyan]Routing...[/cyan]", spinner="dots"):
                r = route(line, "", budget)
            console.print(f"[bold]{r['ceo_name']}[/bold]  ->  [cyan]{r['expert']}[/cyan]")
            with console.status("[cyan]Executing...[/cyan]"):
                result = execute(line, "", budget)
            md = Markdown(result['solution'][:2000])
            console.print(Panel(md, box=box.ASCII, border_style="green"))
            learn(line, result['solution'][:500], "success", result['agents_used'], result['confidence'], 0, 0)

if __name__ == "__main__":
    cli()
