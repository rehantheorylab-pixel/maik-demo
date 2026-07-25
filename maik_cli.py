#!/usr/bin/env python3
"""MAIK CLI — full-featured terminal interface with all management capabilities."""
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
from rich.columns import Columns

from config import TokenBudget, council, api_configs, WORKFLOW_CHAINS, WorkflowStep, cfg
from config import APIConfig
from router_engine import route, clear_cache, cache_stats
from tree_engine import execute, ceo_execution_breakdown
from learn_engine import learn, get_stats
from scheduler_engine import scheduler
from cognitive_engine import incubation
from memory_engine import thought_vdb, l1_memory
from evolution_engine import pbt
from safety_engine import stop_light
from boolean_engine import voter
from meta_controller import prompt_selector, workflow_engine, meta_agent, PROMPT_TEMPLATES
from corporate_engine import org_chart, agent_tracker, corp_library, perm_system

console = Console(legacy_windows=True)

MAIK_LOGO = """
[bold cyan]  __  __      _   _   _  __  ___ _  _   _   [/bold cyan]
[bold cyan] |  \\/  |__ _| |_(_)_(_)/ _|/ __| || | /_\\  [/bold cyan]
[bold cyan] | |\\/| / _`|  _| | | |  _| (__| __ |/ _ \\ [/bold cyan]
[bold cyan] |_|  |_\\__,_|\\__|_|_|_|_|  \\___|_||_/_/ \\_\\\\[/bold cyan]
"""

def make_header():
    return Panel(
        Text.from_markup(f"{MAIK_LOGO}\n[dim]Multi-Agent Intelligence Kernel  •  {council.num_ceos} CEOs  •  {council.profile} profile  •  {len(api_configs)} APIs[/dim]"),
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
    """Route + execute + learn in one shot."""
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
    """Route a problem to best expert & CEO."""
    print_header()
    budget = TokenBudget(total=ctx.obj["budget"])
    with console.status("[cyan]Routing...[/cyan]", spinner="dots"):
        r = route(problem, domain, budget)
    table = Table(box=box.ASCII, border_style="blue")
    table.add_column("Property", style="bold cyan"); table.add_column("Value")
    table.add_row("CEO", f"{r['ceo_name']} [dim]({r['ceo']})[/dim]")
    table.add_row("Expert", r['expert']); table.add_row("Problem Type", r['problem_type'])
    table.add_row("Confidence", f"{r['confidence']:.0%}")
    table.add_row("Model", f"{r['model']} [dim]({r['model_full']})[/dim]")
    table.add_row("Budget", str(r['budget'])); table.add_row("CEO Budget", r.get('ceo_budget','N/A'))
    table.add_row("Cached", status_tag(r['cached'], "cached", "miss"))
    table.add_row("Cache Hit Rate", f"{r['cache_stats']['hit_rate']:.0%}")
    console.print(table)

@cli.command()
@click.argument("problem")
@click.option("--domain", "-d", default="")
@click.option("--depth", default=0)
@click.pass_context
def execute_cmd(ctx, problem, domain, depth):
    """Execute through agent tree."""
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
def learn_cmd(problem, solution, outcome, confidence):
    """Record a learning experience."""
    print_header()
    result = learn(problem, solution, outcome, [], confidence, 0, 0)
    table = Table(box=box.ASCII, border_style="yellow")
    table.add_column("Metric", style="bold yellow"); table.add_column("Value")
    table.add_row("Learned", status_tag(result['learned']))
    table.add_row("Run ID", result['run_id'][:12])
    table.add_row("Total Runs", str(result['total_runs']))
    table.add_row("Replay Queue", str(result['replay_queue_size']))
    console.print(table)
    if result['elo_updated']:
        elo_table = Table(box=box.ASCII, border_style="dim", title="ELO Ratings")
        elo_table.add_column("Agent", style="cyan"); elo_table.add_column("Rating")
        for agent, rating in list(result['elo_updated'].items())[:5]:
            elo_table.add_row(agent, f"{rating:.0f}")
        console.print(elo_table)

@cli.command(name="status")
def status_cmd():
    """Show system health & all stats."""
    print_header()
    stats = get_stats(); cs = cache_stats(); s = scheduler.stats(); ps = pbt.stats()
    ceo_counts = ceo_execution_breakdown()
    at = agent_tracker.stats()
    oc = org_chart.total_count()
    grid = Table.grid(padding=1)
    grid.add_column(style="bold cyan", width=18); grid.add_column(width=30)
    grid.add_column(style="bold cyan", width=18); grid.add_column(width=30)
    grid.add_row("Runs", str(stats['total_runs']), "Cache", f"{cs['size']} entries ({cs['hit_rate']:.0%} hit)")
    grid.add_row("Success Rate", f"{stats['success_rate']:.0%}", "Schedule", f"{s['queue_size']} queued, {s['completed']} done")
    grid.add_row("Avg Confidence", f"{stats['avg_confidence']:.0%}", "PBT Gen", str(ps['generation']))
    grid.add_row("Avg Tokens", f"{stats['avg_tokens']:.0f}", "Stop Light", status_tag(stop_light.status()=="green","green",stop_light.status()))
    grid.add_row("ELO Agents", str(len(stats['elo_ratings'])), "Council", f"{council.num_ceos} CEOs ({council.profile})")
    grid.add_row("Replay Queue", str(stats['replay_queue']), "Budget", "active" if stats['total_runs']>0 else "idle")
    grid.add_row("Org Chart", f"{oc['ceos']} CEOs, {oc['managers']} Mgrs, {oc['employees']} Emps", "API Configs", str(len(api_configs)))
    grid.add_row("Tracked Agents", str(at['total']), "Avg ELO", str(at['avg_elo']))
    console.print(Panel(grid, box=box.ASCII, border_style="cyan", title="[bold]System Status[/bold]"))
    if ceo_counts:
        t = Table(box=box.ASCII, border_style="dim", title="CEO Execution Breakdown")
        t.add_column("CEO", style="cyan"); t.add_column("Calls")
        for ceo_id, count in sorted(ceo_counts.items(), key=lambda x: -x[1]):
            t.add_row(ceo_id, str(count))
        console.print(t)

@cli.command()
def council_cmd():
    """Show the Executive Council with org chart."""
    print_header()
    console.print(Panel(
        Text.from_markup(f"[bold]{council.num_ceos} CEOs[/bold]  •  [dim]{council.profile} profile  •  [dim]{len(api_configs)} API configs[/dim]"),
        box=box.ASCII, border_style="cyan"
    ))
    table = Table(box=box.ASCII, border_style="blue", title="Executive Council")
    table.add_column("CEO", style="bold cyan", no_wrap=True); table.add_column("Name", style="white")
    table.add_column("Managers"); table.add_column("APIs"); table.add_column("Budget")
    for c in council.list_ceos():
        table.add_row(c['id'], c['name'], str(c['managers']), str(c['api_count']), c['budget'])
    console.print(table)
    mind = org_chart.get_mind_map()
    if mind:
        tree_display = Tree("[bold cyan]Org Chart[/bold cyan]")
        for ceo_id, ceo_data in mind.items():
            ceo_branch = tree_display.add(f"[bold green]{ceo_data['name']}[/bold green] [dim]({ceo_id})[/dim]")
            for mgr_id, mgr_data in ceo_data.get("managers", {}).items():
                mgr_branch = ceo_branch.add(f"[yellow]{mgr_data['name']}[/yellow] [dim]({mgr_id})[/dim]")
                for emp in mgr_data.get("employees", []):
                    emp_status = "🟢" if emp["status"]=="idle" else "🟡"
                    mgr_branch.add(f"{emp_status} [white]{emp['name']}[/white] [dim]({emp['role']})[/dim]")
        console.print(tree_display)

@cli.command()
@click.argument("thought")
@click.option("--tags", "-t", multiple=True, help="Tags")
@click.option("--query", "-q", default="", help="Query related thoughts")
def thought_cmd(thought, tags, query):
    """Inject a thought into Thought VDB."""
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
            t.add_column("Confidence"); t.add_column("Thought")
            for r in results:
                t.add_row(f"{r['confidence']:.0%}", r['thought'][:80])
            console.print(t)

@cli.command()
@click.option("--query", "-q", default="", help="Search query")
def memory_cmd(query):
    """Query L1 memory & Thought VDB."""
    print_header()
    l1r = l1_memory.recall(query or "general")
    tvdb = thought_vdb.query(query or "general")
    if l1r:
        t = Table(box=box.ASCII, border_style="cyan", title="L1 Memory")
        t.add_column("Score"); t.add_column("Content")
        for r in l1r:
            t.add_row(f"{r['score']:.2f}", r['value'][:80])
        console.print(t)
    if tvdb:
        t = Table(box=box.ASCII, border_style="magenta", title="Thought VDB")
        t.add_column("Conf."); t.add_column("Thought"); t.add_column("Tags")
        for r in tvdb:
            tags_str = ", ".join(r.get('tags',[])[:2]) if r.get('tags') else ""
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
    t.add_column("Metric"); t.add_column("Value")
    t.add_row("Queued", str(s['queue_size'])); t.add_row("Running", str(s['running']))
    t.add_row("Completed", str(s['completed'])); t.add_row("Budget Spent", f"{s['budget_spent']:.0f}")
    console.print(t)
    next_tasks = scheduler.next_up(5)
    if next_tasks:
        n = Table(box=box.ASCII, border_style="dim", title="Next Up")
        n.add_column("Urgency"); n.add_column("Task"); n.add_column("Agent")
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
        Text.from_markup(f"[bold]Generation {gen}[/bold]\nPopulation: [cyan]{s['population']}[/cyan]\nBest Fitness: [green]{s['best_fitness']:.3f}[/green]\nAvg Fitness: [yellow]{s['avg_fitness']:.3f}[/yellow]"),
        box=box.ASCII, border_style="green", title="[bold]Evolution[/bold]"
    ))

@cli.command()
@click.option("--action", type=click.Choice(["status","pause","resume"]), default="status")
def safety(action):
    """Safety system controls."""
    print_header()
    if action == "status":
        table = Table(box=box.ASCII, border_style="red")
        table.add_column("System", style="bold red"); table.add_column("Status")
        table.add_row("Stop Light", status_tag(stop_light.status()=="green",stop_light.status(),stop_light.status()))
        table.add_row("Violations", "0"); table.add_row("Kill Switch", "(inactive)")
        table.add_row("Circuit Breaker", status_tag(stop_light.status()=="green","closed","open"))
        console.print(table)
    elif action == "pause":
        stop_light.set_red()
        console.print("[red]⚠ Paused (red light)[/red]")
    elif action == "resume":
        stop_light.set_green()
        console.print("[green]✓ Resumed (green light)[/green]")

# === NEW: ORG CHART COMMANDS ===
@cli.group()
def org():
    """Manage corporate org chart hierarchy."""

@org.command(name="show")
def org_show():
    """Show full org chart as mind map."""
    print_header()
    mind = org_chart.get_mind_map()
    if not mind:
        console.print("[yellow]No CEOs in org chart. Use 'maik org add-ceo' to start.[/yellow]")
        return
    tree_display = Tree("[bold cyan]🏢 Corporate Org Chart[/bold cyan]")
    for ceo_id, ceo_data in mind.items():
        ceo_branch = tree_display.add(f"[bold green]👤 {ceo_data['name']}[/bold green] [dim]({ceo_id})[/dim]")
        mgrs = ceo_data.get("managers", {})
        if not mgrs:
            ceo_branch.add("[dim]No managers yet[/dim]")
        for mgr_id, mgr_data in mgrs.items():
            mgr_branch = ceo_branch.add(f"[yellow]👤 {mgr_data['name']}[/yellow] [dim]({mgr_id})[/dim]")
            emps = mgr_data.get("employees", [])
            if not emps:
                mgr_branch.add("[dim]No employees yet[/dim]")
            for emp in emps:
                st = "🟢" if emp["status"]=="idle" else "🟡"
                mgr_branch.add(f"{st} [white]{emp['name']}[/white] [dim]({emp['role']}, {emp['tasks']} tasks)[/dim]")
    console.print(tree_display)

@org.command()
@click.argument("ceo_id")
@click.argument("name")
def add_ceo(ceo_id, name):
    """Add a CEO to the org chart."""
    oc = org_chart.add_ceo(ceo_id, name)
    console.print(f"[green]+[/green] CEO [bold]{name}[/bold] ({ceo_id}) added to org chart")
    c = council.add_ceo(name, ["general","custom"])
    console.print(f"[green]+[/green] Also added to Executive Council: [bold]{c.name}[/bold] (ID: {c.id}) to add managers, use ceo_id: [cyan]{c.id}[/cyan]")

@org.command()
@click.argument("ceo_id")
def remove_ceo(ceo_id):
    """Remove a CEO from org chart."""
    if org_chart.remove_ceo(ceo_id):
        council.remove_ceo(ceo_id)
        console.print(f"[red]-[/red] CEO [bold]{ceo_id}[/bold] removed")
    else:
        console.print(f"[red]CEO {ceo_id} not found[/red]")

@org.command()
@click.argument("ceo_id")
@click.argument("mgr_id")
@click.argument("mgr_name")
def add_manager(ceo_id, mgr_id, mgr_name):
    """Add a manager under a CEO."""
    m = org_chart.add_manager(ceo_id, mgr_id, mgr_name)
    if m:
        agent_tracker.register(mgr_id, "manager")
        console.print(f"[green]+[/green] Manager [bold]{mgr_name}[/bold] ({mgr_id}) under {ceo_id}")
    else:
        console.print(f"[red]CEO {ceo_id} not found[/red]")

@org.command()
@click.argument("ceo_id")
@click.argument("mgr_id")
def remove_manager(ceo_id, mgr_id):
    """Remove a manager."""
    if org_chart.remove_manager(ceo_id, mgr_id):
        console.print(f"[red]-[/red] Manager [bold]{mgr_id}[/bold] removed from {ceo_id}")
    else:
        console.print(f"[red]Not found[/red]")

@org.command()
@click.argument("ceo_id")
@click.argument("mgr_id")
@click.argument("emp_id")
@click.argument("emp_name")
@click.option("--role", "-r", default="employee", help="Role")
def add_employee(ceo_id, mgr_id, emp_id, emp_name, role):
    """Add an employee under a manager."""
    e = org_chart.add_employee(ceo_id, mgr_id, emp_id, emp_name, role)
    if e:
        agent_tracker.register(emp_id, role)
        console.print(f"[green]+[/green] Employee [bold]{emp_name}[/bold] ({emp_id}, {role}) under {mgr_id}")
    else:
        console.print(f"[red]CEO {ceo_id} or Manager {mgr_id} not found[/red]")

@org.command()
@click.argument("ceo_id")
@click.argument("mgr_id")
@click.argument("emp_id")
def remove_employee(ceo_id, mgr_id, emp_id):
    """Remove an employee."""
    if org_chart.remove_employee(ceo_id, mgr_id, emp_id):
        console.print(f"[red]-[/red] Employee [bold]{emp_id}[/bold] removed")
    else:
        console.print(f"[red]Not found[/red]")

# === WORKFLOW COMMANDS ===
@cli.group()
def workflow():
    """Manage and run workflow chains."""

@workflow.command(name="list")
def workflow_list():
    """List all workflow chains."""
    print_header()
    table = Table(box=box.ASCII, border_style="cyan", title="Workflow Chains")
    table.add_column("Chain ID", style="bold cyan"); table.add_column("Name"); table.add_column("Steps")
    for cid, chain in WORKFLOW_CHAINS.items():
        table.add_row(cid, chain["name"], str(len(chain["steps"])))
    console.print(table)

@workflow.command()
@click.argument("chain_id")
def show(chain_id):
    """Show workflow chain details."""
    chain = WORKFLOW_CHAINS.get(chain_id)
    if not chain:
        console.print(f"[red]Chain '{chain_id}' not found[/red]")
        return
    print_header()
    console.print(Panel(f"[bold]{chain['name']}[/bold] — {len(chain['steps'])} steps", box=box.ASCII, border_style="cyan"))
    for i, step in enumerate(chain["steps"]):
        panel = Panel(
            f"[cyan]{step.role}[/cyan]\n[dim]{step.system_prompt[:120]}[/dim]",
            box=box.ASCII, border_style="blue",
            title=f"Step {i+1} ({step.id})", title_align="left"
        )
        console.print(panel)

@workflow.command()
@click.argument("chain_id")
@click.argument("task")
def run(chain_id, task):
    """Run a workflow chain (simulated)."""
    chain = WORKFLOW_CHAINS.get(chain_id)
    if not chain:
        console.print(f"[red]Chain '{chain_id}' not found[/red]")
        return
    print_header()
    console.print(f"[bold]Running:[/bold] {chain['name']} on [italic]'{task[:60]}'[/italic]")
    with console.status("[cyan]Running workflow...[/cyan]", spinner="dots"):
        result = workflow_engine.run_all_simulated(chain_id, task)
    table = Table(box=box.ASCII, border_style="green", title="Workflow Results")
    table.add_column("Step", style="cyan"); table.add_column("Role"); table.add_column("Output")
    for i, (step, output) in enumerate(zip(result["steps"], result["outputs"])):
        table.add_row(f"{i+1}", step["role"], output[:80])
    console.print(table)
    console.print(f"[dim]Run ID: {result['run_id']}  Duration: {result['duration_s']:.2f}s  Status: {result['status']}[/dim]")

@workflow.command()
def runs():
    """List active/recent workflow runs."""
    runs_list = workflow_engine.list_runs()
    if not runs_list:
        console.print("[yellow]No workflow runs yet[/yellow]")
        return
    table = Table(box=box.ASCII, border_style="cyan", title="Workflow Runs")
    table.add_column("Run ID"); table.add_column("Chain"); table.add_column("Task")
    table.add_column("Step"); table.add_column("Status")
    for r in runs_list[:10]:
        table.add_row(r["id"], r["chain"], r["task"], str(r["step"]), r["status"])
    console.print(table)

# === API MANAGEMENT ===
@cli.group()
def api():
    """Manage API configurations."""

@api.command(name="list")
def api_list():
    """List all API configurations."""
    print_header()
    table = Table(box=box.ASCII, border_style="cyan", title=f"API Configurations ({len(api_configs)})")
    table.add_column("ID", style="bold cyan"); table.add_column("Provider"); table.add_column("Model")
    table.add_column("Key Prefix"); table.add_column("Enabled")
    for a in api_configs:
        table.add_row(a.id, a.provider, a.model, a.key_prefix + "..." if a.key_prefix else "-",
                     status_tag(a.enabled, "yes", "no"))
    console.print(table)

@api.command()
@click.argument("provider")
@click.argument("model")
@click.option("--key-prefix", "-k", default="", help="API key prefix")
@click.option("--id", "api_id", default="", help="Custom ID")
def add(provider, model, key_prefix, api_id):
    """Add a new API configuration."""
    new_id = api_id or f"api-{len(api_configs)+1}"
    ap = APIConfig(new_id, provider, model, key_prefix)
    api_configs.append(ap)
    console.print(f"[green]+[/green] API added: [bold]{provider}/{model}[/bold] ({new_id}) [dim](total: {len(api_configs)})[/dim]")

@api.command()
@click.argument("api_id")
def remove(api_id):
    """Remove an API configuration."""
    for i, a in enumerate(api_configs):
        if a.id == api_id:
            api_configs.pop(i)
            console.print(f"[red]-[/red] API [bold]{api_id}[/bold] removed")
            return
    console.print(f"[red]API '{api_id}' not found[/red]")

@api.command()
@click.argument("api_id")
def toggle(api_id):
    """Toggle API enabled/disabled."""
    for a in api_configs:
        if a.id == api_id:
            a.enabled = not a.enabled
            console.print(f"[cyan]∼[/cyan] API [bold]{api_id}[/bold] toggled to {'enabled' if a.enabled else 'disabled'}")
            return
    console.print(f"[red]API '{api_id}' not found[/red]")

# === AGENT MANAGEMENT ===
@cli.group()
def agents():
    """Manage and view agent performance."""

@agents.command(name="list")
def agent_list():
    """List all tracked agents."""
    stats = agent_tracker.stats()
    table = Table(box=box.ASCII, border_style="cyan", title=f"Tracked Agents ({stats['total']})")
    table.add_column("Agent ID", style="bold cyan"); table.add_column("Role"); table.add_column("ELO")
    table.add_column("Tasks"); table.add_column("Success %"); table.add_column("Status")
    for aid, info in stats["agents"].items():
        table.add_row(aid, info["role"], str(info["elo"]), str(info["tasks"]),
                     f"{info['success_rate']:.0%}", info["status"])
    console.print(table)

@agents.command()
def leaderboard():
    """Show agent ELO leaderboard."""
    board = agent_tracker.leaderboard()
    table = Table(box=box.ASCII, border_style="gold", title="🏆 Agent ELO Leaderboard")
    table.add_column("#"); table.add_column("Agent", style="bold cyan"); table.add_column("Role")
    table.add_column("ELO", style="yellow"); table.add_column("Tasks"); table.add_column("Success Rate")
    for i, a in enumerate(board, 1):
        medal = {1:"🥇",2:"🥈",3:"🥉"}.get(i, f"{i}.")
        table.add_row(medal, a["id"], a["role"], str(a["elo"]), str(a["tasks"]), f"{a['success_rate']:.0%}")
    console.print(table)

@agents.command()
@click.argument("agent_id")
@click.argument("role")
def register(agent_id, role):
    """Register a new agent for tracking."""
    agent_tracker.register(agent_id, role)
    console.print(f"[green]+[/green] Agent [bold]{agent_id}[/bold] registered as {role}")

# === PROMPT SELECTOR ===
@cli.group()
def prompt():
    """Manage AI system prompts."""

@prompt.command(name="list")
def prompt_list():
    """List all available prompt roles."""
    print_header()
    roles = prompt_selector.list_roles()
    custom = prompt_selector.list_custom()
    table = Table(box=box.ASCII, border_style="cyan", title="Prompt Templates")
    table.add_column("Role", style="bold cyan"); table.add_column("Template (preview)")
    table.add_column("Customized")
    for role in roles:
        is_custom = "yes" if role in custom else "no"
        template = PROMPT_TEMPLATES.get(role, "")[:60]
        table.add_row(role, template, status_tag(role in custom, "yes", "no"))
    console.print(table)

@prompt.command()
@click.argument("role")
@click.argument("prompt_text")
def set(role, prompt_text):
    """Set a custom prompt for a role."""
    prompt_selector.set_custom_prompt(role, prompt_text)
    console.print(f"[green]+[/green] Custom prompt set for role [bold]{role}[/bold]")

@prompt.command()
@click.argument("role")
def reset(role):
    """Reset a role to default prompt."""
    prompt_selector.reset_role(role)
    console.print(f"[cyan]∼[/cyan] Role [bold]{role}[/bold] reset to default")

@prompt.command()
@click.argument("role")
@click.argument("task")
@click.option("--prev", "-p", default="", help="Previous output")
def preview(role, task, prev):
    """Preview what prompt would be selected."""
    result = prompt_selector.select_prompt(role, task, prev)
    console.print(Panel(result[:2000], box=box.ASCII, border_style="cyan", title=f"Prompt for: {role}"))

# === BUDGET MANAGEMENT ===
@cli.group()
def budget():
    """Manage token budgets."""

@budget.command(name="show")
def budget_show():
    """Show budget breakdown."""
    print_header()
    table = Table(box=box.ASCII, border_style="green", title="Budget Breakdown")
    table.add_column("CEO", style="bold cyan"); table.add_column("Budget"); table.add_column("Used")
    table.add_column("Remaining"); table.add_column("% Left"); table.add_column("Mode")
    for ceo in council.ceo_list:
        b = council.budget_for(ceo.id)
        table.add_row(ceo.id, f"{b.total:,}", f"{b.used:,}", f"{b.remaining:,}",
                     f"{b.remaining_pct*100:.0f}%", b.mode())
    console.print(table)

@budget.command()
@click.argument("ceo_id")
@click.argument("amount", type=int)
def set_cmd(ceo_id, amount):
    """Set CEO token budget."""
    b = council.budget_for(ceo_id)
    if b:
        b.total = amount
        console.print(f"[cyan]∼[/cyan] Budget for [bold]{ceo_id}[/bold] set to {amount:,}")
    else:
        console.print(f"[red]CEO '{ceo_id}' not found[/red]")

# === LIBRARY COMMANDS ===
@cli.group()
def library():
    """Manage corporate library."""

@library.command(name="stats")
def lib_stats():
    """Show library statistics."""
    s = corp_library.stats()
    table = Table(box=box.ASCII, border_style="cyan", title="Corporate Library")
    table.add_column("Metric", style="bold"); table.add_column("Value")
    table.add_row("Total Libraries", str(s['total_libraries']))
    table.add_row("Total Agents", str(s['total_agents']))
    table.add_row("Total Usage", str(s['total_usage']))
    table.add_row("Avg Quality", f"{s['avg_quality']:.2f}")
    console.print(table)

@library.command()
@click.argument("query")
@click.option("--domain", "-d", default="")
def search(query, domain):
    """Search the corporate library."""
    results = corp_library.search(query, domain)
    if not results:
        console.print("[yellow]No results found[/yellow]")
        return
    table = Table(box=box.ASCII, border_style="cyan", title=f"Library Search: '{query}'")
    table.add_column("ID"); table.add_column("Name"); table.add_column("Domain")
    table.add_column("Author"); table.add_column("Quality"); table.add_column("Usage")
    for r in results:
        table.add_row(r["id"], r["name"], r["domain"], r["author"],
                     f"{r['quality']:.2f}", str(r["usage"]))
    console.print(table)

# === PERMISSION COMMANDS ===
@cli.group()
def permission():
    """Manage permissions."""

@permission.command(name="list")
def perm_list():
    """List all permission roles."""
    roles = ["ceo", "exec", "manager", "specialist"]
    table = Table(box=box.ASCII, border_style="cyan", title="Permission Roles")
    table.add_column("Role", style="bold cyan"); table.add_column("Permissions")
    for role in roles:
        perms = ", ".join(sorted(perm_system._permissions.get(role, set())))
        table.add_row(role, perms)
    console.print(table)

@permission.command()
@click.argument("role")
@click.argument("action")
def check(role, action):
    """Check if a role has a permission."""
    allowed = perm_system.check(role, action)
    console.print(f"[bold]{role}[/bold] can[{'not' if not allowed else ''}] [cyan]{action}[/cyan]: {status_tag(allowed, 'allowed', 'denied')}")

# === INTERACTIVE MODE ===
@cli.command()
@click.pass_context
def interactive(ctx):
    """Interactive REPL mode with all features."""
    print_header()
    console.print(Panel(
        "[bold cyan]MAIK Interactive[/bold cyan]\n"
        "Type any question or use commands below.\n"
        "[dim]/route <q>  /execute <q>  /status  /council  /org  /workflow  /api  /agents  /evolve  /schedule  /memory  /thought  /safety  /budget  /library  /permission  /prompt  /help  exit[/dim]",
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
                console.print(Panel(Text.from_markup(f"[bold]{r['ceo_name']}[/bold]  ->  [cyan]{r['expert']}[/cyan] ({r['confidence']:.0%})"), box=box.ASCII, border_style="blue"))
            elif sub == "execute" and rest:
                with console.status("[cyan]Executing...[/cyan]"):
                    result = execute(rest)
                console.print(Panel(Markdown(result['solution'][:2000]), box=box.ASCII, border_style="green"))
            elif sub in ("status", "st"):
                stats = get_stats()
                grid = Table.grid(padding=1)
                grid.add_row("Runs", str(stats['total_runs']), "Success", f"{stats['success_rate']:.0%}")
                grid.add_row("Cache", f"{cache_stats()['size']} entries", "Council", f"{council.num_ceos} CEOs")
                grid.add_row("APIs", str(len(api_configs)), "Agents", str(agent_tracker.stats()['total']))
                console.print(Panel(grid, box=box.ASCII, border_style="cyan"))
            elif sub == "council":
                for c in council.list_ceos():
                    console.print(f"  [cyan]{c['id']:<18}[/cyan] {c['name']:<25} [dim]{c['managers']} mgrs[/dim]")
            elif sub == "org":
                mind = org_chart.get_mind_map()
                if mind:
                    t = Tree("[cyan]Org Chart[/cyan]")
                    for cid, cd in mind.items():
                        tb = t.add(f"[green]{cd['name']}[/green]")
                        for mid, md in cd.get("managers",{}).items():
                            mb = tb.add(f"[yellow]{md['name']}[/yellow]")
                            for e in md.get("employees",[]):
                                mb.add(f"[white]{e['name']}[/white]")
                    console.print(t)
                else:
                    console.print("[yellow]Org chart is empty[/yellow]")
            elif sub == "workflow":
                for cid, chain in WORKFLOW_CHAINS.items():
                    console.print(f"  [cyan]{cid:<16}[/cyan] {chain['name']:<20} [dim]{len(chain['steps'])} steps[/dim]")
            elif sub == "api":
                for a in api_configs:
                    en = "✓" if a.enabled else "✗"
                    console.print(f"  {en} [cyan]{a.id:<8}[/cyan] {a.provider}/{a.model}")
            elif sub == "agents":
                board = agent_tracker.leaderboard(5)
                for a in board:
                    console.print(f"  [cyan]{a['id']:<16}[/cyan] ELO: {a['elo']:<6} {a['success_rate']:.0%} ({a['status']})")
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
            elif sub == "safety":
                st = stop_light.status()
                console.print(f"Stop Light: {status_tag(st=='green',st,st)}")
            elif sub == "budget":
                for ceo in council.ceo_list:
                    b = council.budget_for(ceo.id)
                    console.print(f"  [cyan]{ceo.id:<18}[/cyan] {b.remaining:,}/{b.total:,}")
            elif sub == "prompt":
                for role in prompt_selector.list_roles():
                    console.print(f"  [cyan]{role:<16}[/cyan] {PROMPT_TEMPLATES.get(role,'')[:50]}")
            elif sub == "help":
                console.print("[cyan]/route[/cyan] [cyan]/execute[/cyan] [cyan]/status[/cyan] [cyan]/council[/cyan] [cyan]/org[/cyan] [cyan]/workflow[/cyan] [cyan]/api[/cyan] [cyan]/agents[/cyan] [cyan]/evolve[/cyan] [cyan]/schedule[/cyan] [cyan]/memory[/cyan] [cyan]/thought[/cyan] [cyan]/safety[/cyan] [cyan]/budget[/cyan] [cyan]/library[/cyan] [cyan]/permission[/cyan] [cyan]/prompt[/cyan]")
            else:
                console.print(f"[red]Unknown: /{sub}[/red]")
        else:
            budget = TokenBudget(total=100000)
            with console.status("[cyan]Routing...[/cyan]", spinner="dots"):
                r = route(line, "", budget)
            console.print(f"[bold]{r['ceo_name']}[/bold]  ->  [cyan]{r['expert']}[/cyan]")
            with console.status("[cyan]Executing...[/cyan]"):
                result = execute(line, "", budget)
            console.print(Panel(Markdown(result['solution'][:2000]), box=box.ASCII, border_style="green"))
            learn(line, result['solution'][:500], "success", result['agents_used'], result['confidence'], 0, 0)

if __name__ == "__main__":
    cli()
