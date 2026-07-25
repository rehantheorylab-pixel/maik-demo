#!/usr/bin/env python3
"""MAIK TUI — full-featured Textual app with hierarchy, workflow, agent management."""
import sys, os, asyncio, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input, RichLog, TabbedContent, TabPane, Label, Button, ListView, ListItem, Tree
from textual.containers import Horizontal, Vertical, ScrollableContainer, Container
from textual.binding import Binding
from textual.screen import Screen
from textual.reactive import reactive
from textual import work
from rich.text import Text
from rich.panel import Panel as RichPanel
from rich.table import Table as RichTable
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.tree import Tree as RichTree

from config import TokenBudget, council, api_configs, WORKFLOW_CHAINS, APIConfig
from router_engine import route, cache_stats
from tree_engine import execute, ceo_execution_breakdown
from learn_engine import learn, get_stats
from scheduler_engine import scheduler
from memory_engine import thought_vdb, l1_memory
from evolution_engine import pbt
from safety_engine import stop_light
from boolean_engine import voter
from meta_controller import prompt_selector, workflow_engine, PROMPT_TEMPLATES
from corporate_engine import org_chart, agent_tracker, corp_library

class AskTab(Static):
    def compose(self):
        yield Static("[bold cyan]Ask MAIK[/bold cyan]", id="ask-title")
        yield Input(placeholder="Ask anything...", id="ask-input")
        yield Button("Ask", id="ask-btn", variant="primary")
        yield RichLog(id="ask-output", highlight=True, markup=True)

    async def on_button_pressed(self, event: Button.Pressed):
        inp = self.query_one("#ask-input", Input)
        if inp.value:
            await self.run_ask(inp.value)

    async def on_input_submitted(self, event: Input.Submitted):
        if event.value:
            await self.run_ask(event.value)

    async def run_ask(self, problem):
        out = self.query_one("#ask-output", RichLog); out.clear()
        out.write("[cyan]Routing...[/cyan]")
        budget = TokenBudget(total=100000)
        r = route(problem, "", budget)
        out.write(f"[bold]{r['ceo_name']}[/bold]  →  [cyan]{r['expert']}[/cyan]  (conf={r['confidence']:.0%})")
        out.write("[cyan]Executing...[/cyan]")
        result = execute(problem, "", budget)
        out.clear()
        md = Markdown(result['solution'][:5000] or "(no output)")
        out.write(md)
        out.write(f"\n[dim]conf={result['confidence']:.0%}  agents={len(result['agents_used'])}[/dim]")
        learn(problem, result['solution'][:500], "success", result['agents_used'], result['confidence'], 0, 0)

class StatusTab(Static):
    def on_mount(self):
        self.refresh()
        self.set_interval(5, self.refresh)

    def compose(self):
        yield Static("[bold cyan]System Status[/bold cyan]", id="status-title")
        yield RichLog(id="status-output", highlight=True, markup=True)
        yield Button("Refresh", id="status-refresh")

    def on_button_pressed(self, event: Button.Pressed):
        self.refresh()

    def refresh(self):
        out = self.query_one("#status-output", RichLog); out.clear()
        stats = get_stats(); cs = cache_stats(); s = scheduler.stats(); ps = pbt.stats()
        at = agent_tracker.stats(); oc = org_chart.total_count()
        t = RichTable(box=None)
        t.add_column("Metric", style="cyan"); t.add_column("Value")
        t.add_row("Runs", str(stats['total_runs']))
        t.add_row("Success Rate", f"{stats['success_rate']:.0%}")
        t.add_row("Cache", f"{cs['size']} entries ({cs['hit_rate']:.0%} hit)")
        t.add_row("Schedule", f"{s['queue_size']} queued, {s['completed']} done")
        t.add_row("PBT Gen", str(ps['generation']))
        t.add_row("Council", f"{council.num_ceos} CEOs ({council.profile})")
        t.add_row("APIs", str(len(api_configs)))
        t.add_row("Avg Confidence", f"{stats['avg_confidence']:.0%}")
        t.add_row("Org Chart", f"{oc['ceos']} CEOs, {oc['managers']} Mgrs, {oc['employees']} Emps")
        t.add_row("Tracked Agents", f"{at['total']} (Avg ELO: {at['avg_elo']})")
        t.add_row("Stop Light", stop_light.status().upper())
        out.write(t)
        board = agent_tracker.leaderboard(5)
        if board:
            tt = RichTable(box=None, title="ELO Leaderboard")
            tt.add_column("Agent", style="cyan"); tt.add_column("ELO"); tt.add_column("Success"); tt.add_column("Status")
            for a in board:
                tt.add_row(a["id"], str(a["elo"]), f"{a['success_rate']:.0%}", a["status"])
            out.write(tt)

class CouncilTab(Static):
    def on_mount(self): self.refresh()
    def compose(self):
        yield Static("[bold cyan]Executive Council & Org Chart[/bold cyan]", id="council-title")
        yield RichLog(id="council-output", highlight=True, markup=True)
        yield Button("Refresh", id="council-refresh")

    def on_button_pressed(self, event: Button.Pressed): self.refresh()

    def refresh(self):
        out = self.query_one("#council-output", RichLog); out.clear()
        t = RichTable(box=None, title="Executive Council")
        t.add_column("CEO", style="cyan", no_wrap=True); t.add_column("Name")
        t.add_column("Managers"); t.add_column("APIs"); t.add_column("Budget")
        for c in council.list_ceos():
            t.add_row(c['id'], c['name'], str(c['managers']), str(c['api_count']), c['budget'])
        out.write(t)
        mind = org_chart.get_mind_map()
        if mind:
            tree = RichTree("[bold cyan]Org Chart[/bold cyan]")
            for ceo_id, cd in mind.items():
                ceo_b = tree.add(f"[bold green]{cd['name']}[/bold green] [dim]({ceo_id})[/dim]")
                mgrs = cd.get("managers", {})
                if not mgrs:
                    ceo_b.add("[dim]No managers[/dim]")
                for mgr_id, md in mgrs.items():
                    mgr_b = ceo_b.add(f"[yellow]{md['name']}[/yellow] [dim]({mgr_id})[/dim]")
                    emps = md.get("employees", [])
                    if not emps:
                        mgr_b.add("[dim]No employees[/dim]")
                    for e in emps:
                        s = "🟢" if e["status"]=="idle" else "🟡"
                        mgr_b.add(f"{s} [white]{e['name']}[/white] [dim]({e['role']})[/dim]")
            out.write(tree)

class OrgTab(Static):
    def on_mount(self): self.refresh()
    def compose(self):
        yield Static("[bold cyan]Org Chart Manager[/bold cyan]", id="org-title")
        yield Input(placeholder="CEO ID (for add ops)", id="org-ceo-input")
        yield Horizontal(
            Button("Add CEO", id="org-add-ceo", variant="primary"),
            Button("Add Manager", id="org-add-mgr"),
            Button("Add Employee", id="org-add-emp"),
        )
        yield RichLog(id="org-output", highlight=True, markup=True)

    def on_button_pressed(self, event: Button.Pressed):
        inp = self.query_one("#org-ceo-input", Input)
        ceo_id = inp.value or ""
        if event.button.id == "org-add-ceo":
            self.add_ceo_dialog()
        elif event.button.id == "org-add-mgr":
            self.add_mgr_dialog(ceo_id)
        elif event.button.id == "org-add-emp":
            self.add_emp_dialog(ceo_id)

    def add_ceo_dialog(self):
        from textual.screen import ModalScreen
        class AddCEOScreen(ModalScreen):
            def compose(self):
                yield Vertical(
                    Static("[bold]Add CEO[/bold]"),
                    Input(placeholder="CEO ID (e.g., ceo-new)", id="ceo-id"),
                    Input(placeholder="CEO Name", id="ceo-name"),
                    Horizontal(Button("Add", id="add"), Button("Cancel", id="cancel")),
                )
            def on_button_pressed(self, event):
                if event.button.id == "add":
                    cid = self.query_one("#ceo-id", Input).value
                    nm = self.query_one("#ceo-name", Input).value
                    if cid and nm:
                        org_chart.add_ceo(cid, nm)
                        council.add_ceo(nm, ["general"])
                self.app.pop_screen()
        self.app.push_screen(AddCEOScreen())
        self.refresh_later()

    def add_mgr_dialog(self, ceo_id):
        from textual.screen import ModalScreen
        class AddMgrScreen(ModalScreen):
            def compose(self):
                yield Vertical(
                    Static(f"[bold]Add Manager under {ceo_id or '?'}[/bold]"),
                    Input(placeholder="Manager ID", id="mgr-id"),
                    Input(placeholder="Manager Name", id="mgr-name"),
                    Horizontal(Button("Add", id="add"), Button("Cancel", id="cancel")),
                )
            def on_button_pressed(self, event):
                if event.button.id == "add" and ceo_id:
                    mid = self.query_one("#mgr-id", Input).value
                    nm = self.query_one("#mgr-name", Input).value
                    if mid and nm:
                        org_chart.add_manager(ceo_id, mid, nm)
                        agent_tracker.register(mid, "manager")
                self.app.pop_screen()
        self.app.push_screen(AddMgrScreen())
        self.refresh_later()

    def add_emp_dialog(self, ceo_id):
        from textual.screen import ModalScreen
        class AddEmpScreen(ModalScreen):
            def compose(self):
                yield Vertical(
                    Static(f"[bold]Add Employee under {ceo_id or '?'}[/bold]"),
                    Input(placeholder="Manager ID", id="emp-mgr"),
                    Input(placeholder="Employee ID", id="emp-id"),
                    Input(placeholder="Employee Name", id="emp-name"),
                    Input(placeholder="Role (default: employee)", id="emp-role"),
                    Horizontal(Button("Add", id="add"), Button("Cancel", id="cancel")),
                )
            def on_button_pressed(self, event):
                if event.button.id == "add" and ceo_id:
                    mid = self.query_one("#emp-mgr", Input).value
                    eid = self.query_one("#emp-id", Input).value
                    nm = self.query_one("#emp-name", Input).value
                    role = self.query_one("#emp-role", Input).value or "employee"
                    if mid and eid and nm:
                        org_chart.add_employee(ceo_id, mid, eid, nm, role)
                        agent_tracker.register(eid, role)
                self.app.pop_screen()
        self.app.push_screen(AddEmpScreen())
        self.refresh_later()

    def refresh_later(self):
        asyncio.get_event_loop().call_later(0.5, self.refresh)

    def refresh(self):
        out = self.query_one("#org-output", RichLog); out.clear()
        mind = org_chart.get_mind_map()
        if not mind:
            out.write("[yellow]No CEOs yet. Use Add CEO to start.[/yellow]")
            return
        tree = RichTree("[bold cyan]Corporate Hierarchy[/bold cyan]")
        for ceo_id, cd in mind.items():
            ceo_b = tree.add(f"[bold green]👤 {cd['name']}[/bold green] [dim]({ceo_id})[/dim]")
            for mgr_id, md in cd.get("managers", {}).items():
                mgr_b = ceo_b.add(f"[yellow]👤 {md['name']}[/yellow] [dim]({mgr_id})[/dim]")
                for e in md.get("employees", []):
                    s = "🟢" if e["status"]=="idle" else "🟡"
                    mgr_b.add(f"{s} [white]{e['name']}[/white] [dim]({e['role']}, {e['tasks']} tasks)[/dim]")
            ceo_b.add("[dim]Tip: Use buttons above to add managers/employees[/dim]")
        out.write(tree)

class WorkflowTab(Static):
    def on_mount(self): self.refresh()
    def compose(self):
        yield Static("[bold cyan]Workflow Chains[/bold cyan]", id="wf-title")
        yield Input(placeholder="Select chain (e.g., code-verify):", id="wf-chain-input")
        yield Input(placeholder="Task description:", id="wf-task-input")
        yield Horizontal(
            Button("Show Details", id="wf-details"),
            Button("Run Chain", id="wf-run", variant="primary"),
        )
        yield RichLog(id="wf-output", highlight=True, markup=True)

    def on_button_pressed(self, event: Button.Pressed):
        chain = self.query_one("#wf-chain-input", Input).value
        task = self.query_one("#wf-task-input", Input).value
        out = self.query_one("#wf-output", RichLog); out.clear()
        if event.button.id == "wf-details":
            c = WORKFLOW_CHAINS.get(chain)
            if c:
                out.write(f"[bold]{c['name']}[/bold] — {len(c['steps'])} steps")
                for i, step in enumerate(c["steps"]):
                    out.write(f"  Step {i+1}: [cyan]{step.role}[/cyan] — {step.system_prompt[:80]}...")
            else:
                out.write(f"[red]Chain '{chain}' not found[/red]")
        elif event.button.id == "wf-run" and chain and task:
            out.write(f"[bold]Running {chain}...[/bold]")
            result = workflow_engine.run_all_simulated(chain, task)
            out.write(f"Run ID: {result['run_id']} | Duration: {result['duration_s']:.2f}s")
            for o in result["outputs"]:
                out.write(f"  {o}")

    def refresh(self):
        out = self.query_one("#wf-output", RichLog); out.clear()
        for cid, chain in WORKFLOW_CHAINS.items():
            out.write(f"[cyan]{cid:<16}[/cyan] {chain['name']:<20} [dim]{len(chain['steps'])} steps[/dim]")

class ApiTab(Static):
    def on_mount(self): self.refresh()
    def compose(self):
        yield Static("[bold cyan]API Configurations[/bold cyan]", id="api-title")
        yield Input(placeholder="Provider (e.g., openrouter)", id="api-provider")
        yield Input(placeholder="Model (e.g., gpt-4)", id="api-model")
        yield Horizontal(
            Button("Add API", id="api-add", variant="primary"),
            Button("Remove Selected", id="api-remove"),
            Button("Toggle", id="api-toggle"),
        )
        yield RichLog(id="api-output", highlight=True, markup=True)

    def on_button_pressed(self, event: Button.Pressed):
        out = self.query_one("#api-output", RichLog)
        provider = self.query_one("#api-provider", Input).value
        model = self.query_one("#api-model", Input).value
        if event.button.id == "api-add" and provider and model:
            ap = APIConfig(f"api-{len(api_configs)+1}", provider, model)
            api_configs.append(ap)
            self.refresh()
        elif event.button.id == "api-remove" and api_configs:
            api_configs.pop()
            self.refresh()
        elif event.button.id == "api-toggle" and api_configs:
            api_configs[-1].enabled = not api_configs[-1].enabled
            self.refresh()

    def refresh(self):
        out = self.query_one("#api-output", RichLog); out.clear()
        t = RichTable(box=None, title=f"APIs ({len(api_configs)})")
        t.add_column("ID", style="cyan"); t.add_column("Provider"); t.add_column("Model")
        t.add_column("Enabled")
        for a in api_configs:
            t.add_row(a.id, a.provider, a.model, "✓" if a.enabled else "✗")
        out.write(t)

class AgentsTab(Static):
    def on_mount(self): self.refresh()
    def compose(self):
        yield Static("[bold cyan]Agent Performance[/bold cyan]", id="agents-title")
        yield Input(placeholder="Agent ID to register:", id="agent-id")
        yield Input(placeholder="Role:", id="agent-role")
        yield Horizontal(
            Button("Register", id="agent-reg", variant="primary"),
            Button("Refresh", id="agent-ref"),
        )
        yield RichLog(id="agents-output", highlight=True, markup=True)

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "agent-reg":
            aid = self.query_one("#agent-id", Input).value
            role = self.query_one("#agent-role", Input).value
            if aid and role:
                agent_tracker.register(aid, role)
                self.refresh()
        elif event.button.id == "agent-ref":
            self.refresh()

    def refresh(self):
        out = self.query_one("#agents-output", RichLog); out.clear()
        stats = agent_tracker.stats()
        out.write(f"[bold]Total:[/bold] {stats['total']} | Active: {stats['active']} | Avg ELO: {stats['avg_elo']} | Avg Success: {stats['avg_success_rate']:.1%}")
        board = agent_tracker.leaderboard(15)
        if board:
            t = RichTable(box=None, title="ELO Leaderboard")
            t.add_column("Agent", style="cyan"); t.add_column("Role"); t.add_column("ELO")
            t.add_column("Tasks"); t.add_column("Success"); t.add_column("Status")
            for a in board:
                t.add_row(a["id"], a["role"], str(a["elo"]), str(a["tasks"]), f"{a['success_rate']:.0%}", a["status"])
            out.write(t)

class PromptTab(Static):
    def compose(self):
        yield Static("[bold cyan]Prompt Manager[/bold cyan]", id="prompt-title")
        yield Input(placeholder="Role name:", id="prompt-role")
        yield Input(placeholder="Task for preview:", id="prompt-task")
        yield Horizontal(
            Button("Preview", id="prompt-preview"),
            Button("Set Custom", id="prompt-set"),
            Button("Reset", id="prompt-reset"),
        )
        yield RichLog(id="prompt-output", highlight=True, markup=True)

    def on_button_pressed(self, event: Button.Pressed):
        out = self.query_one("#prompt-output", RichLog); out.clear()
        role = self.query_one("#prompt-role", Input).value
        task = self.query_one("#prompt-task", Input).value
        if event.button.id == "prompt-preview" and role:
            result = prompt_selector.select_prompt(role, task or "example")
            out.write(f"[bold]Prompt for {role}:[/bold]\n{result}")
        elif event.button.id == "prompt-set" and role:
            prompt_selector.set_custom_prompt(role, "Custom prompt for " + role)
            out.write(f"[green]Custom prompt set for '{role}'[/green]")
        elif event.button.id == "prompt-reset" and role:
            prompt_selector.reset_role(role)
            out.write(f"[yellow]Reset '{role}' to default[/yellow]")

class ScheduleTab(Static):
    def on_mount(self): self.refresh()
    def compose(self):
        yield Static("[bold cyan]Scheduler[/bold cyan]", id="sched-title")
        yield Input(placeholder="Task description (Enter to add)", id="sched-input")
        yield RichLog(id="sched-output", highlight=True, markup=True)

    async def on_input_submitted(self, event: Input.Submitted):
        if event.value:
            scheduler.enqueue(event.value, "general", 100, 0.5)
            self.refresh()

    def refresh(self):
        out = self.query_one("#sched-output", RichLog); out.clear()
        s = scheduler.stats()
        out.write(f"[bold]Queued:[/bold] {s['queue_size']}  [bold]Completed:[/bold] {s['completed']}  [bold]Running:[/bold] {s['running']}")
        next_tasks = scheduler.next_up(10)
        if next_tasks:
            t = RichTable(box=None)
            t.add_column("Urgency", style="yellow"); t.add_column("Task"); t.add_column("Agent")
            for nt in next_tasks:
                t.add_row(f"{nt['urgency']:.1f}", nt['desc'][:60], nt['agent'])
            out.write(t)

class MemoryTab(Static):
    def compose(self):
        yield Static("[bold cyan]Memory & Thoughts[/bold cyan]", id="mem-title")
        yield Input(placeholder="Search query", id="mem-input")
        yield Button("Inject Thought", id="mem-inject")
        yield RichLog(id="mem-output", highlight=True, markup=True)

    async def on_input_submitted(self, event: Input.Submitted):
        await self.do_search(event.value)

    async def on_button_pressed(self, event: Button.Pressed):
        inp = self.query_one("#mem-input", Input)
        if event.button.id == "mem-inject" and inp.value:
            thought_vdb.inject("tui", inp.value, [])
            self.query_one("#mem-output", RichLog).write(f"[green]+[/green] Thought injected: {inp.value[:60]}")

    async def do_search(self, query):
        out = self.query_one("#mem-output", RichLog); out.clear()
        q = query or "general"
        l1r = l1_memory.recall(q)
        tvdb = thought_vdb.query(q)
        if l1r:
            out.write("[bold cyan]L1 Memory[/bold cyan]")
            for r in l1r[:5]:
                out.write(f"  [dim]{r['score']:.2f}[/dim]  {r['value'][:80]}")
        if tvdb:
            out.write("\n[bold magenta]Thought VDB[/bold magenta]")
            for r in tvdb[:5]:
                tags = ", ".join(r.get('tags',[])[:2]) if r.get('tags') else ""
                out.write(f"  {r['confidence']:.0%}  {r['thought'][:80]}  [dim]{tags}[/dim]")

class LibraryTab(Static):
    def compose(self):
        yield Static("[bold cyan]Corporate Library[/bold cyan]", id="lib-title")
        yield Input(placeholder="Search query", id="lib-input")
        yield Horizontal(
            Button("Search", id="lib-search"),
            Button("Stats", id="lib-stats"),
        )
        yield RichLog(id="lib-output", highlight=True, markup=True)

    def on_button_pressed(self, event: Button.Pressed):
        out = self.query_one("#lib-output", RichLog); out.clear()
        inp = self.query_one("#lib-input", Input).value
        if event.button.id == "lib-search" and inp:
            results = corp_library.search(inp)
            if results:
                t = RichTable(box=None, title=f"Search: '{inp}'")
                t.add_column("ID"); t.add_column("Name"); t.add_column("Domain")
                t.add_column("Quality"); t.add_column("Usage")
                for r in results:
                    t.add_row(r["id"], r["name"], r["domain"], f"{r['quality']:.2f}", str(r["usage"]))
                out.write(t)
            else:
                out.write("[yellow]No results[/yellow]")
        elif event.button.id == "lib-stats":
            s = corp_library.stats()
            out.write(f"[bold]Stats:[/bold] {s['total_libraries']} libs, {s['total_agents']} agents, {s['total_usage']} uses, avg quality {s['avg_quality']:.2f}")

class MAIKTUI(App):
    TITLE = "MAIK TUI"
    CSS = """
    Screen { background: #0a0a1a; }
    Header { background: #0a0a1a; color: #00ffcc; }
    Footer { background: #0a0a1a; }
    TabbedContent { height: 100%; }
    RichLog { border: solid #1a1a3e; padding: 1; height: 1fr; }
    Input { margin: 0 1; }
    Static#ask-title, Static#status-title, Static#council-title, Static#org-title, Static#wf-title, Static#api-title, Static#agents-title, Static#prompt-title, Static#sched-title, Static#mem-title, Static#lib-title {
        padding: 0 1; text-style: bold; background: #0d0d2b; }
    Button { margin: 1; }
    Horizontal { height: auto; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("1", "switch_tab('ask')", "Ask"),
        Binding("2", "switch_tab('status')", "Status"),
        Binding("3", "switch_tab('council')", "Council"),
        Binding("4", "switch_tab('org')", "Org"),
        Binding("5", "switch_tab('workflow')", "Workflow"),
        Binding("6", "switch_tab('api')", "APIs"),
        Binding("7", "switch_tab('agents')", "Agents"),
        Binding("8", "switch_tab('schedule')", "Schedule"),
        Binding("9", "switch_tab('memory')", "Memory"),
    ]

    def compose(self):
        yield Header()
        with TabbedContent(initial="ask"):
            with TabPane("Ask", id="ask"): yield AskTab()
            with TabPane("Status", id="status"): yield StatusTab()
            with TabPane("Council", id="council"): yield CouncilTab()
            with TabPane("Org", id="org"): yield OrgTab()
            with TabPane("Workflow", id="workflow"): yield WorkflowTab()
            with TabPane("APIs", id="api"): yield ApiTab()
            with TabPane("Agents", id="agents"): yield AgentsTab()
            with TabPane("Prompts", id="prompts"): yield PromptTab()
            with TabPane("Schedule", id="schedule"): yield ScheduleTab()
            with TabPane("Memory", id="memory"): yield MemoryTab()
            with TabPane("Library", id="library"): yield LibraryTab()
        yield Footer()

    def action_switch_tab(self, tab: str):
        tc = self.query_one(TabbedContent)
        tc.active = tab

    def on_mount(self):
        self.sub_title = f"Multi-Agent Intelligence Kernel  •  {council.num_ceos} CEOs  •  {len(api_configs)} APIs  •  {org_chart.total_count()['ceos']} org CEOs"

if __name__ == "__main__":
    app = MAIKTUI()
    app.run()
