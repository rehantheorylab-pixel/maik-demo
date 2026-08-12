#!/usr/bin/env python3
"""MAIK CLI — full-featured terminal interface with all management capabilities."""
import sys, os, json, time, threading
from datetime import datetime
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
from evolution_engine import pbt as pbt_engine
from safety_engine import stop_light
from boolean_engine import voter
from meta_controller import prompt_selector, workflow_engine, meta_agent, PROMPT_TEMPLATES
from corporate_engine import org_chart, agent_tracker, corp_library, perm_system
from governance_engine import voting_engine, logic_probe, sentinel, sheriff, session_manager, cognitive_controls, pbt_tracker, training
from cognitive_engine import incubation as incubation_engine
from session_compactor import session_archiver, summary_generator, agent_context_builder, compaction_manager
from file_access_agent import file_agent
from browser_agent import browser, screen_reader
from computer_use_agent import computer
from code_analysis_engine import analyzer
from web_research_agent import researcher
from pixel_vision import pixel_vision
from api_router import router as api_router
from cli_plugin import cli_plugins
from github_integration import github
from auth_manager import auth
from agent_tree import agent_tree, AgentStatus
from mindmap_ui import render_mind_map_json, render_tree_text
from unified_vision import unified_vision
from git_engine import git_engine
from coding_agent import coding_agent
from sysmon import sysmon
from agent_memory import agent_memory
from tool_chain import tool_chain
from ai_enhance import ai_enhance
from delta_viewer import delta_viewer

# Alias for UI compatibility
vote_manager = voting_engine
incubation = incubation_engine

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
    stats = get_stats(); cs = cache_stats(); s = scheduler.stats(); ps = pbt_engine.stats()
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
        gen = pbt_engine.evolve()
        s = pbt_engine.stats()
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

    def add_nodes(branch, children_dict, depth=0):
        for cid, cdata in children_dict.items():
            ad = cdata.get("agent_data", {})
            st = "🟢" if ad.get("status")=="idle" else "🟡"
            subs = cdata.get("sub_agents", 0)
            descs = cdata.get("descendants", 0)
            count_str = f" [{subs} direct, {descs} total]" if descs else ""
            nm = cdata.get("name", cid)
            tp = cdata.get("type", "?")
            elo = ad.get("elo", 1000)
            elo_str = f" ELO:{elo}" if elo != 1000 else ""
            label = f"{st} [bold{'green' if tp=='ceo' else 'yellow' if tp=='manager' else 'cyan' if tp=='agent' else 'white'}]{nm}[/bold{'green' if tp=='ceo' else 'yellow' if tp=='manager' else 'cyan' if tp=='agent' else 'white'}] [dim]({cid}, {tp}{elo_str})[/dim]{count_str}"
            child_branch = branch.add(label)
            if cdata.get("children"):
                add_nodes(child_branch, cdata["children"], depth+1)

    for ceo_id, ceo_data in mind.items():
        ceo_branch = tree_display.add(f"[bold green]👤 {ceo_data['name']}[/bold green] [dim]({ceo_id})[/dim] — {ceo_data.get('descendants',0)} total under")
        if ceo_data.get("children"):
            add_nodes(ceo_branch, ceo_data["children"])
        else:
            ceo_branch.add("[dim]No sub-agents yet. Use 'maik org add-sub-agent' to add.[/dim]")
    counts = org_chart.total_count()
    console.print(f"[dim]Total: {counts['total']} nodes  •  {counts['ceos']} CEOs  •  {counts['managers']} Managers  •  {counts['employees']} Employees  •  {counts['agents']} Agents  •  {counts['sub_agents']} Sub-agents[/dim]")
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
@click.argument("parent_id")
@click.argument("child_id")
@click.argument("child_name")
@click.option("--type", "-t", default="agent", help="Node type: agent, sub-agent, worker")
def add_sub_agent(parent_id, child_id, child_name, type):
    """Add a sub-agent under any node (arbitrary depth)."""
    n = org_chart.add_child(parent_id, child_id, child_name, type)
    if n:
        console.print(f"[green]+[/green] Sub-agent [bold]{child_name}[/bold] ({child_id}, {type}) under {parent_id}")
    else:
        console.print(f"[red]Parent {parent_id} not found[/red]")

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
def vote():
    """Voting and consensus system."""

@vote.command(name="list")
def vote_list():
    """List open votes."""
    print_header()
    votes = voting_engine.list_open()
    if not votes:
        console.print("[yellow]No open votes[/yellow]"); return
    t = Table(box=box.ASCII, border_style="cyan", title="Open Votes")
    t.add_column("ID", style="bold cyan"); t.add_column("Topic"); t.add_column("Options"); t.add_column("Votes")
    for v in votes:
        t.add_row(v["id"], v["topic"][:40], ", ".join(v.get("options",["?"])), str(v["votes"]))
    console.print(t)

@vote.command()
@click.argument("topic")
@click.argument("options")
def create(topic, options):
    """Create a vote. Options as comma-separated."""
    opts = [o.strip() for o in options.split(",")]
    vid = voting_engine.create_vote(topic, "", opts, "cli")
    console.print(f"[green]+[/green] Vote created: [bold]{topic}[/bold] ({vid})")

@vote.command()
@click.argument("vote_id")
@click.argument("voter")
@click.argument("choice")
def cast(vote_id, voter, choice):
    """Cast a vote."""
    if voting_engine.cast(vote_id, voter, choice):
        console.print(f"[green]✓[/green] {voter} voted for [bold]{choice}[/bold]")
    else:
        console.print(f"[red]Failed to cast vote. Check vote ID and choice.[/red]")

@vote.command()
@click.argument("vote_id")
def close(vote_id):
    """Close a vote and show results."""
    result = voting_engine.close(vote_id)
    if not result:
        console.print(f"[red]Vote '{vote_id}' not found[/red]"); return
    t = Table(box=box.ASCII, border_style="green", title=f"Results: {result['topic']}")
    t.add_column("Option"); t.add_column("Votes"); t.add_column("Weighted")
    for opt in result["options"] if "options" in result else result["counts"]:
        t.add_row(opt, str(result["counts"].get(opt,0)), f"{result['weighted'].get(opt,0):.1f}")
    t.add_row("[bold]Winner[/bold]", f"[green]{result['winner']}[/green]", "")
    console.print(t)

@vote.command()
def results():
    """Show all votes and results."""
    all_v = voting_engine.all_votes()
    if not all_v:
        console.print("[yellow]No votes yet[/yellow]"); return
    t = Table(box=box.ASCII, border_style="cyan", title="All Votes")
    t.add_column("ID"); t.add_column("Topic"); t.add_column("Status"); t.add_column("Total")
    for v in all_v:
        t.add_row(v["id"], v["topic"][:30], v["status"], str(v["total"]))
    console.print(t)

@cli.group()
def probe():
    """Logic probe — track contradictions & flagged thoughts."""

@probe.command(name="list")
def probe_list():
    """List all probed thoughts."""
    print_header()
    pts = logic_probe.all_thoughts()
    if not pts:
        console.print("[yellow]No probed thoughts[/yellow]"); return
    t = Table(box=box.ASCII, border_style="magenta", title="Probed Thoughts")
    t.add_column("ID"); t.add_column("Thought"); t.add_column("Agent")
    t.add_column("Category"); t.add_column("Severity"); t.add_column("Flagged"); t.add_column("Resolved")
    for p in pts:
        t.add_row(p["id"], p["thought"][:60], p["agent"], p["category"], f"{p['severity']:.2f}",
                 status_tag(p["flagged"], "⚠", "✓"), status_tag(p["resolved"], "✓", ""))
    console.print(t)

@probe.command()
def flagged():
    """Show flagged contradictions."""
    print_header()
    flagged_list = logic_probe.flagged_thoughts()
    if not flagged_list:
        console.print("[green]No flagged thoughts[/green]"); return
    t = Table(box=box.ASCII, border_style="red", title=f"🚩 Flagged Thoughts ({len(flagged_list)})")
    t.add_column("ID"); t.add_column("Thought"); t.add_column("Agent"); t.add_column("Severity"); t.add_column("Resolved")
    for p in flagged_list:
        t.add_row(p["id"], p["thought"][:60], p["agent"], f"{p['severity']:.2f}", status_tag(p["resolved"], "yes", "no"))
    console.print(t)

@probe.command()
@click.argument("thought")
@click.argument("agent")
@click.option("--category", "-c", default="general")
@click.option("--severity", "-s", default=0.3, type=float)
def add(thought, agent, category, severity):
    """Add a thought to the probe."""
    pt = logic_probe.probe(thought, agent, category, severity)
    flag = "⚠ FLAGGED" if pt.flagged else "✓"
    console.print(f"[green]+[/green] Thought probed: [bold]{thought[:60]}[/bold] {flag}")

@probe.command()
@click.argument("thought_id")
def resolve(thought_id):
    """Resolve a flagged thought."""
    logic_probe.resolve(thought_id)
    console.print(f"[green]✓[/green] Thought {thought_id} resolved")

@cli.group()
def sentinel_cmd():
    """Sentinel system monitor."""

@sentinel_cmd.command(name="status")
def sentinel_status():
    """Show sentinel health status."""
    print_header()
    h = sentinel.health()
    t = Table(box=box.ASCII, border_style="cyan", title="Sentinel Health")
    t.add_column("Metric", style="bold"); t.add_column("Value")
    t.add_row("Status", status_tag(h["status"] == "healthy", h["status"], h["status"]))
    t.add_row("Uptime", f"{h['uptime']:.0f}s"); t.add_row("Active Agents", str(h["agents_active"]))
    t.add_row("CPU", f"{h['cpu']:.1f}%"); t.add_row("Memory", f"{h['memory']:.1f}%")
    t.add_row("Recent Alerts", str(h["alerts"])); t.add_row("Total Alerts", str(h["total_alerts"]))
    console.print(t)

@sentinel_cmd.command()
def alerts():
    """Show recent sentinel alerts."""
    al = sentinel.recent_alerts()
    if not al:
        console.print("[green]No recent alerts[/green]"); return
    t = Table(box=box.ASCII, border_style="yellow", title="Recent Alerts")
    t.add_column("Level", style="bold"); t.add_column("Source"); t.add_column("Message"); t.add_column("Time")
    for a in al:
        t.add_row(a["level"], a["source"], a["message"], a["time"])
    console.print(t)

@sentinel_cmd.command()
def history():
    """Show sentinel health history."""
    hist = sentinel.history(15)
    if not hist:
        console.print("[yellow]No history yet[/yellow]"); return
    t = Table(box=box.ASCII, border_style="dim", title="Health History (last 15)")
    t.add_column("Time"); t.add_column("Status"); t.add_column("Agents"); t.add_column("CPU"); t.add_column("Memory")
    for h in hist:
        t.add_row(h["time"], h["status"], str(h["agents"]), f"{h['cpu']:.1f}%", f"{h['memory']:.1f}%")
    console.print(t)

@cli.group()
def sheriff_cmd():
    """Sheriff rule manager."""

@sheriff_cmd.command(name="list")
def sheriff_list():
    """List all sheriff rules."""
    print_header()
    rules = sheriff.list_rules()
    t = Table(box=box.ASCII, border_style="cyan", title=f"Sheriff Rules ({len(rules)})")
    t.add_column("ID", style="bold"); t.add_column("Name"); t.add_column("Action")
    t.add_column("Priority"); t.add_column("Enabled")
    for r in rules:
        t.add_row(r["id"], r["name"], r["action"], str(r["priority"]), status_tag(r["enabled"], "on", "off"))
    console.print(t)

@sheriff_cmd.command()
@click.argument("name")
@click.argument("description")
@click.argument("action")
@click.option("--priority", "-p", default=5, type=int)
def add_rule(name, description, action, priority):
    """Add a sheriff rule."""
    rid = sheriff.add_rule(name, description, action, priority)
    console.print(f"[green]+[/green] Rule added: [bold]{name}[/bold] ({rid})")

@sheriff_cmd.command()
@click.argument("rule_id")
def remove_rule(rule_id):
    """Remove a sheriff rule."""
    if sheriff.remove_rule(rule_id):
        console.print(f"[red]-[/red] Rule {rule_id} removed")
    else:
        console.print(f"[red]Rule {rule_id} not found[/red]")

@sheriff_cmd.command()
@click.argument("rule_id")
def toggle_rule(rule_id):
    """Toggle a sheriff rule on/off."""
    result = sheriff.toggle(rule_id)
    if result is not None:
        console.print(f"[cyan]∼[/cyan] Rule {rule_id} toggled to {'ON' if result else 'OFF'}")
    else:
        console.print(f"[red]Rule {rule_id} not found[/red]")

@cli.group()
def session():
    """Session manager."""

@session.command(name="start")
@click.argument("label", default="")
def session_start(label):
    """Start a new session."""
    sid = session_manager.start(label)
    console.print(f"[green]+[/green] Session started: [bold]{label or sid}[/bold] ({sid})")

@session.command()
@click.argument("session_id")
def end(session_id):
    """End a session."""
    session_manager.end(session_id)
    console.print(f"[cyan]∼[/cyan] Session {session_id} ended")

@session.command(name="active")
def session_active():
    """Show active session."""
    a = session_manager.active()
    if a:
        console.print(Panel(Text.from_markup(f"Active: [bold]{a['label']}[/bold] ({a['id']})\nTasks: {a['tasks']}  Success: {a['rate']}"), box=box.ASCII, border_style="cyan"))
    else:
        console.print("[yellow]No active session[/yellow]")

@session.command(name="list")
def session_list():
    """List all sessions."""
    print_header()
    sessions = session_manager.list_sessions()
    t = Table(box=box.ASCII, border_style="cyan", title="Sessions")
    t.add_column("ID"); t.add_column("Label"); t.add_column("Started"); t.add_column("Ended")
    t.add_column("Tasks"); t.add_column("Success")
    for s in sessions:
        t.add_row(s["id"][:12], s["label"], s["started"], s["ended"], str(s["tasks"]), s["success_rate"])
    console.print(t)

@cli.group()
def cognitive():
    """Cognitive controls (incubation, training, patterns)."""

@cognitive.command()
def status():
    """Show cognitive engine status."""
    print_header()
    hot = incubation.hot_ideas()
    gs = training.gold_stats()
    t = Table(box=box.ASCII, border_style="cyan", title="Cognitive Status")
    t.add_column("Metric", style="bold"); t.add_column("Value")
    t.add_row("Incubating Ideas", str(len(hot))); t.add_row("Gold Repos", str(gs["total_gold"]))
    t.add_row("Distillations", str(gs["total_distillations"])); t.add_row("Patterns", str(gs["total_patterns"]))
    t.add_row("Domains", ", ".join(gs["domains"]) if gs["domains"] else "none")
    console.print(t)

@cognitive.command()
@click.argument("idea")
@click.argument("agent")
@click.option("--source", "-s", default="")
@click.option("--tags", "-t", multiple=True)
def seed(idea, agent, source, tags):
    """Seed an idea into incubation."""
    incubation.seed(agent, idea, source, list(tags) if tags else [])
    console.print(f"[green]+[/green] Idea seeded: [bold]{idea[:60]}[/bold]")

@cognitive.command()
def hatch():
    """Hatch incubated ideas."""
    count = incubation.percolate()
    hatched = incubation.hatch_one()
    if hatched:
        console.print(f"[green]🐣[/green] Hatched: {hatched['idea'][:80]}")
    elif count:
        console.print(f"[cyan]{count}[/cyan] ideas percolated, none ready to hatch")
    else:
        console.print("[yellow]No ideas ready[/yellow]")

@cognitive.command()
@click.argument("name")
@click.argument("content")
@click.option("--domain", "-d", default="general")
def add_gold(name, content, domain):
    """Add a gold repository entry."""
    gid = training.add_gold(name, content, domain)
    console.print(f"[green]+[/green] Gold repo added: [bold]{name}[/bold] ({gid})")

@cognitive.command(name="list")
def gold_list():
    """List gold repositories."""
    gold_list_data = training.list_gold()
    if not gold_list_data:
        console.print("[yellow]No gold repos[/yellow]"); return
    t = Table(box=box.ASCII, border_style="gold", title="Gold Repositories")
    t.add_column("ID"); t.add_column("Name"); t.add_column("Domain"); t.add_column("Content")
    for g in gold_list_data:
        t.add_row(g["id"], g["name"], g["domain"], g["content"])
    console.print(t)

@cognitive.command()
@click.argument("key")
@click.argument("pattern")
def add_pattern(key, pattern):
    """Store a pattern."""
    training.store_pattern(key, pattern)
    console.print(f"[green]+[/green] Pattern stored under [bold]{key}[/bold]")

@cognitive.command()
@click.argument("key")
def get_patterns(key):
    """Get patterns for a key."""
    pats = training.get_patterns(key)
    if pats:
        console.print(f"Patterns for [bold]{key}[/bold]:")
        for p in pats:
            console.print(f"  • {p[:80]}")
    else:
        console.print(f"[yellow]No patterns for '{key}'[/yellow]")

@cli.group()
def pbt():
    """PBT evolution visualizer."""

@pbt.command(name="status")
def pbt_status():
    """Show PBT status with population."""
    print_header()
    s = pbt_engine.stats()
    t = Table(box=box.ASCII, border_style="green", title="PBT Evolution")
    t.add_column("Metric", style="bold"); t.add_column("Value")
    t.add_row("Generation", str(s["generation"])); t.add_row("Population", str(s["population"]))
    t.add_row("Best Fitness", f"{s['best_fitness']:.3f}"); t.add_row("Avg Fitness", f"{s['avg_fitness']:.3f}")
    t.add_row("History", str(s["history_length"]) + " records")
    console.print(t)

@pbt.command()
def population():
    """Show population details."""
    pop = pbt_engine.population_detail()
    if not pop:
        console.print("[yellow]No population[/yellow]"); return
    t = Table(box=box.ASCII, border_style="cyan", title=f"Population ({len(pop)})")
    t.add_column("Genome ID", style="bold"); t.add_column("Fitness"); t.add_column("Age")
    for g in pop:
        t.add_row(g["id"], f"{g['fitness']:.3f}", str(g["age"]))
    console.print(t)

@pbt.command()
def history():
    """Show fitness history."""
    fh = pbt_engine.fitness_history()
    if not fh:
        console.print("[yellow]No history yet. Run 'maik evolve' first.[/yellow]"); return
    t = Table(box=box.ASCII, border_style="dim", title="Fitness History")
    t.add_column("Gen", style="bold"); t.add_column("Best Fitness"); t.add_column("Survivors")
    for h in fh:
        t.add_row(str(h["gen"]), f"{h['best']:.3f}", str(h["survivors"]))
    console.print(t)

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

# === SESSION COMPACT COMMANDS ===
@cli.group()
def session_compact():
    """Session compaction & archival system."""

@session_compact.command(name="archive")
@click.argument("session_id")
@click.option("--label", "-l", default="")
@click.option("--messages", "-m", default="[]")
@click.option("--summary", "-s", default="")
def archive_session(session_id, label, messages, summary):
    """Archive a session to compacted MD file."""
    print_header()
    try:
        msg_list = json.loads(messages) if messages != "[]" else []
    except: msg_list = []
    if not msg_list:
        console.print("[yellow]No messages provided. Use --messages with JSON array.[/yellow]")
        return
    summary_text = summary or summary_generator.generate(msg_list)
    archived = session_archiver.archive(session_id, label or f"Session {session_id}", msg_list, summary_text)
    console.print(f"[green]+[/green] Session [bold]{session_id}[/bold] archived")
    console.print(f"  File: {archived.file_path}")
    console.print(f"  Messages: {archived.message_count}  Size: {archived.length}b")
    console.print(f"  Summary: {summary_text[:200]}")

@session_compact.command()
@click.argument("session_id")
def summary(session_id):
    """Get summary of a compacted session."""
    s = session_archiver.get_summary(session_id)
    if s:
        console.print(f"[bold]Session {session_id} Summary:[/bold]\n{s}")
    else:
        console.print(f"[red]Session {session_id} not found[/red]")

@session_compact.command()
@click.argument("query")
@click.option("--session", "-s", default="", help="Restrict to session ID")
def search(query, session):
    """Search compacted session content without loading full file."""
    print_header()
    results = session_archiver.search_content(query, session)
    if not results:
        console.print(f"[yellow]No matches for '{query}'[/yellow]")
        return
    t = Table(box=box.ASCII, border_style="cyan", title=f"Search: '{query}' ({len(results)} matches)")
    t.add_column("Session", style="bold"); t.add_column("Context")
    for r in results[:10]:
        t.add_row(r["session"], r["context"][:100])
    console.print(t)

@session_compact.command(name="list")
def session_compact_list():
    """List all compacted sessions."""
    all_s = session_archiver.get_all()
    if not all_s:
        console.print("[yellow]No compacted sessions yet[/yellow]"); return
    t = Table(box=box.ASCII, border_style="cyan", title="Compacted Sessions")
    t.add_column("ID", style="bold"); t.add_column("Label"); t.add_column("Messages"); t.add_column("Summary")
    for s in all_s:
        t.add_row(s["id"][:12], s["label"], str(s["messages"]), s["summary"][:60])
    console.print(t)
    stats = session_archiver.stats()
    console.print(f"[dim]Total: {stats['compacted_sessions']} sessions, {stats['total_messages']} messages, {stats['total_size_bytes']} bytes[/dim]")

@session_compact.command()
@click.option("--max", "-m", default=50, type=int)
def auto(max):
    """Auto-compact: check threshold and compact if needed."""
    compaction_manager._max_messages = max
    result = compaction_manager.compact()
    if result:
        console.print(f"[green]+[/green] Auto-compacted {result['archived_messages']} messages")
        console.print(f"  File: {result['file']}")
        console.print(f"  Summary: {result['summary'][:200]}")
    else:
        console.print(f"[yellow]Only {len(compaction_manager._pending_messages)} pending, threshold is {max}. Not compacting yet.[/yellow]")

# === FILE ACCESS COMMANDS ===
@cli.group()
def file():
    """File access & management (Claude Code-style)."""

@file.command()
@click.argument("path")
@click.option("--offset", "-o", default=0, type=int)
@click.option("--limit", "-l", default=0, type=int)
def read(path, offset, limit):
    """Read a file with optional offset/limit."""
    print_header()
    r = file_agent.read_file(path, offset, limit)
    if "error" in r:
        console.print(f"[red]{r['error']}[/red]"); return
    console.print(f"[dim]{r['path']} — {r['lines']} lines ({r['size']} bytes)[/dim]")
    console.print(Syntax(r['content'], "python", theme="monokai", line_numbers=True) if path.endswith('.py') else r['content'][:5000])

@file.command()
@click.argument("path")
@click.option("--chunk-size", "-c", default=200, type=int)
def toc(path, chunk_size):
    """Show table of contents for a file (chunked)."""
    chunks = file_agent.read_file_chunked(path, chunk_size)
    if not chunks or "error" in chunks[0]:
        console.print(f"[red]Error reading {path}[/red]"); return
    t = Table(box=box.ASCII, border_style="cyan", title=f"{path} — {sum(c['count'] for c in chunks)} lines")
    t.add_column("Start", style="bold"); t.add_column("End"); t.add_column("Lines"); t.add_column("Preview")
    for c in chunks:
        t.add_row(str(c['start']), str(c['end']), str(c['count']), c['preview'][:60])
    console.print(t)

@file.command()
@click.argument("pattern")
@click.option("--path", "-p", default=".")
@click.option("--include", "-i", default="*.py")
def grep(pattern, path, include):
    """Search file contents with regex."""
    print_header()
    r = file_agent.search(pattern, path, include)
    if not r["matches"]:
        console.print(f"[yellow]No matches for '{pattern}'[/yellow]"); return
    t = Table(box=box.ASCII, border_style="green", title=f"Grep '{pattern}' ({r['matches']} matches)")
    t.add_column("File", style="bold"); t.add_column("Line"); t.add_column("Content")
    for res in r["results"][:50]:
        t.add_row(res["file"], str(res["line"]), res["content"][:100])
    console.print(t)
    if r["truncated"]: console.print(f"[dim]... and {r['matches'] - 50} more matches[/dim]")

@file.command()
@click.argument("pattern")
def glob_cmd(pattern):
    """Glob for files matching a pattern."""
    r = file_agent.glob(pattern)
    if not r["matches"]:
        console.print(f"[yellow]No matches for '{pattern}'[/yellow]"); return
    t = Table(box=box.ASCII, border_style="cyan", title=f"Glob '{pattern}' ({r['matches']} files)")
    t.add_column("#"); t.add_column("File")
    for i, f in enumerate(r["files"], 1):
        t.add_row(str(i), f)
    console.print(t)

@file.command()
@click.argument("path")
def info(path):
    """Show detailed file/directory info."""
    r = file_agent.info(path)
    if "error" in r:
        console.print(f"[red]{r['error']}[/red]"); return
    t = Table(box=box.ASCII, border_style="cyan", title=f"Info: {path}")
    t.add_column("Property", style="bold"); t.add_column("Value")
    for k, v in r.items():
        if k in ("contents",): continue
        t.add_row(k, str(v)[:80])
    console.print(t)
    if r.get("type") == "directory" and r.get("contents"):
        sub = Table(box=box.ASCII, border_style="dim", title="Contents")
        sub.add_column("Name"); sub.add_column("Type"); sub.add_column("Size")
        for c in r["contents"][:30]:
            sub.add_row(c["name"], c["type"], str(c["size"]))
        console.print(sub)

@file.command()
@click.argument("path")
@click.option("--depth", "-d", default=3, type=int)
def tree(path, depth):
    """Show directory tree."""
    r = file_agent.tree(path, depth)
    if "error" in r:
        console.print(f"[red]{r['error']}[/red]"); return
    def render(items, prefix=""):
        for item in items:
            marker = "📁" if item["type"] == "dir" else "📄"
            sz = f" ({item.get('size',0)}b)" if item["type"] == "file" else ""
            console.print(f"{prefix}{marker} {item['name']}{sz}")
            if "children" in item:
                render(item["children"], prefix + "  ")
    console.print(f"[bold]{r['root']}[/bold]")
    render(r["tree"])

@file.command()
@click.argument("path")
@click.argument("old")
@click.argument("new")
def edit(path, old, new):
    """Edit file by replacing old_string with new_string."""
    result = file_agent.edit_file(path, old, new)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]")
    else:
        console.print(f"[green]+[/green] Edited {path}")

@file.command()
@click.argument("path")
def history(path):
    """Show file access history."""
    h = file_agent.history()
    t = Table(box=box.ASCII, border_style="dim", title="File Access History")
    t.add_column("Action"); t.add_column("Path"); t.add_column("Time")
    for entry in h[-15:]:
        t.add_row(entry["action"], entry.get("path","")[:60], time.strftime("%H:%M:%S", time.localtime(entry["time"])))
    console.print(t)

# === BROWSER AUTOMATION COMMANDS ===
@cli.group()
def browse():
    """Browser automation (screen-reading + pixel-coord)."""

@browse.command()
@click.argument("url")
def navigate(url):
    """Navigate to a URL."""
    print_header()
    with console.status(f"[cyan]Navigating to {url}...[/cyan]"):
        r = browser.navigate(url)
    if r["status"] == "error":
        console.print(f"[red]Error: {r.get('error')}[/red]"); return
    console.print(f"[green]✓[/green] Loaded: [bold]{r.get('title', url)}[/bold]")

@browse.command(name="screenshot")
def browse_screenshot():
    """Take a screenshot of current page."""
    b64 = browser.screenshot()
    if b64:
        console.print(f"[green]✓[/green] Screenshot taken (base64: {len(b64)} bytes)")
    else:
        console.print("[red]Screenshot failed[/red]")

@browse.command()
@click.option("--selector", "-s", default="", help="CSS selector to click")
@click.option("--x", type=int, default=0, help="X coordinate")
@click.option("--y", type=int, default=0, help="Y coordinate")
@click.option("--coords", is_flag=True, help="Use pixel coordinates")
def browse_click(selector, x, y, coords):
    """Click element by selector or pixel coordinates."""
    r = browser.click(selector, x, y, coords)
    if r["success"]:
        console.print(f"[green]✓[/green] Clicked {r['clicked']}")
    else:
        console.print(f"[red]Click failed: {r.get('error')}[/red]")

@browse.command()
@click.argument("text")
@click.option("--selector", "-s", default="", help="CSS selector")
def browse_type(text, selector):
    """Type text into an element."""
    r = browser.type(selector, text) if selector else browser.type(x=500, y=400, text=text, use_coords=True)
    if r["success"]: console.print(f"[green]✓[/green] Typed '{r['typed']}'")
    else: console.print(f"[red]{r.get('error')}[/red]")

@browse.command()
def state():
    """Show interactive elements on page."""
    s = browser.get_state()
    if "error" in s:
        console.print(f"[red]{s['error']}[/red]"); return
    t = Table(box=box.ASCII, border_style="cyan", title=f"Interactive Elements ({s['count']})")
    t.add_column("Tag"); t.add_column("Text"); t.add_column("Position"); t.add_column("Center")
    for el in s["elements"][:30]:
        pos = f"{el['x']},{el['y']}"
        center = f"{el['center_x']},{el['center_y']}"
        t.add_row(el["tag"], el["text"][:40], pos, center)
    console.print(t)
    if s['count'] > 30: console.print(f"[dim]... and {s['count'] - 30} more elements[/dim]")

@browse.command()
@click.argument("text")
def find(text):
    """Find and click element by text."""
    r = screen_reader.click_text(text)
    if r.get("found", True):
        console.print(f"[green]✓[/green] Clicked '{text}'")
    else:
        console.print(f"[red]{r.get('error')}[/red]")

@browse.command()
@click.argument("script")
def js(script):
    """Run JavaScript in the browser."""
    r = browser.evaluate(script)
    console.print(r.get("result", r.get("error", "?"))[:2000])

@browse.command()
def extract():
    """Extract visible text from current page."""
    r = browser.extract_text()
    console.print(r.get("text", r.get("error", "?"))[:5000])

@browse.command()
def links():
    """Extract all links from page."""
    links = browser.extract_links()
    if not links:
        console.print("[yellow]No links found[/yellow]"); return
    t = Table(box=box.ASCII, border_style="cyan", title=f"Links ({len(links)})")
    t.add_column("Text", style="bold"); t.add_column("URL")
    for l in links[:20]:
        t.add_row(l.get("text","")[:60], l.get("href","")[:80])
    console.print(t)

@browse.command()
def close():
    """Close the browser."""
    browser.close()
    console.print("[red]Browser closed[/red]")

# === COMPUTER USE COMMANDS ===
@cli.group()
def computer_use():
    """Desktop automation: mouse, keyboard, windows."""

@computer_use.command()
@click.argument("x", type=int)
@click.argument("y", type=int)
def move(x, y):
    """Move mouse to coordinates."""
    r = computer.move_mouse(x, y)
    console.print(f"[green]✓[/green] Mouse moved to ({x}, {y})")

@computer_use.command()
@click.argument("x", type=int)
@click.argument("y", type=int)
@click.option("--button", "-b", default="left")
def cu_click(x, y, button):
    """Click at coordinates."""
    computer.click(x, y, button)
    console.print(f"[green]✓[/green] {button}-clicked ({x}, {y})")

@computer_use.command()
@click.argument("text")
@click.option("--interval", "-i", default=0.05, type=float)
def cu_type(text, interval):
    """Type text at human speed."""
    r = computer.type_text(text, interval)
    console.print(f"[green]✓[/green] Typed {r['length']} chars: '{r['typed']}'")

@computer_use.command()
@click.argument("key")
def press(key):
    """Press a keyboard key."""
    computer.press_key(key)
    console.print(f"[green]✓[/green] Pressed '{key}'")

@computer_use.command()
@click.argument("keys", nargs=-1, required=True)
def hotkey(keys):
    """Press a key combination. Usage: hotkey ctrl c"""
    computer.hotkey(*keys)
    console.print(f"[green]✓[/green] Hotkey: {'+'.join(keys)}")

@computer_use.command()
@click.argument("app")
def open(app):
    """Open an application (Win+R)."""
    computer.open_app(app)
    console.print(f"[green]✓[/green] Launched '{app}'")

@computer_use.command()
def screenshot():
    """Take desktop screenshot."""
    b64 = computer.screenshot()
    console.print(f"[green]✓[/green] Desktop screenshot taken ({len(b64)} bytes)")

@computer_use.command()
def windows():
    """List open windows."""
    wins = computer.list_windows()
    if not wins:
        console.print("[yellow]No windows found[/yellow]"); return
    t = Table(box=box.ASCII, border_style="cyan", title=f"Open Windows ({len(wins)})")
    t.add_column("Window", style="bold"); t.add_column("Visible")
    for w in wins:
        t.add_row(w.get("title","")[:80], str(w.get("visible","?")))
    console.print(t)

@computer_use.command()
@click.argument("title")
def focus(title):
    """Focus a window by title substring."""
    r = computer.focus_window(title)
    if "error" in r:
        console.print(f"[red]{r['error']}[/red]")
    else:
        console.print(f"[green]✓[/green] Focused: {r['window']}")

@computer_use.command()
def position():
    """Show current mouse position."""
    p = computer.get_position()
    console.print(f"Mouse position: ({p['x']}, {p['y']})")

@computer_use.command()
@click.option("--speed", "-s", default=0.5, type=float)
def speed(speed):
    """Set automation speed: 0=instant, 0.5=normal, 1=slow."""
    computer.set_speed(speed)
    console.print(f"[cyan]Speed set to {speed}[/cyan]")

@computer_use.command()
def demo():
    """Demo: open notepad and type a message."""
    with console.status("[cyan]Opening notepad...[/cyan]"):
        computer.open_notepad()
    console.print("[green]✓[/green] Notepad opened and text typed!")

# === CODE ANALYSIS COMMANDS ===
@cli.group()
def code():
    """Code analysis: AST, deps, complexity, refactoring."""

@code.command()
@click.argument("path")
def analyze(path):
    """Analyze a Python file or project."""
    print_header()
    if path.endswith('.py'):
        r = analyzer.analyze_file(path)
        if "error" in r: console.print(f"[red]{r['error']}[/red]"); return
        console.print(f"[bold]{r['file']}[/bold] — {r['lines']} lines, {len(r['functions'])} functions, {len(r['classes'])} classes")
        console.print(f"  Complexity: {r['complexity']['total']} (avg {r['complexity']['avg']:.1f})")
        console.print(f"  Imports: {len(r['imports'])}  Dependencies: {len(r['dependencies'])}")
        console.print(f"  Code: {r['metrics']['code_lines']}  Comments: {r['metrics']['comment_lines']}  Blanks: {r['metrics']['blank_lines']}")
        if r['functions']:
            t = Table(box=box.ASCII, border_style="cyan", title="Functions")
            t.add_column("Name"); t.add_column("Args"); t.add_column("Complexity"); t.add_column("Line")
            for f in r['functions']:
                t.add_row(f['name'], str(f['arg_count']), str(f['complexity']), str(f['line']))
            console.print(t)
    else:
        with console.status("[cyan]Analyzing project...[/cyan]"):
            r = analyzer.analyze_project(path)
        console.print(f"[bold]Project Analysis[/bold] — {r['files']} files, {r['lines']} lines")
        console.print(f"  Functions: {r['functions']}  Classes: {r['classes']}  Complexity: {r['complexity']}")
        if r['top_dependencies']:
            t = Table(box=box.ASCII, border_style="cyan", title="Top Dependencies")
            t.add_column("Package", style="bold"); t.add_column("Used By")
            for dep, count in r['top_dependencies'][:15]:
                t.add_row(dep, str(count))
            console.print(t)

@code.command()
@click.argument("name")
@click.option("--path", "-p", default=".")
def refs(name, path):
    """Find all references to a symbol."""
    r = analyzer.find_references(name, path)
    if not r:
        console.print(f"[yellow]No references to '{name}'[/yellow]"); return
    t = Table(box=box.ASCII, border_style="cyan", title=f"References to '{name}' ({len(r)})")
    t.add_column("File", style="bold"); t.add_column("Line"); t.add_column("Content")
    for ref in r[:30]:
        t.add_row(ref['file'], str(ref['line']), ref['content'][:100])
    console.print(t)

@code.command()
@click.argument("path")
def suggestions(path):
    """Get refactoring suggestions."""
    r = analyzer.refactor_suggestions(path)
    if not r: console.print("[green]No suggestions — code looks clean![/green]"); return
    t = Table(box=box.ASCII, border_style="yellow", title=f"Refactoring Suggestions ({len(r)})")
    t.add_column("Type", style="bold"); t.add_column("Item"); t.add_column("Detail"); t.add_column("Line")
    for s in r:
        name = s.get('function') or s.get('class','')
        val = s.get('args') or s.get('complexity') or s.get('methods','')
        t.add_row(s['type'], name, str(val), str(s['line']))
    console.print(t)

@code.command()
@click.argument("pattern")
@click.option("--path", "-p", default=".")
def search(pattern, path):
    """Search code with regex."""
    r = analyzer.search_code(pattern, path)
    if not r['matches']:
        console.print(f"[yellow]No matches[/yellow]"); return
    t = Table(box=box.ASCII, border_style="cyan", title=f"Code Search '{pattern}' ({r['matches']} matches)")
    t.add_column("File"); t.add_column("Line"); t.add_column("Content")
    for res in r['results'][:40]:
        t.add_row(res['file'], str(res['line']), res['content'][:100])
    console.print(t)

# === CODING EDITOR COMMANDS (Claude Code-style) ===
@cli.group()
def edit():
    """AI-powered code editor (Claude Code-style)."""

@edit.command()
@click.argument("filepath")
@click.argument("old_text")
@click.argument("new_text")
@click.option("--no-backup", is_flag=True, help="Skip backup")
def sedit(filepath, old_text, new_text, no_backup):
    """Edit file by replacing text (with diff preview)."""
    with console.status(f"[cyan]Editing {filepath}...[/cyan]"):
        result = coding_agent.edit(filepath, old_text, new_text, backup=not no_backup)
    if result.success:
        d = result.diff
        if len(d) > 2000:
            d = d[:1000] + "\n... (truncated)"
        console.print(Syntax(d[:2000], "diff", theme="monokai"))
        console.print(f"[green]Edited {filepath}[/green]")
        if result.backup_path:
            console.print(f"[dim]Backup: {result.backup_path}[/dim]")
    else:
        console.print(f"[red]Error: {result.error}[/red]")

@edit.command()
@click.argument("filepath")
@click.argument("start_line", type=int)
@click.argument("end_line", type=int)
@click.argument("new_text")
@click.option("--no-backup", is_flag=True, help="Skip backup")
def sedit_lines(filepath, start_line, end_line, new_text, no_backup):
    """Replace a range of lines."""
    with console.status(f"[cyan]Editing lines {start_line}-{end_line}...[/cyan]"):
        result = coding_agent.edit_lines(filepath, start_line, end_line, new_text, backup=not no_backup)
    if result.success:
        console.print(result.diff[:2000])
        console.print(f"[green]Edited {filepath}[/green]")
    else:
        console.print(f"[red]Error: {result.error}[/red]")

@edit.command()
@click.argument("filepath")
@click.option("--start", "-s", type=int, default=1, help="Start line")
@click.option("--end", "-e", type=int, help="End line")
def sread(filepath, start, end):
    """Read file with optional line range."""
    content_lines, count = coding_agent.read(filepath, start, end)
    if count == 0:
        console.print(f"[red]Error reading {filepath}: {content_lines}[/red]")
        return
    ext = os.path.splitext(filepath)[1][1:] or "text"
    console.print(Syntax(content_lines[:5000], ext, theme="monokai"))
    console.print(f"[dim]{count} lines[/dim]")

@edit.command()
@click.argument("filepath")
@click.argument("content")
def swrite(filepath, content):
    """Write a new file (with diff if overwriting)."""
    with console.status(f"[cyan]Writing {filepath}...[/cyan]"):
        result = coding_agent.write(filepath, content)
    if result.success:
        if result.diff:
            console.print(Syntax(result.diff[:2000], "diff", theme="monokai"))
        console.print(f"[green]Written {filepath}[/green]")
    else:
        console.print(f"[red]Error: {result.error}[/red]")

@edit.command()
@click.argument("filepath")
def slint(filepath):
    """Lint a file and show issues."""
    issues = coding_agent.lint(filepath)
    if not issues:
        console.print("[green]No issues found[/green]"); return
    t = Table(box=box.ASCII, title=f"Lint: {filepath}")
    t.add_column("Line"); t.add_column("Severity"); t.add_column("Message")
    for issue in issues:
        sev = {"error": "[red]E[/red]", "warning": "[yellow]W[/yellow]", "info": "[blue]I[/blue]"}
        t.add_row(str(issue["line"]), sev.get(issue["severity"], "?"), issue["message"])
    console.print(t)

@edit.command()
@click.argument("description")
@click.argument("language")
@click.option("--output", "-o", help="Output file")
def sgenerate(description, language, output):
    """Generate code scaffold from description."""
    result = coding_agent.generate(description, language, output)
    ext = os.path.splitext(output)[1][1:] if output else "text"
    console.print(Syntax(result["content"][:3000], ext or "text", theme="monokai"))
    if result.get("saved_to"):
        console.print(f"[green]Saved to {result['saved_to']}[/green]")

@edit.command()
def sedit_history():
    """Show edit history."""
    stats = coding_agent.stats()
    t = Table(box=box.ASCII, title=f"Edit History ({stats['total_edits']})")
    t.add_column("#"); t.add_column("Action"); t.add_column("File")
    for i, h in enumerate(stats.get("recent", []), 1):
        t.add_row(str(i), h.get("action",""), h.get("file","")[:60])
    console.print(t)

# === WEB RESEARCH COMMANDS ===
@cli.group()
def research():
    """Web research: search, fetch, synthesize."""

@research.command()
@click.argument("query")
@click.option("--num", "-n", default=5, type=int)
def search(query, num):
    """Search the web."""
    print_header()
    with console.status(f"[cyan]Searching for '{query}'...[/cyan]"):
        r = researcher.search(query, num)
    if not r['results']:
        console.print("[yellow]No results[/yellow]"); return
    t = Table(box=box.ASCII, border_style="cyan", title=f"Search: '{query}' ({r['total']} results)")
    t.add_column("#"); t.add_column("Title", style="bold"); t.add_column("Snippet")
    for i, res in enumerate(r['results'], 1):
        t.add_row(str(i), res['title'][:60], res.get('snippet','')[:100])
    console.print(t)

@research.command()
@click.argument("url")
def fetch(url):
    """Fetch and extract content from a URL."""
    print_header()
    with console.status(f"[cyan]Fetching {url}...[/cyan]"):
        r = researcher.fetch_page(url)
    if "error" in r:
        console.print(f"[red]{r['error']}[/red]"); return
    console.print(f"[bold]{r.get('title', url)}[/bold]")
    console.print(f"[dim]Content: {r.get('length',0)} bytes[/dim]")
    console.print(r.get('content','')[:5000])
    if r.get('links'):
        console.print(f"[dim]Links: {len(r['links'])} found[/dim]")

@research.command()
@click.argument("topic")
@click.option("--depth", "-d", default=2, type=int)
@click.option("--pages", "-p", default=5, type=int)
def deep(topic, depth, pages):
    """Deep research: search, fetch, analyze, synthesize."""
    print_header()
    with console.status(f"[cyan]Researching '{topic}' (depth={depth}, pages={pages})...[/cyan]"):
        r = researcher.research(topic, depth, pages)
    console.print(f"[bold]Research: {r['topic']}[/bold]")
    console.print(f"Pages fetched: {r['pages_fetched']}")
    console.print(f"Synthesis: {r['synthesis']['summary']}")
    console.print(f"Report: memory/research/research_{r['id']}.json")
    if r['synthesis'].get('sections'):
        t = Table(box=box.ASCII, border_style="cyan", title="Key Topics")
        t.add_column("Topic", style="bold"); t.add_column("Sources")
        for sec in r['synthesis']['sections'][:10]:
            t.add_row(sec['topic'], str(sec['mentioned_in']))
        console.print(t)

@research.command()
@click.argument("question")
def ask(question):
    """Ask a question and get web-researched answer."""
    print_header()
    with console.status(f"[cyan]Researching '{question}'...[/cyan]"):
        r = researcher.ask(question)
    console.print(f"[bold]Question:[/bold] {r['question']}")
    console.print(f"[bold]Answer:[/bold] {r['synthesis']['summary']}")
    console.print(f"[dim]Sources ({r['pages_consulted']}):[/dim]")
    for src in r['sources'][:5]:
        console.print(f"  • {src}")

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
                gen = pbt_engine.evolve()
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

# === PIXEL VISION COMMANDS ===
@cli.group()
def vision():
    """Pixel-level screen perception."""

@vision.command()
@click.argument("image_path", required=False, default="")
def analyze(image_path):
    """Describe a screen or analyze elements."""
    from pixel_vision import PixelVision
    pv = PixelVision()
    with console.status("[cyan]Analyzing...[/cyan]"):
        if image_path:
            result = pv.detect_elements(image_path)
        else:
            result = pv.describe_screen()
    if isinstance(result, dict):
        for k, v in result.items():
            if isinstance(v, list):
                console.print(f"[bold]{k}:[/bold] {len(v)} items")
                for item in v[:5]:
                    if isinstance(item, dict):
                        console.print(f"  {str(item)[:100]}")
                    else:
                        console.print(f"  {str(item)[:80]}")
            else:
                console.print(f"[bold]{k}:[/bold] {str(v)[:80]}")
    elif isinstance(result, str):
        console.print(result[:2000])

@vision.command()
def capabilities():
    """Check available vision libraries."""
    from pixel_vision import PixelVision
    pv = PixelVision()
    avail = []
    not_avail = []
    for method in ['describe_screen','detect_elements','detect_color_palette','detect_layout_grid','find_all_icons','screenshot_b64']:
        if hasattr(pv, method) and callable(getattr(pv, method)):
            avail.append(method)
        else:
            not_avail.append(method)
    console.print("[bold]Available methods:[/bold]")
    for m in avail:
        console.print(f"  [green]Y[/green] {m}")
    for m in not_avail:
        console.print(f"  [red]N[/red] {m}")

# === API ROUTER COMMANDS ===
@cli.group()
def apirouter():
    """Multi-API intelligent router."""

@apirouter.command()
@click.argument("prompt_text")
def aroute(prompt_text):
    """Route a task to the best API provider."""
    with console.status("[cyan]Classifying task...[/cyan]"):
        result = api_router.route(prompt_text)
    console.print(f"[bold]Capability:[/bold] {result.get('capability','?')}")
    console.print(f"[bold]Provider:[/bold] {result.get('provider','?')}")
    console.print(f"[bold]Model:[/bold] {result.get('model','?')}")
    console.print(f"[bold]Priority:[/bold] {result.get('priority','?')}")
    if result.get('fallback_chain'):
        console.print(f"[bold]Fallback chain:[/bold] {result['fallback_chain']}")
    if result.get('error'):
        console.print(f"[red]Error: {result['error']}[/red]")

@apirouter.command()
def astats():
    """Show router usage statistics."""
    s = api_router.stats()
    console.print(f"Total calls: {s.get('total_calls',0)}")
    console.print(f"Total tokens: {s.get('total_tokens',0)}")
    console.print(f"History size: {s.get('history_size',0)}")
    console.print(f"Providers: {s.get('providers',[])}")
    console.print(f"Enabled: {s.get('enabled',False)}")
    console.print(f"API keys set: {s.get('api_keys_set',0)}")

@apirouter.command()
def providers():
    """List available API providers."""
    for p in api_router.list_providers():
        name = p.name if hasattr(p,'name') else str(p)
        url = p.base_url if hasattr(p,'base_url') else ''
        console.print(f"  {name} ({url})")

@apirouter.command()
def history():
    """Show routing history."""
    h = api_router.history()
    if not h:
        console.print("[yellow]No history[/yellow]"); return
    for item in h[-10:]:
        if isinstance(item, dict):
            console.print(f"  {str(item.get('time',''))[:19]} {str(item.get('task',''))[:40]} -> {item.get('provider','?')}")
        else:
            console.print(f"  {str(item)[:80]}")

# === CLI PLUGIN COMMANDS ===
@cli.group()
def plugins():
    """Manage CLI tool integrations."""

@plugins.command()
def plist():
    """List all available CLI plugins."""
    plug_list = cli_plugins.list_plugins()
    t = Table(box=box.ASCII, title="CLI Plugins")
    t.add_column("Plugin"); t.add_column("Installed"); t.add_column("Category"); t.add_column("Description")
    for p in plug_list:
        inst = "[green]Y[/green]" if p.get('installed') else "[red]N[/red]"
        t.add_row(p.get('name',''), inst, p.get('category',''), p.get('description','')[:60])
    console.print(t)

@plugins.command()
@click.argument("plugin_name")
@click.argument("args", nargs=-1)
def run(plugin_name, args):
    """Run a CLI plugin with arguments."""
    found = [p for p in cli_plugins.list_plugins() if p['name'] == plugin_name]
    if not found:
        console.print(f"[red]Unknown plugin: {plugin_name}[/red]"); return
    cmd = ' '.join(args)
    with console.status(f"[cyan]Running {plugin_name} {cmd}...[/cyan]"):
        result = cli_plugins.run(plugin_name, args=cmd)
    if result.get('success'):
        console.print(result.get('stdout','')[:5000] or "(no output)")
    else:
        console.print(f"[red]Error: {result.get('error','Unknown')}[/red]")
        console.print(result.get('stderr','')[:2000] if result.get('stderr') else "")

@plugins.command()
def pdetect():
    """Show which CLI tools are installed."""
    plug_list = cli_plugins.list_plugins()
    t = Table(box=box.ASCII, title="Detection Results")
    t.add_column("Plugin"); t.add_column("Available")
    for p in sorted(plug_list, key=lambda x: x['name']):
        avail = "[green]Y[/green]" if p.get('installed') else "[red]N[/red]"
        t.add_row(p['name'], avail)
    console.print(t)

@plugins.command()
def pcategories():
    """Show plugins grouped by category."""
    cats = cli_plugins.installed_by_category()
    t = Table(box=box.ASCII, title="Plugins by Category")
    t.add_column("Category"); t.add_column("Plugins")
    for cat, plugs in sorted(cats.items()):
        names = [p['name'] if isinstance(p, dict) else str(p) for p in plugs]
        t.add_row(cat, ', '.join(names))
    console.print(t)

# === GITHUB COMMANDS ===
@cli.group()
def gh():
    """GitHub integration."""

@gh.command()
def gstatus():
    """Check GitHub connection status."""
    auth_status = github.is_authenticated
    has_tok = github.has_token
    console.print(f"Authenticated: {status_tag(auth_status,'Yes','No')}")
    console.print(f"Has token: {status_tag(has_tok,'Yes','No')}")
    if auth_status:
        try:
            user = github.get_user()
            if isinstance(user, dict):
                console.print(f"User: {user.get('login','?')} ({user.get('name','?')})")
        except Exception:
            pass

@gh.command()
@click.argument("query")
@click.option("--limit", "-l", default=5, type=int)
def repos(query, limit):
    """Search GitHub repositories."""
    with console.status(f"[cyan]Searching repos: '{query}'...[/cyan]"):
        r = github.search_repos(query, limit)
    if not r:
        console.print("[yellow]No results[/yellow]"); return
    t = Table(box=box.ASCII, title=f"GitHub Repos: '{query}'")
    t.add_column("Name"); t.add_column("Stars"); t.add_column("Language"); t.add_column("Description")
    for repo in r:
        t.add_row(repo.get('name',''), str(repo.get('stars',0)), repo.get('language','') or '', (repo.get('description','') or '')[:60])
    console.print(t)

@gh.command()
@click.argument("owner_repo")
@click.option("--state", default="open")
def issues(owner_repo, state):
    """List issues for a repo."""
    parts = owner_repo.split('/')
    if len(parts) != 2:
        console.print("[red]Use format: owner/repo[/red]"); return
    with console.status(f"[cyan]Fetching issues for {owner_repo}...[/cyan]"):
        r = github.list_issues(parts[0], parts[1], state)
    t = Table(box=box.ASCII, title=f"Issues: {owner_repo}")
    t.add_column("#"); t.add_column("Title"); t.add_column("State"); t.add_column("Author")
    for i in r:
        num = i.get('number',i.get('id','?'))
        title = i.get('title','')[:60]
        state_v = i.get('state','')
        author = i.get('user',{}).get('login','') if isinstance(i.get('user'),dict) else str(i.get('user',''))
        t.add_row(str(num), title, state_v, author)
    console.print(t)

@gh.command()
@click.argument("owner_repo")
@click.argument("path")
def gfile(owner_repo, path):
    """Get file content from a repo."""
    parts = owner_repo.split('/')
    if len(parts) != 2:
        console.print("[red]Use format: owner/repo[/red]"); return
    with console.status(f"[cyan]Fetching {path} from {owner_repo}...[/cyan]"):
        r = github.get_file_content(parts[0], parts[1], path)
    if r:
        console.print(Syntax(r[:5000], "python" if path.endswith('.py') else "text", theme="monokai"))
    else:
        console.print(f"[red]File not found or no access[/red]")

@gh.command()
@click.argument("query")
@click.option("--limit", "-l", default=5, type=int)
def codesearch(query, limit):
    """Search GitHub code."""
    with console.status(f"[cyan]Searching code: '{query}'...[/cyan]"):
        r = github.search_code(query, limit)
    if not r:
        console.print("[yellow]No results[/yellow]"); return
    t = Table(box=box.ASCII, title=f"Code: '{query}'")
    t.add_column("Repo"); t.add_column("Path")
    for item in r:
        repo_name = item.get('repository',item.get('repo',''))
        if isinstance(repo_name, dict):
            repo_name = repo_name.get('full_name','')
        t.add_row(str(repo_name)[:40], item.get('path',''))
    console.print(t)

@gh.command()
@click.option("--state", default="open", help="PR state: open/closed/merged")
@click.option("--limit", "-l", default=10, type=int)
def prs(state, limit):
    """List GitHub pull requests."""
    with console.status("[cyan]Fetching PRs...[/cyan]"):
        pr_list = git_engine.pr_list(state=state, max_count=limit)
    if not pr_list:
        console.print("[yellow]No PRs found (gh CLI required)[/yellow]"); return
    t = Table(box=box.ASCII, title=f"PRs ({state})")
    t.add_column("#"); t.add_column("Title"); t.add_column("Author"); t.add_column("Branch")
    for pr in pr_list:
        author = pr.get('author',{}).get('login','?') if isinstance(pr.get('author'),dict) else '?'
        head = pr.get('headRefName','')
        t.add_row(str(pr.get('number','')), pr.get('title','')[:60], author, head)
    console.print(t)

@gh.command()
@click.argument("title")
@click.option("--body", default="", help="PR body text")
def prcreate(title, body):
    """Create a GitHub pull request."""
    with console.status("[cyan]Creating PR...[/cyan]"):
        out, err, code = git_engine.pr_create(title, body)
    if code == 0:
        console.print(f"[green]PR created: {out}[/green]")
    else:
        console.print(f"[red]Failed: {err}[/red]")

@gh.command()
def pistatus():
    """Show CI/CD pipeline status."""
    with console.status("[cyan]Checking CI status...[/cyan]"):
        runs = git_engine.ci_status()
    if not runs:
        console.print("[yellow]No CI runs found (gh CLI required)[/yellow]"); return
    t = Table(box=box.ASCII, title="CI/CD Status")
    t.add_column("Name"); t.add_column("Status"); t.add_column("Conclusion")
    for run in runs:
        s = run.get('status','?')
        c = run.get('conclusion','?') or 'running'
        t.add_row(run.get('displayTitle','')[:50], s, c)
    console.print(t)

# === GIT COMMANDS (lazygit-style) ===
@cli.group()
def git():
    """Git operations (lazygit-style TUI)."""

@git.command()
def gstatus():
    """Show working tree status (like lazygit Files panel)."""
    files, branch = git_engine.status()
    t = Table(box=box.ASCII, title=f"Branch: {branch.get('branch','?')}  "
              f"{'[green]↑'+str(branch.get('ahead',0))+'[/green]' if branch.get('ahead') else ''}"
              f"{'[red]↓'+str(branch.get('behind',0))+'[/red]' if branch.get('behind') else ''}")
    t.add_column("Status"); t.add_column("Staged"); t.add_column("File"); t.add_column("+/-")
    for f in files:
        staged_str = "Y" if f.staged else ""
        stats = f"+{f.additions}/-{f.deletions}" if (f.additions or f.deletions) else ""
        t.add_row(f.status, staged_str, f.path[:80], stats)
    console.print(t)
    console.print(f"[cyan]{len(files)} files[/cyan]")

@git.command()
@click.argument("paths", nargs=-1)
def gadd(paths):
    """Stage files (space to toggle in lazygit)."""
    out, err, code = git_engine.stage(list(paths) if paths else None)
    if code == 0:
        console.print("[green]Staged[/green]")
    else:
        console.print(f"[red]{err}[/red]")

@git.command()
@click.argument("paths", nargs=-1)
def gunstage(paths):
    """Unstage files."""
    out, err, code = git_engine.unstage(list(paths) if paths else None)
    if code == 0:
        console.print("[green]Unstaged[/green]")
    else:
        console.print(f"[red]{err}[/red]")

@git.command()
@click.argument("message", required=False)
@click.option("--ai", is_flag=True, help="Generate commit message from diff")
@click.option("--amend", is_flag=True, help="Amend last commit")
def gcommit(message, ai, amend):
    """Commit staged changes (with optional AI message)."""
    if amend:
        out, err, code = git_engine.commit_amend()
    elif ai or not message:
        msg = git_engine.commit_ai_message()
        if not message:
            message = msg
        out, err, code = git_engine.commit(message)
    else:
        out, err, code = git_engine.commit(message)
    if code == 0:
        console.print(f"[green]Committed: {out[:100]}[/green]")
    else:
        console.print(f"[red]{err}[/red]")

@git.command()
def glog():
    """Show commit log (like lazygit Commits panel)."""
    log = git_engine.log(max_count=30, pretty="medium")
    if not log:
        console.print("[yellow]No commits[/yellow]")
        return
    console.print(Syntax(log, "bash", theme="monokai"))

@git.command()
def gbranch():
    """List and manage branches (like lazygit Branches panel)."""
    branches = git_engine.branches()
    t = Table(box=box.ASCII, title="Branches")
    t.add_column("Current"); t.add_column("Name"); t.add_column("Last Commit")
    for b in branches:
        cur = "*" if b.current else ""
        t.add_row(cur, b.name, b.last_commit[:60])
    console.print(t)

@git.command()
@click.argument("name")
@click.option("--base", help="Base branch")
def gbranch_create(name, base):
    """Create a new branch."""
    out, err, code = git_engine.branch_create(name, base)
    if code == 0:
        console.print(f"[green]Created branch: {name}[/green]")
    else:
        console.print(f"[red]{err}[/red]")

@git.command()
@click.argument("name")
@click.option("--force", is_flag=True, help="Force delete")
def gbranch_delete(name, force):
    """Delete a branch."""
    out, err, code = git_engine.branch_delete(name, force)
    if code == 0:
        console.print(f"[green]Deleted branch: {name}[/green]")
    else:
        console.print(f"[red]{err}[/red]")

@git.command()
@click.argument("name")
@click.option("--create", "-c", is_flag=True, help="Create and switch")
def gswitch(name, create):
    """Switch branch."""
    out, err, code = git_engine.branch_switch(name, create)
    if code == 0:
        console.print(f"[green]Switched to {name}[/green]")
    else:
        console.print(f"[red]{err}[/red]")

@git.command()
@click.argument("name")
def gmerge(name):
    """Merge a branch."""
    out, err, code = git_engine.branch_merge(name)
    if code == 0:
        console.print(f"[green]Merged {name}[/green]")
    else:
        console.print(f"[red]{err}[/red]")

@git.command()
@click.option("--staged", is_flag=True, help="Show staged changes")
@click.argument("filepath", required=False)
def gdiff(filepath, staged):
    """Show diff (delta-style)."""
    diff = git_engine.diff(filepath, staged=staged)
    if diff["raw"]:
        console.print(Syntax(diff["raw"][:5000], "diff", theme="monokai"))
    else:
        console.print("[yellow]No changes[/yellow]")

@git.command()
def gstash():
    """List stashes."""
    stashes = git_engine.stash_list()
    if not stashes:
        console.print("[yellow]No stashes[/yellow]"); return
    t = Table(box=box.ASCII, title="Stashes")
    t.add_column("#"); t.add_column("Message")
    for s in stashes:
        t.add_row(str(s.index), s.message[:80])
    console.print(t)

@git.command()
@click.argument("message", required=False)
def gstash_push(message):
    """Stash changes."""
    out, err, code = git_engine.stash_push(message or "")
    if code == 0:
        console.print("[green]Stashed[/green]")
    else:
        console.print(f"[red]{err}[/red]")

@git.command()
@click.argument("index", default=0, type=int)
def gstash_pop(index):
    """Pop a stash."""
    out, err, code = git_engine.stash_pop(index)
    if code == 0:
        console.print("[green]Stash popped[/green]")
    else:
        console.print(f"[red]{err}[/red]")

@git.command()
def greflog():
    """Show reflog (for undo/recovery)."""
    log = git_engine.reflog(max_count=30)
    if log:
        console.print(Syntax(log[0][:5000] if isinstance(log, tuple) else log[:5000], "bash", theme="monokai"))
    else:
        console.print("[yellow]No reflog[/yellow]")

@git.command()
def gworktree():
    """List worktrees."""
    wts = git_engine.worktree_list()
    if not wts:
        console.print("[yellow]No worktrees[/yellow]"); return
    t = Table(box=box.ASCII, title="Worktrees")
    t.add_column("Path"); t.add_column("Branch"); t.add_column("Hash")
    for w in wts:
        t.add_row(w.get('path',''), w.get('branch',''), w.get('hash','')[:12])
    console.print(t)


@git.command()
@click.option("--staged", is_flag=True)
@click.option("--all", "-a", "all_files", is_flag=True)
def smart_commit(staged, all_files):
    """AI commit message + commit."""
    import subprocess as _sp
    if all_files: _sp.run(["git", "add", "-A"], check=True, capture_output=True)
    cmd = ["git", "diff", "--cached"] if staged or all_files else ["git", "diff"]
    r = _sp.run(cmd, capture_output=True, text=True, timeout=30)
    if not r.stdout.strip(): console.print("[yellow]No changes.[/yellow]"); return
    console.print("[yellow]Generating commit message...[/yellow]")
    msg = ai_enhance.generate_commit_message(r.stdout)
    console.print(f"[green]Proposed:[/green]\n{msg}")
    confirm = input("Commit? [Y/n]: ").strip().lower()
    if confirm in ("", "y", "yes"): _sp.run(["git", "commit", "-m", msg], check=True); console.print("[green]Committed![/green]")
    else:
        custom = input("Custom message: ").strip()
        if custom: _sp.run(["git", "commit", "-m", custom], check=True)


@git.command()
@click.argument("file", required=False, default=None)
def resolve(file):
    """AI suggest conflict resolution."""
    import subprocess as _sp
    r = _sp.run(["git", "diff", file] if file else ["git", "diff"], capture_output=True, text=True, timeout=30)
    if not r.stdout.strip(): console.print("[yellow]No diffs.[/yellow]"); return
    console.print("[yellow]Analyzing conflict...[/yellow]")
    console.print(Panel(ai_enhance.resolve_conflict_hint(r.stdout), title="Resolution", border_style="yellow"))


@cli.group()
def creds():
    """Manage encrypted credentials."""

@creds.command()
@click.argument("service")
@click.argument("key")
def set(service, key):
    """Set an API key for a service."""
    auth.set_api_key(service, key)
    console.print(f"[green]Key for '{service}' saved[/green]")

@creds.command()
@click.argument("service")
def get(service):
    """Get an API key (shows only first/last 4 chars)."""
    v = auth.get_api_key(service)
    if v:
        console.print(f"[bold]{service}:[/bold] {v[:4]}...{v[-4:]}")
    else:
        console.print(f"[yellow]Key for '{service}' not found[/yellow]")

@creds.command()
@click.argument("service")
def remove(service):
    """Remove a credential."""
    auth.remove_api_key(service)
    console.print(f"[green]Key for '{service}' removed[/green]")

@creds.command()
@click.argument("service")
def rotate(service):
    """Rotate an API key."""
    new_key = auth.rotate_api_key(service)
    if new_key:
        console.print(f"[green]Key for '{service}' rotated: {new_key[:8]}...[/green]")
    else:
        console.print(f"[red]No key exists for '{service}' to rotate[/red]")

@creds.command()
def clist():
    """List all stored service credentials."""
    services = auth.list_services()
    if not services:
        console.print("[yellow]No credentials stored[/yellow]"); return
    t = Table(box=box.ASCII, title="Credentials")
    t.add_column("Service"); t.add_column("Has Key")
    for s in services:
        has = auth.has_key(s) if hasattr(auth,'has_key') else auth.get_api_key(s) is not None
        t.add_row(s, status_tag(has,'Yes','No'))
    console.print(t)

@creds.command()
def cstatus():
    """Show auth system status."""
    s = auth.status()
    for k, v in s.items():
        if isinstance(v, bool):
            console.print(f"{k}: {status_tag(v,'Yes','No')}")
        else:
            console.print(f"{k}: {v}")

# === AGENT TREE COMMANDS ===
@cli.group()
def tree():
    """18-agent hierarchical tree management."""

@tree.command()
def show():
    """Display the agent tree."""
    tree_data = agent_tree.get_tree_structure()
    console.print(agent_tree.agent_summary())

@tree.command()
def mindmap():
    """Show mind-map style agent tree."""
    tree_data = agent_tree.get_tree_structure()
    mm = render_mind_map_json(tree_data)
    console.print_json(mm)

@tree.command()
@click.argument("task")
def delegate(task):
    """Delegate a task through the agent tree."""
    with console.status(f"[cyan]Delegating task...[/cyan]"):
        result = agent_tree.delegate(task)
    console.print(f"[bold]Delegated to:[/bold] {result.get('delegated_to','?')}")
    console.print(f"[bold]Path:[/bold] {' -> '.join(result.get('path',[]))}")
    console.print(f"[bold]ID:[/bold] {result.get('id','?')}")

@tree.command()
def astats():
    """Show agent tree statistics."""
    s = agent_tree.stats()
    for k, v in s.items():
        console.print(f"{k}: {v}")

@tree.command()
def tlist():
    """List all agents with their status."""
    agents = agent_tree.list_agents()
    t = Table(box=box.ASCII, title=f"All Agents ({len(agents)})")
    t.add_column("ID"); t.add_column("Name"); t.add_column("Role"); t.add_column("Status")
    for a in agents:
        t.add_row(a.get('id',''), a.get('name',''), a.get('role',''), str(a.get('status','')))
    console.print(t)

@tree.command()
def broadcast():
    """Broadcast status to all agents."""
    agent_tree.broadcast_event("cli_status_check", {"source": "cli"})
    console.print("[green]Broadcast sent to all agents[/green]")

# === UNIFIED VISION COMMANDS ===
@cli.group()
def uvision():
    """Unified browser+desktop vision."""

@uvision.command()
def ustatus():
    """Check unified vision status."""
    console.print("[bold]Unified Vision[/bold]")
    console.print(f"describe_screen: {'[green]available[/green]' if hasattr(unified_vision,'describe_screen') else '[red]N/A[/red]'}")
    console.print(f"detect_elements: {'[green]available[/green]' if hasattr(unified_vision,'detect_elements') else '[red]N/A[/red]'}")
    console.print(f"detect_ui_changes: {'[green]available[/green]' if hasattr(unified_vision,'detect_ui_changes') else '[red]N/A[/red]'}")

@uvision.command()
def capture():
    """Capture unified viewport snapshot."""
    with console.status("[cyan]Capturing...[/cyan]"):
        try:
            result = unified_vision.describe_screen()
            console.print(str(result)[:2000])
        except Exception as e:
            console.print(f"[red]Capture failed: {e}[/red]")

@uvision.command()
def diff():
    """Detect UI changes since last capture."""
    with console.status("[cyan]Detecting changes...[/cyan]"):
        try:
            changes = unified_vision.detect_ui_changes()
            if isinstance(changes, list):
                console.print(f"[bold]Changes detected:[/bold] {len(changes)}")
                for c in changes[:10]:
                    console.print(f"  {str(c)[:100]}")
            else:
                console.print(str(changes)[:1000])
        except Exception as e:
            console.print(f"[red]Change detection failed: {e}[/red]")

# === SEARCH COMMANDS (rg + fd + fzf hybrid) ===
@cli.group()
def search():
    """Search code & files (rg/fd/fzf hybrid)."""

@search.command()
@click.argument("pattern")
@click.argument("path", default=".")
@click.option("--regex", is_flag=True, help="Treat pattern as regex")
@click.option("--include", "-i", multiple=True, help="File extension filter (e.g. .py)")
@click.option("--exclude", "-x", multiple=True, help="Exclude extensions")
@click.option("--max", "max_results", default=500, help="Max results")
@click.option("--json", "json_out", is_flag=True, help="JSON output")
def rgrep(pattern, path, regex, include, exclude, max_results, json_out):
    """Recursive text search (like ripgrep)."""
    from search_engine import search_engine
    inc = list(include) if include else None
    exc = list(exclude) if exclude else None
    with console.status(f"[cyan]Searching for '{pattern}'...[/cyan]"):
        results = search_engine.search_text(pattern, path, regex=regex, max_results=max_results,
                                            include_ext=inc, exclude_ext=exc)
    if json_out:
        console.print(json.dumps([{"file": m.file, "line": m.line, "text": m.text[:200]}
                                  for m in results.matches[:max_results]], indent=2))
        return
    if not results.matches:
        console.print(f"[yellow]No matches for '{pattern}' in {path}[/yellow]")
        return
    t = Table(box=box.ASCII)
    t.add_column("File"); t.add_column("Line"); t.add_column("Text")
    for m in results.matches[:max_results]:
        t.add_row(os.path.relpath(m.file, path)[:60], str(m.line), m.text[:120])
    console.print(t)
    console.print(f"[cyan]{results.total} matches in {results.elapsed:.2f}s[/cyan]")

@search.command()
@click.argument("pattern")
@click.argument("path", default=".")
@click.option("--fuzzy", "-f", is_flag=True, help="Fuzzy matching")
@click.option("--include", "-i", multiple=True, help="Extension filter")
@click.option("--max", "max_results", default=100, help="Max results")
def find(pattern, path, fuzzy, include, max_results):
    """Find files by name (like fd)."""
    from search_engine import search_engine
    inc = list(include) if include else None
    with console.status(f"[cyan]Finding files matching '{pattern}'...[/cyan]"):
        results = search_engine.search_files(pattern, path, fuzzy=fuzzy,
                                             max_results=max_results, include_ext=inc)
    if not results.matches:
        console.print(f"[yellow]No files matching '{pattern}' in {path}[/yellow]")
        return
    t = Table(box=box.ASCII)
    t.add_column("File"); t.add_column("Type")
    for m in results.matches[:max_results]:
        ext = os.path.splitext(m.file)[1] or "?"
        t.add_row(m.file[:80], ext)
    console.print(t)
    console.print(f"[cyan]{results.total} files found in {results.elapsed:.2f}s[/cyan]")

@search.command()
@click.argument("pattern")
@click.option("--path", default=".", help="Path to search")
@click.option("--preview", "-p", is_flag=True, help="Show preview context")
def interactive(pattern, path, preview):
    """Interactive search with fuzzy finder (like fzf)."""
    from search_engine import search_engine
    with console.status(f"[cyan]Searching...[/cyan]"):
        results = search_engine.search_text(pattern, path)
    if not results.matches:
        console.print(f"[yellow]No matches[/yellow]")
        return
    items = [f"{os.path.relpath(m.file, path)}:{m.line}: {m.text[:80]}" for m in results.matches[:200]]
    selected = search_engine.interactive_find(items)
    if selected:
        for s in selected:
            console.print(s)
    console.print(f"[cyan]{results.total} matches total[/cyan]")

@search.command()
def shistory():
    """Show search history."""
    from search_engine import search_engine
    stats = search_engine.stats()
    t = Table(box=box.ASCII, title="Search History")
    t.add_column("#"); t.add_column("Pattern"); t.add_column("Path"); t.add_column("Matches"); t.add_column("Time")
    for i, h in enumerate(stats.get("recent", []), 1):
        t.add_row(str(i), h.get("pattern","")[:30], h.get("path","")[:20], str(h.get("total",0)), f"{h.get('elapsed',0):.2f}s")
    console.print(t)

@search.command()
@click.argument("query")
@click.option("--files", "-f", default="", help="Comma-separated files")
def ai_s(query, files):
    """AI semantic code search."""
    file_list = [f.strip() for f in files.split(",") if f.strip()] if files else None
    results = ai_enhance.semantic_search(query, file_paths=file_list)
    if isinstance(results, list):
        t = Table(box=box.ASCII, title=f"AI Search: {query}")
        t.add_column("File"); t.add_column("Line"); t.add_column("Snippet")
        for r in results[:10]:
            t.add_row(r.get("file","?")[:30], str(r.get("line","?")), r.get("snippet","")[:80])
        console.print(t)
    else:
        console.print(str(results)[:500])


@search.command()
@click.argument("query")
@click.option("--limit", "-l", default=20, type=int)
@click.option("--dir", "-d", "sdir", default=".", help="Search directory")
def afuzzy(query, limit, sdir):
    """AI-enhanced fuzzy search with context."""
    from search_engine import search_engine
    raw = search_engine.search_text(query, path=sdir)
    if hasattr(raw, 'get') and raw.get("error"):
        console.print(f"[red]{raw['error']}[/red]"); return
    matches = []
    if hasattr(raw, 'get'):
        matches = raw.get("results", raw.get("matches", []))[:limit]
    elif hasattr(raw, '__iter__'):
        matches = list(raw)[:limit]
    if not matches:
        console.print("[yellow]No matches.[/yellow]"); return
    t = Table(box=box.ASCII, title=f"Fuzzy Search: {query}")
    t.add_column("File"); t.add_column("Line"); t.add_column("Content")
    for m in matches[:limit]:
        path = m.get("path", m.get("file", ""))[:30] if hasattr(m, 'get') else str(m)[:30]
        line = str(m.get("line", m.get("lineno", ""))) if hasattr(m, 'get') else ""
        content = m.get("line", m.get("content", ""))[:60] if hasattr(m, 'get') else str(m)[:60]
        t.add_row(path, line, content)
    console.print(t)

# === DATA COMMANDS (jq + yq hybrid) ===
@cli.group()
def data():
    """Query & transform data (jq/yq hybrid)."""

@data.command()
@click.argument("filepath")
@click.argument("expression", default=".")
@click.option("--raw", is_flag=True, help="Raw output (no pretty-print)")
def dquery(filepath, expression, raw):
    """Query JSON/YAML/CSV data (like jq)."""
    from data_query_engine import data_query
    with console.status(f"[cyan]Querying {filepath}...[/cyan]"):
        result = data_query.query(filepath, expression, raw=raw)
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error')}[/red]")
        return
    console.print(f"[dim]Format: {result['format']}[/dim]")
    console.print(str(result["output"])[:5000] or "(empty)")

@data.command()
@click.argument("filepath")
def dschema(filepath):
    """Infer data schema (schema inference)."""
    from data_query_engine import data_query
    with console.status(f"[cyan]Inferring schema...[/cyan]"):
        result = data_query.schema(filepath)
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error')}[/red]")
        return
    console.print(f"[bold]Schema ({result['format']}):[/bold]")
    console.print(result["output"][:5000])

@data.command()
@click.argument("filepath")
@click.option("--filter", "-f", help="Filter expression")
@click.option("--sort", help="Sort key")
@click.option("--reverse", is_flag=True)
@click.option("--limit", type=int, help="Max items")
def dtransform(filepath, filter, sort, reverse, limit):
    """Transform data: filter, sort, slice."""
    from data_query_engine import data_query
    with console.status(f"[cyan]Transforming...[/cyan]"):
        result = data_query.transform(filepath, filter_expr=filter, sort_key=sort,
                                       reverse=reverse, limit=limit)
    if not result.get("success"):
        console.print(f"[red]Error: {result.get('error')}[/red]")
        return
    t = Table(box=box.ASCII, title=f"{result['count']} items")
    items = result["data"]
    if items and isinstance(items[0], dict):
        keys = list(items[0].keys())[:10]
        for k in keys:
            t.add_column(k)
        for item in items[:50]:
            t.add_row(*[str(item.get(k, ""))[:40] for k in keys])
        console.print(t)
    else:
        console.print(result["output"][:5000])

@data.command()
def dhistory():
    """Show query history."""
    from data_query_engine import data_query
    stats = data_query.stats()
    t = Table(box=box.ASCII, title="Query History")
    t.add_column("#"); t.add_column("File"); t.add_column("Expr"); t.add_column("Format"); t.add_column("Time")
    for i, h in enumerate(stats.get("recent", []), 1):
        t.add_row(str(i), h.get("file","")[:30], h.get("expr","")[:20], h.get("format",""), f"{h.get('elapsed',0):.3f}s")
    console.print(t)


@data.command()
@click.argument("sample_file")
def ainfer(sample_file):
    """Infer JSON schema from data file."""
    import json as _json
    try:
        with open(sample_file, "r", encoding="utf-8") as f:
            raw = f.read()[:5000]
    except OSError as e:
        console.print(f"[red]{e}[/red]"); return
    try:
        parsed = _json.loads(raw)
        sample = _json.dumps(parsed, indent=2)[:4000]
    except _json.JSONDecodeError:
        sample = raw[:4000]
    console.print("[yellow]Inferring schema with AI...[/yellow]")
    schema = ai_enhance.schema_infer(sample)
    console.print(_json.dumps(schema, indent=2) if isinstance(schema, dict) else str(schema))


@data.command()
@click.argument("natural_query")
def aiquery(natural_query):
    """Build jq query from natural language."""
    console.print(f"[yellow]Translating:[/yellow] {natural_query}")
    result = ai_enhance.ai_query_builder(natural_query)
    console.print(f"[green]Query:[/green] {result}")

# === AI EDIT COMMANDS ===

@edit.command()
@click.argument("file_a", required=False, default=None)
@click.argument("file_b", required=False, default=None)
@click.option("--staged", is_flag=True)
@click.option("--stdin", "from_stdin", is_flag=True)
def explain(file_a, file_b, staged, from_stdin):
    """AI explain a diff in plain English."""
    import subprocess as _sp, difflib as _dl
    diff_text = ""
    if from_stdin: diff_text = sys.stdin.read()
    elif staged: r = _sp.run(["git", "diff", "--cached"], capture_output=True, text=True, timeout=30); diff_text = r.stdout
    elif file_a and file_b:
        with open(file_a) as f: ta = f.read()
        with open(file_b) as f: tb = f.read()
        diff_text = "\n".join(_dl.unified_diff(ta.splitlines(), tb.splitlines(), fromfile=file_a, tofile=file_b))
    elif file_a: r = _sp.run(["git", "diff", file_a], capture_output=True, text=True, timeout=30); diff_text = r.stdout
    else: r = _sp.run(["git", "diff"], capture_output=True, text=True, timeout=30); diff_text = r.stdout
    if not diff_text.strip(): console.print("[yellow]No diff.[/yellow]"); return
    console.print("[yellow]Analyzing diff with AI...[/yellow]")
    console.print(Panel(ai_enhance.explain_diff(diff_text), title="Diff Explanation", border_style="green"))

# === AGENT LOOP COMMANDS (Phase 4) ===

@cli.group()
def agent():
    """Agent loop: memory, chain, session."""


# === AGENT MEMORY ===

@agent.group()
def memory():
    """Persistent agent memory (store/recall/search)."""


@memory.command("store")
@click.argument("key")
@click.argument("data")
@click.option("--meta", "-m", default="", help="JSON metadata string")
def memory_store(key, data, meta):
    """Store a memory entry."""
    metadata = json.loads(meta) if meta else {}
    result = agent_memory.store(key, data, metadata)
    console.print(f"[green]Stored[/green] [bold]{result['stored']}[/bold] ({result['size']} bytes)")


@memory.command("recall")
@click.argument("key")
def memory_recall(key):
    """Recall a memory entry by key."""
    entry = agent_memory.recall(key)
    if entry is None:
        console.print(f"[yellow]No memory found for key:[/yellow] {key}")
        return
    t = Table(box=box.ASCII, title=f"Memory: {key}")
    t.add_column("Field"); t.add_column("Value")
    t.add_row("Data", str(entry["data"])[:200])
    t.add_row("Created", datetime.fromtimestamp(entry["created"]).isoformat() if entry.get("created") else "N/A")
    t.add_row("Updated", datetime.fromtimestamp(entry["updated"]).isoformat() if entry.get("updated") else "N/A")
    if entry.get("metadata"):
        t.add_row("Metadata", str(entry["metadata"])[:200])
    console.print(t)


@memory.command("search")
@click.argument("query")
@click.option("--top", "-t", default=10, type=int)
def memory_search(query, top):
    """Search memories by keyword."""
    results = agent_memory.search(query, top_k=top)
    if not results:
        console.print("[yellow]No matches.[/yellow]"); return
    t = Table(box=box.ASCII, title=f"Search: {query}")
    t.add_column("Key"); t.add_column("Data (truncated)")
    for r in results:
        t.add_row(r.get("key", "?"), str(r.get("data", ""))[:80])
    console.print(t)


@memory.command("forget")
@click.argument("key")
def memory_forget(key):
    """Delete a memory entry."""
    if agent_memory.forget(key):
        console.print(f"[green]Forgot[/green] {key}")
    else:
        console.print(f"[yellow]Not found:[/yellow] {key}")


@memory.command("list")
@click.option("--prefix", "-p", default="", help="Filter by key prefix")
@click.option("--json", "as_json", is_flag=True, help="Output as JSON")
def memory_list(prefix, as_json):
    """List all memory keys."""
    keys = agent_memory.list_keys(prefix=prefix or None)
    if not keys:
        console.print("[yellow]No memories stored.[/yellow]"); return
    if as_json:
        console.print(json.dumps(keys, indent=2))
    else:
        for k in keys:
            console.print(f"  [cyan]{k}[/cyan]")


@memory.command("stats")
def memory_stats():
    """Show memory statistics."""
    s = agent_memory.stats()
    t = Table(box=box.ASCII, title="Memory Stats")
    t.add_column("Metric"); t.add_column("Value")
    t.add_row("Total entries", str(s["total_entries"]))
    t.add_row("Total size", f"{s['total_size_kb']} KB")
    console.print(t)
    if s["keys"]:
        console.print("[bold]Recent keys:[/bold]")
        for k in s["keys"]:
            console.print(f"  [dim]{k}[/dim]")
        if s["has_more"]:
            console.print(f"  ... and {s['total_entries'] - len(s['keys'])} more")


# === AGENT SESSION ===

@agent.group()
def session():
    """Interactive agent session management."""


@session.command("start")
@click.argument("session_id", required=False, default=None)
def session_start(session_id):
    """Start a new agent session."""
    sid = agent_memory.session_start(session_id)
    console.print(f"[green]Session started:[/green] [bold]{sid}[/bold]")


@session.command("log")
@click.argument("session_id")
@click.argument("event_type")
@click.argument("content")
def session_log_cmd(session_id, event_type, content):
    """Log an event to a session."""
    if agent_memory.session_log(session_id, event_type, content):
        console.print(f"[green]Logged[/green] {event_type} to {session_id}")
    else:
        console.print(f"[yellow]Session {session_id} not found. Start it first.[/yellow]")


@session.command("save")
@click.argument("session_id")
def session_save(session_id):
    """Save session to persistent memory."""
    if agent_memory.session_save(session_id):
        console.print(f"[green]Session saved:[/green] {session_id}")
    else:
        console.print(f"[yellow]No active session buffer for {session_id}[/yellow]")


@session.command("load")
@click.argument("session_id")
def session_load(session_id):
    """Load a saved session."""
    data = agent_memory.session_load(session_id)
    if data is None:
        console.print(f"[yellow]No saved session:[/yellow] {session_id}")
        return
    t = Table(box=box.ASCII, title=f"Session: {session_id}")
    t.add_column("#"); t.add_column("Type"); t.add_column("Content"); t.add_column("Time")
    events = data.get("events", [])
    if isinstance(events, list):
        for i, ev in enumerate(events):
            ts = datetime.fromtimestamp(ev.get("timestamp", 0)).isoformat() if isinstance(ev, dict) else ""
            t.add_row(str(i+1), ev.get("type", "?") if isinstance(ev, dict) else "?",
                      str(ev.get("content", ""))[:60] if isinstance(ev, dict) else str(ev)[:60], ts)
    console.print(t)


@session.command("list")
def session_list():
    """List all sessions."""
    sessions = agent_memory.session_list()
    if not sessions:
        console.print("[yellow]No sessions.[/yellow]"); return
    t = Table(box=box.ASCII, title="Sessions")
    t.add_column("Session ID"); t.add_column("Events"); t.add_column("Created")
    for s in sessions:
        created = datetime.fromtimestamp(s["created"]).isoformat() if s.get("created") else "N/A"
        t.add_row(s["session_id"], str(s["events"]), created)
    console.print(t)


# === TOOL CHAIN ===

@agent.group()
def chain():
    """Tool chain pipelines (compose commands)."""


@chain.command("define")
@click.argument("name")
@click.argument("steps_json", required=False, default=None)
@click.option("--file", "-f", type=click.Path(exists=True), help="JSON file with steps")
@click.option("--desc", "-d", default="", help="Chain description")
def chain_define(name, steps_json, file, desc):
    """Define a chain from JSON steps (inline or --file)."""
    try:
        if file:
            with open(file, "r", encoding="utf-8") as f:
                steps = json.load(f)
        elif steps_json:
            steps = json.loads(steps_json)
        else:
            console.print("[red]Provide steps as JSON string or --file[/red]"); return
        if not isinstance(steps, list):
            console.print("[red]Steps must be a JSON array[/red]"); return
        tool_chain.define(name, steps, description=desc)
        console.print(f"[green]Chain defined:[/green] [bold]{name}[/bold] ({len(steps)} steps)")
    except (json.JSONDecodeError, ValueError) as e:
        console.print(f"[red]Invalid JSON: {e}[/red]")


@chain.command("run")
@click.argument("name")
@click.option("--input", "-i", multiple=True, help="Inputs as key=value")
@click.option("--quiet", "-q", is_flag=True, help="Suppress step output")
def chain_run(name, input, quiet):
    """Execute a tool chain."""
    inputs = {}
    for kv in input:
        if "=" in kv:
            k, v = kv.split("=", 1)
            inputs[k] = v
    result = tool_chain.run(name, inputs=inputs, verbose=not quiet)
    if "error" in result:
        console.print(f"[red]{result['error']}[/red]"); return
    console.print()
    t = Table(box=box.ASCII, title=f"Chain: {name}")
    t.add_column("Step"); t.add_column("Tool"); t.add_column("Status")
    for s in result["steps"]:
        status = "[green]OK[/green]" if s["success"] else "[red]FAIL[/red]"
        t.add_row(s["id"], s["tool"], status)
    console.print(t)
    if not quiet and result.get("outputs"):
        console.print("[bold]Captured outputs:[/bold]")
        for k, v in result["outputs"].items():
            console.print(f"  [cyan]{k}[/cyan] = {v[:100]}")


@chain.command("list")
def chain_list():
    """List all defined chains."""
    chains = tool_chain.list_chains()
    if not chains:
        console.print("[yellow]No chains defined.[/yellow]"); return
    t = Table(box=box.ASCII, title="Tool Chains")
    t.add_column("Name"); t.add_column("Description"); t.add_column("Steps")
    for c in chains:
        t.add_row(c["name"], c.get("description", "")[:50], str(c["steps"]))
    console.print(t)


@chain.command("show")
@click.argument("name")
def chain_show(name):
    """Show chain definition."""
    c = tool_chain.get(name)
    if not c:
        console.print(f"[yellow]Chain not found:[/yellow] {name}"); return
    console.print(json.dumps(c, indent=2))


@chain.command("delete")
@click.argument("name")
def chain_delete(name):
    """Delete a chain."""
    if tool_chain.delete(name):
        console.print(f"[green]Deleted chain:[/green] {name}")
    else:
        console.print(f"[yellow]Chain not found:[/yellow] {name}")


# === SYSTEM MONITOR COMMANDS (btop-style) ===
@cli.group()
def sys():
    """System monitoring (btop-style dashboard)."""

@sys.command()
def stop():
    """Show CPU, memory, disk, network summary."""
    try:
        import psutil
    except ImportError:
        console.print("[red]psutil not installed. Run: pip install psutil[/red]")
        return
    s = sysmon.summary()
    t = Table(box=box.ASCII, title="System Health")
    t.add_column("Metric"); t.add_column("Value")
    t.add_row("CPU", f"{s['cpu_percent']}%")
    t.add_row("Memory", f"{s['memory_percent']}% ({s['memory_used_gb']}/{s['memory_total_gb']}GB)")
    t.add_row("Disk", f"{s['disk_percent']}% ({s['disk_used_gb']}GB used)")
    t.add_row("Network Connections", str(s['connections']))
    t.add_row("Processes", str(s['processes']))
    console.print(t)
    if s.get("top_processes"):
        t2 = Table(box=box.ASCII, title="Top Processes")
        t2.add_column("Name"); t2.add_column("CPU%"); t2.add_column("MEM%")
        for name, cpu_p, mem_p in s["top_processes"]:
            t2.add_row(name[:30], f"{cpu_p:.1f}", f"{mem_p:.1f}")
        console.print(t2)


@gh.command()
@click.argument("pr_number", required=False, default=None)
@click.option("--from-current", is_flag=True)
def summarize(pr_number, from_current):
    """AI generate PR summary."""
    import subprocess as _sp
    try:
        if pr_number: r = _sp.run(["gh", "pr", "view", pr_number, "--json", "title,body,files,additions,deletions,author,state"], capture_output=True, text=True, timeout=30)
        elif from_current: r = _sp.run(["gh", "pr", "view", "--json", "title,body,files,additions,deletions,author,state"], capture_output=True, text=True, timeout=30)
        else: console.print("[yellow]Provide PR number or --from-current[/yellow]"); return
        if r.returncode != 0: console.print(f"[red]gh error: {r.stderr}[/red]"); return
        pr_data = json.loads(r.stdout)
    except Exception as e: console.print(f"[red]Error: {e}[/red]"); return
    console.print("[yellow]Generating PR summary...[/yellow]")
    console.print(Panel(ai_enhance.summarize_pr(pr_data), title="PR Summary", border_style="cyan"))

@sys.command()
@click.option("--interval", "-i", default=1.0, type=float, help="Refresh interval (s)")
@click.option("--count", "-c", default=5, type=int, help="Number of samples")
def spoll(interval, count):
    """Poll CPU/memory in real-time (like btop live view)."""
    try:
        import psutil
    except ImportError:
        console.print("[red]psutil required[/red]"); return
    for i in range(count):
        from sysmon import sysmon
        cpu = sysmon.cpu()
        mem = sysmon.memory()
        bar_len = 20
        cpu_pct = cpu.percent / 100.0
        mem_pct = mem.percent / 100.0
        cpu_filled = int(cpu_pct * bar_len)
        mem_filled = int(mem_pct * bar_len)
        cpu_bar = "#" * cpu_filled + "-" * (bar_len - cpu_filled)
        mem_bar = "#" * mem_filled + "-" * (bar_len - mem_filled)
        console.print(f"[cyan]CPU:[/cyan] {cpu.percent:5.1f}% |{cpu_bar}| [cyan]MEM:[/cyan] {mem.percent:5.1f}% |{mem_bar}|")
        if i < count - 1:
            time.sleep(interval)

@sys.command()
def scpu():
    """Show detailed CPU info."""
    info = sysmon.cpu()
    t = Table(box=box.ASCII, title="CPU")
    t.add_column("Metric"); t.add_column("Value")
    t.add_row("Usage", f"{info.percent}%")
    t.add_row("Physical cores", str(info.count_physical))
    t.add_row("Logical cores", str(info.count_logical))
    t.add_row("Frequency", f"{info.freq_current:.0f} MHz" if info.freq_current else "N/A")
    if info.load_1m:
        t.add_row("Load (1m)", f"{info.load_1m:.2f}")
    console.print(t)
    if info.per_cpu:
        bar = ""
        for i, p in enumerate(info.per_cpu):
            bar += f" C{i}:{p:4.0f}% "
            if (i+1) % 4 == 0:
                bar += "\n"
        console.print(bar)

@sys.command()
def smem():
    """Show memory info."""
    info = sysmon.memory()
    t = Table(box=box.ASCII, title="Memory")
    t.add_column("Metric"); t.add_column("Value")
    t.add_row("RAM", f"{sysmon._format_bytes(info.used)} / {sysmon._format_bytes(info.total)} ({info.percent}%)")
    t.add_row("Available", sysmon._format_bytes(info.available))
    t.add_row("Swap", f"{sysmon._format_bytes(info.swap_used)} / {sysmon._format_bytes(info.swap_total)} ({info.swap_percent}%)" if info.swap_total else "N/A")
    console.print(t)

@sys.command()
@click.argument("path", default=".")
def sdisk(path):
    """Show disk usage (like duf)."""
    info = sysmon.disk_usage(path)
    if "error" in info:
        console.print(f"[red]{info['error']}[/red]"); return
    t = Table(box=box.ASCII, title=f"Disk: {info['path']}")
    t.add_column("Metric"); t.add_column("Value")
    t.add_row("Total", sysmon._format_bytes(info["total"]))
    t.add_row("Used", f"{sysmon._format_bytes(info['used'])} ({info['percent']}%)")
    t.add_row("Free", sysmon._format_bytes(info["free"]))
    console.print(t)

@sys.command()
@click.option("--sort", default="cpu", help="Sort: cpu/mem/pid/name")
@click.option("--limit", "-l", default=20, type=int, help="Number of processes")
def sprocs(sort, limit):
    """List processes (like btop process list)."""
    procs = sysmon.processes(sort_by=sort, limit=limit)
    t = Table(box=box.ASCII, title=f"Processes (sorted by {sort})")
    t.add_column("PID"); t.add_column("Name"); t.add_column("CPU%"); t.add_column("MEM%"); t.add_column("Status")
    for p in procs:
        t.add_row(str(p.pid), p.name[:25], f"{p.cpu_percent:.1f}", f"{p.memory_percent:.1f}", p.status)
    console.print(t)


@sys.command()
@click.option("--interval", "-i", default=2.0, type=float)
def aanomaly(interval):
    """AI detect system anomalies."""
    from sysmon import sysmon; import time
    console.print(f"[yellow]Sampling for {interval}s...[/yellow]"); time.sleep(0.5)
    cpu_info = sysmon.cpu(); mem_info = sysmon.memory()
    metrics = {"cpu_percent": cpu_info.percent, "cpu_freq": cpu_info.freq_current, "cpu_cores": cpu_info.count_logical,
               "memory_percent": mem_info.percent, "memory_used_gb": mem_info.used / (1024**3),
               "memory_total_gb": mem_info.total / (1024**3), "processes": len(sysmon.processes())}
    console.print("[yellow]Analyzing with AI...[/yellow]")
    result = ai_enhance.detect_anomaly(metrics)
    anomalies = result.get("anomalies", []) if isinstance(result, dict) else []
    if not anomalies: console.print("[green]No anomalies.[/green]"); return
    t = Table(box=box.ASCII, title="Anomalies")
    t.add_column("Type"); t.add_column("Severity"); t.add_column("Value"); t.add_column("Action")
    for a in anomalies: t.add_row(a.get("type","?"), a.get("severity","?"), str(a.get("value","?")), a.get("action","")[:40])
    console.print(t)

@sys.command()
@click.option("--path", "-p", default=".")
def aclean(path):
    """AI suggest disk cleanup actions."""
    from sysmon import sysmon; from pathlib import Path; import os as _os
    console.print("[yellow]Scanning...[/yellow]")
    large = []
    for d in [".venv", "node_modules", "__pycache__", ".git", "dist", "build", "target"]:
        fp = _os.path.join(path, d)
        if _os.path.isdir(fp):
            try:
                size = sum(f.stat().st_size for f in Path(fp).rglob("*") if f.is_file()) / (1024**3)
                if size > 0.05: large.append({"path": d, "size_gb": round(size, 2)})
            except OSError: continue
    info = {"path": path, "large_dirs": large}
    console.print("[yellow]Generating cleanup suggestions...[/yellow]")
    result = ai_enhance.suggest_cleanup(info)
    suggestions = result.get("suggestions", []) if isinstance(result, dict) else []
    if not suggestions: console.print("[green]No suggestions.[/green]"); return
    t = Table(box=box.ASCII, title="Cleanup Suggestions")
    t.add_column("Target"); t.add_column("Action"); t.add_column("Size(MB)"); t.add_column("Reason")
    for s in suggestions: t.add_row(s.get("target","")[:30], s.get("action","")[:15], str(s.get("size_mb","?")), s.get("reason","")[:40])
    console.print(t)

# === DELTA COMMANDS (side-by-side syntax-highlighted diff viewer) ===

@cli.group()
def delta():
    """Syntax-highlighted diff viewer (delta-style)."""

@delta.command()
@click.argument("file_a")
@click.argument("file_b", required=False, default=None)
@click.option("--context", "-c", default=3, type=int)
@click.option("--stats", "show_stats", is_flag=True)
def ddiff(file_a, file_b, context, show_stats):
    """Side-by-side diff between two files."""
    if show_stats:
        s = delta_viewer.stats(file_a, file_b)
        t = Table(box=box.ASCII, title="Diff Stats")
        t.add_column("Metric"); t.add_column("Value")
        t.add_row("Insertions", str(s["insertions"])); t.add_row("Deletions", str(s["deletions"]))
        t.add_row("Files", str(s["files_changed"])); t.add_row("Chunks", str(s["chunks"]))
        console.print(t); return
    result = delta_viewer.side_by_side(file_a, file_b, context=context)
    if isinstance(result, tuple) and len(result) == 2:
        left, right = result
        from rich.table import Table as RTable
        rt = RTable(box=box.SIMPLE, padding=(0, 1), show_header=False, width=120)
        rt.add_column(f"a/{file_a}", style="red", no_wrap=True)
        rt.add_column(f"b/{file_b or file_a}", style="green", no_wrap=True)
        for i in range(max(len(left), len(right))):
            rt.add_row((left[i] if i < len(left) else "")[:60], (right[i] if i < len(right) else "")[:60])
        console.print(rt)
    else:
        for line in result: console.print(delta_viewer.highlight(line))

@delta.command()
@click.argument("file_a")
@click.argument("file_b", required=False, default=None)
def dstats(file_a, file_b):
    """Show diff statistics."""
    s = delta_viewer.stats(file_a, file_b)
    t = Table(box=box.ASCII, title="Diff Stats")
    t.add_column("Metric"); t.add_column("Value")
    t.add_row("Insertions", str(s["insertions"])); t.add_row("Deletions", str(s["deletions"]))
    t.add_row("Files", str(s["files_changed"])); t.add_row("Chunks", str(s["chunks"]))
    console.print(t)

@delta.command()
@click.argument("file_a")
@click.argument("file_b", required=False, default=None)
def dexplain(file_a, file_b):
    """Show diff + AI explanation in one shot."""
    diff_text = "\n".join(delta_viewer.diff(file_a, file_b))
    if not diff_text.strip(): console.print("[yellow]No diff.[/yellow]"); return
    console.print("[bold]Diff:[/bold]")
    for line in diff_text.split("\n"): console.print(delta_viewer.highlight(line))
    console.print()
    console.print("[bold yellow]AI Explanation:[/bold yellow]")
    console.print(Panel(ai_enhance.explain_diff(diff_text), border_style="green"))

if __name__ == "__main__":
    cli()
