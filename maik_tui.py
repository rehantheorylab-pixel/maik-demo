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
from governance_engine import voting_engine, logic_probe, sentinel, sheriff, session_manager, cognitive_controls, pbt_tracker, training
from pixel_vision import pixel_vision
from api_router import router as api_router
from cli_plugin import cli_plugins
from github_integration import github
from auth_manager import auth
from agent_tree import agent_tree, AgentStatus
from mindmap_ui import render_mind_map_json, render_tree_text
from unified_vision import unified_vision

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
    def on_mount(self):
        self.refresh()

    def compose(self):
        yield Static("[bold cyan]Org Chart Manager[/bold cyan]", id="org-title")
        with Horizontal():
            yield Button("Refresh", id="org-ref", variant="primary")
            yield Button("Add CEO", id="org-add-ceo")
            yield Button("+ Sub-Agent", id="org-add-child")
            yield Button("- Remove", id="org-remove")
            yield Button("Details", id="org-detail")
        yield Static(id="org-cnt")
        with Horizontal():
            yield RichLog(id="org-out", highlight=True, markup=True)
            yield RichLog(id="org-det", highlight=True, markup=True)

    def on_button_pressed(self, e):
        b = e.button.id
        if b == "org-ref": self.refresh()
        elif b == "org-add-ceo": self.ceo_dlg()
        elif b == "org-add-child": self.child_dlg()
        elif b == "org-remove": self.rm_dlg()
        elif b == "org-detail": self.det_dlg()

    def ceo_dlg(self):
        from textual.screen import ModalScreen
        class S(ModalScreen):
            def compose(self):
                yield Vertical(
                    Static("[bold]Add CEO[/bold]"),
                    Input(placeholder="CEO ID", id="cid"),
                    Input(placeholder="CEO Name", id="cnm"),
                    Horizontal(Button("Add",id="add"), Button("Cancel",id="cancel")),
                )
            def on_button_pressed(self, e):
                if e.button.id == "add":
                    a=self.query_one("#cid",Input).value; b=self.query_one("#cnm",Input).value
                    if a and b: org_chart.add_ceo(a,b); council.add_ceo(b,["general"])
                self.app.pop_screen()
        self.app.push_screen(S()); self.ref_later()

    def child_dlg(self):
        from textual.screen import ModalScreen
        class S(ModalScreen):
            def compose(self):
                yield Vertical(
                    Static("[bold]Add Sub-Agent[/bold]"),
                    Input(placeholder="Parent ID", id="pid"),
                    Input(placeholder="Sub-Agent ID", id="cid"),
                    Input(placeholder="Sub-Agent Name", id="cnm"),
                    Input(placeholder="Type (default: agent)", id="cty"),
                    Horizontal(Button("Add",id="add"), Button("Cancel",id="cancel")),
                )
            def on_button_pressed(self, e):
                if e.button.id == "add":
                    p=self.query_one("#pid",Input).value; a=self.query_one("#cid",Input).value
                    b=self.query_one("#cnm",Input).value; t=self.query_one("#cty",Input).value or "agent"
                    if p and a and b: org_chart.add_child(p,a,b,t)
                self.app.pop_screen()
        self.app.push_screen(S()); self.ref_later()

    def rm_dlg(self):
        from textual.screen import ModalScreen
        class S(ModalScreen):
            def compose(self):
                yield Vertical(
                    Static("[bold]Remove Node[/bold]"),
                    Input(placeholder="Node ID to remove", id="rid"),
                    Horizontal(Button("Remove",id="rm"), Button("Cancel",id="cancel")),
                )
            def on_button_pressed(self, e):
                if e.button.id == "rm":
                    n=self.query_one("#rid",Input).value
                    if n: org_chart.remove_node(n)
                self.app.pop_screen()
        self.app.push_screen(S()); self.ref_later()

    def det_dlg(self):
        from textual.screen import ModalScreen
        class S(ModalScreen):
            def compose(self):
                yield Vertical(
                    Static("[bold]Agent Details[/bold]"),
                    Input(placeholder="Agent ID", id="did"),
                    RichLog(id="dlog", highlight=True, markup=True),
                    Button("Close", id="cancel"),
                )
            def on_button_pressed(self, e):
                if e.button.id == "show":
                    a=self.query_one("#did",Input).value; l=self.query_one("#dlog",RichLog)
                    if a:
                        d=agent_tracker.stats(a)
                        l.write(json.dumps(d,indent=2) if d else f"[yellow]No data for {a!r}[/yellow]")
                else: self.app.pop_screen()
        self.app.push_screen(S())

    def ref_later(self):
        asyncio.get_event_loop().call_later(0.5, self.refresh)

    def refresh(self):
        o = self.query_one("#org-out", RichLog); o.clear()
        mind = org_chart.get_mind_map()
        if not mind: o.write("[yellow]No CEOs yet.[/yellow]"); return
        t = RichTree("[bold cyan]Corporate Hierarchy[/bold cyan]")
        self._build(t, mind); o.write(t)
        c = org_chart.total_count()
        self.query_one("#org-cnt",Static).update(f"[bold]Total: {c['total']} | CEOs: {c['ceos']} | Sub: {c['sub_agents']}[/bold]")

    def _build(self, pb, cd):
        for nid, nd in sorted(cd.items()):
            nm = nd["name"]; ad = nd.get("agent_data",{}); st = ad.get("status","?")
            el = ad.get("elo",1000); sc = "green" if st=="idle" else "yellow"
            lbl = f"[bold]{nm}[/bold] [dim]({nid})[/dim] [{sc}]{st}[/{sc}] ELO:{el}"
            br = pb.add(lbl)
            if nd.get("children"): self._build(br, nd["children"])



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

class VoteTab(Static):
    def compose(self):
        yield Static("[bold cyan]Voting & Consensus[/bold cyan]", id="vote-title")
        yield RichLog(id="vote-log", highlight=True, markup=True)

    def on_mount(self):
        log = self.query_one("#vote-log", RichLog)
        votes = voting_engine.list_votes()
        log.write("[bold underline]Open Votes[/bold underline]")
        for v in votes:
            log.write(f"  [{v['id']}] {v['topic']} — {v['status']} ({len(v['votes'])} votes)")

class ProbeTab(Static):
    def compose(self):
        yield Static("[bold cyan]Logic Probe[/bold cyan]", id="probe-title")
        yield RichLog(id="probe-log", highlight=True, markup=True)

    def on_mount(self):
        log = self.query_one("#probe-log", RichLog)
        flagged = logic_probe.list_flagged()
        log.write("[bold underline]Flagged Contradictions[/bold underline]")
        for f in flagged:
            log.write(f"  {f['thought_ids']}: {f['reason']}")

class SentinelTab(Static):
    def compose(self):
        yield Static("[bold cyan]Sentinel Monitor[/bold cyan]", id="sentinel-title")
        yield RichLog(id="sentinel-log", highlight=True, markup=True)

    def on_mount(self):
        log = self.query_one("#sentinel-log", RichLog)
        s = sentinel.get_status()
        log.write("[bold underline]Sentinel Status[/bold underline]")
        log.write(f"  Health: {s.get('health','?')}")
        log.write(f"  Uptime: {s.get('uptime','?')}")
        alerts = sentinel.get_alerts()
        log.write("[bold underline]Recent Alerts[/bold underline]")
        for a in alerts[-10:]:
            log.write(f"  {a['time']} [{a['level']}] {a['message']}")

class SheriffTab(Static):
    def compose(self):
        yield Static("[bold cyan]Sheriff Rules[/bold cyan]", id="sheriff-title")
        yield RichLog(id="sheriff-log", highlight=True, markup=True)

    def on_mount(self):
        log = self.query_one("#sheriff-log", RichLog)
        rules = sheriff.list_rules()
        log.write("[bold underline]Active Rules[/bold underline]")
        for r in rules:
            status = "[green]ON[/green]" if r['enabled'] else "[red]OFF[/red]"
            log.write(f"  [{r['id']}] {r['name']} — {status} (severity={r['severity']})")

class SessionTab(Static):
    def compose(self):
        yield Static("[bold cyan]Session Manager[/bold cyan]", id="session-title")
        yield RichLog(id="session-log", highlight=True, markup=True)

    def on_mount(self):
        log = self.query_one("#session-log", RichLog)
        active = session_manager.get_active()
        log.write("[bold underline]Active Session[/bold underline]")
        if active:
            log.write(f"  ID: {active['id']}")
            log.write(f"  Started: {active['start']}")
        else:
            log.write("  No active session.")
        sessions = session_manager.list_sessions()
        log.write("[bold underline]Recent Sessions[/bold underline]")
        for s in sessions[-5:]:
            log.write(f"  [{s['id']}] {s['start']} — {s.get('status','?')}")

class CogTab(Static):
    def compose(self):
        yield Static("[bold cyan]Cognitive Controls[/bold cyan]", id="cog-title")
        yield RichLog(id="cog-log", highlight=True, markup=True)

    def on_mount(self):
        log = self.query_one("#cog-log", RichLog)
        s = cognitive_controls.get_settings()
        log.write("[bold underline]Cognitive Settings[/bold underline]")
        for k, v in s.items():
            log.write(f"  {k}: {v}")

class TrainTab(Static):
    def compose(self):
        yield Static("[bold cyan]Training[/bold cyan]", id="train-title")
        yield RichLog(id="train-log", highlight=True, markup=True)

    def on_mount(self):
        log = self.query_one("#train-log", RichLog)
        tasks = training.get_tasks()
        log.write("[bold underline]Training Tasks[/bold underline]")
        for t in tasks:
            log.write(f"  [{t['id']}] {t['name']} — {t.get('status','?')}")

class PBTab(Static):
    def compose(self):
        yield Static("[bold cyan]PBT Evolution Tracker[/bold cyan]", id="pbt-title")
        yield RichLog(id="pbt-log", highlight=True, markup=True)

    def on_mount(self):
        log = self.query_one("#pbt-log", RichLog)
        s = pbt_tracker.get_status()
        log.write("[bold underline]PBT Status[/bold underline]")
        for k, v in s.items():
            log.write(f"  {k}: {v}")
        history = pbt_tracker.get_history()
        log.write("[bold underline]Fitness History[/bold underline]")
        for entry in history[-10:]:
            log.write(f"  gen={entry['gen']} best={entry['best_fitness']:.4f} avg={entry['avg_fitness']:.4f}")

class AgentTreeTab(Static):
    def on_mount(self): self.refresh()
    def compose(self):
        yield Static("[bold cyan]🧠 Agent Workflow Mind Map[/bold cyan]", id="agenttree-title")
        yield RichLog(id="agenttree-out", highlight=True, markup=True)
        yield Button("Refresh", id="at-refresh", variant="primary")
        yield Button("Delegations", id="at-deleg")

    def on_button_pressed(self, e):
        out = self.query_one("#agenttree-out", RichLog)
        if e.button.id == "at-refresh": self.refresh()
        elif e.button.id == "at-deleg":
            out.clear(); out.write("[bold underline]Delegations[/bold underline]")
            for d in agent_tree.delegation_history(20):
                out.write(f"{d['delegated_to']:<20} {d['task'][:50]} -> {' > '.join(d.get('path',[]))}")

    def refresh(self):
        out = self.query_one("#agenttree-out", RichLog); out.clear()
        out.write(render_tree_text())

class GitHubTab(Static):
    def compose(self):
        yield Static("[bold cyan]🌐 GitHub Integration[/bold cyan]", id="gh-title")
        yield RichLog(id="gh-out", highlight=True, markup=True)
        yield Horizontal(
            Button("User", id="gh-user"), Button("Repos", id="gh-repos"),
            Button("Issues", id="gh-issues"), Button("Search", id="gh-search"),
        )

    def on_button_pressed(self, e):
        out = self.query_one("#gh-out", RichLog); out.clear()
        if e.button.id == "gh-user":
            u = github.get_user()
            out.write(json.dumps(u, indent=2) if isinstance(u, dict) else str(u))
        elif e.button.id == "gh-repos":
            for r in github.list_repos()[:15]:
                out.write(f"{r['full_name']} ★{r['stars']} [{r.get('language','')}]")
        elif e.button.id == "gh-issues":
            for i in github.list_issues("octocat", "Hello-World"):
                out.write(f"#{i['number']} {i['title']}")
        elif e.button.id == "gh-search":
            q = self.query_one("#gh-search").value if hasattr(e.button, 'value') else ""
            for r in github.search_repos("machine learning"):
                out.write(f"{r['name']} ★{r['stars']}")

class ApiRouterTab(Static):
    def compose(self):
        yield Static("[bold cyan]🤖 API Router[/bold cyan]", id="ar-title")
        yield RichLog(id="ar-out", highlight=True, markup=True)
        yield Horizontal(
            Button("List Providers", id="ar-list"), Button("Stats", id="ar-stats"),
        )

    def on_button_pressed(self, e):
        out = self.query_one("#ar-out", RichLog); out.clear()
        if e.button.id == "ar-list":
            for p in api_router.list_providers():
                c = ', '.join(p['capabilities'][:3])
                out.write(f"{p['name']:<20} {p['model']:<30} {c} key={'✓' if p['has_key'] else '✗'}")
        elif e.button.id == "ar-stats":
            out.write(json.dumps(api_router.stats(), indent=2))

class CLIPluginTab(Static):
    def compose(self):
        yield Static("[bold cyan]🔧 CLI Plugins[/bold cyan]", id="cli-title")
        yield RichLog(id="cli-out", highlight=True, markup=True)
        yield Horizontal(
            Button("List", id="cli-list"), Button("Stats", id="cli-stats"),
        )

    def on_button_pressed(self, e):
        out = self.query_one("#cli-out", RichLog); out.clear()
        if e.button.id == "cli-list":
            for p in cli_plugins.list_plugins():
                status = '✅' if p['installed'] else '❌'
                out.write(f"{status} {p['name']:<15} {p['command']:<20} {p.get('version','')}")
        elif e.button.id == "cli-stats":
            out.write(json.dumps(cli_plugins.stats(), indent=2))

class AuthTab(Static):
    def compose(self):
        yield Static("[bold cyan]🔑 Auth Manager[/bold cyan]", id="auth-title")
        yield RichLog(id="auth-out", highlight=True, markup=True)
        yield Button("Status", id="auth-status")

    def on_button_pressed(self, e):
        out = self.query_one("#auth-out", RichLog); out.clear()
        out.write(json.dumps(auth.status(), indent=2))

class PixelVisionTab(Static):
    def on_mount(self): pass
    def compose(self):
        yield Static("[bold cyan]👁 Pixel Vision[/bold cyan]", id="pv-title")
        yield RichLog(id="pv-out", highlight=True, markup=True)
        yield Horizontal(
            Button("Describe Screen", id="pv-desc", variant="primary"),
            Button("Elements", id="pv-elements"),
            Button("Colors", id="pv-colors"),
        )

    def on_button_pressed(self, e):
        out = self.query_one("#pv-out", RichLog); out.clear()
        from rich.markdown import Markdown
        import threading as _t
        if e.button.id == "pv-desc":
            out.write("[yellow]Capturing screen...[/yellow]")
            def _run():
                try:
                    d = pixel_vision.describe_screen()
                    self.app.call_from_thread(lambda: out.write(json.dumps({k:v for k,v in d.items() if k != 'screenshot_b64'}, indent=2)))
                except Exception as ex:
                    self.app.call_from_thread(lambda: out.write(f"[red]Error: {ex}[/red]"))
            _t.Thread(target=_run, daemon=True).start()
        elif e.button.id == "pv-elements":
            def _run():
                try:
                    els = pixel_vision.detect_elements()
                    self.app.call_from_thread(lambda: [out.write(f"{e.type:<10} at ({e.x},{e.y}) text='{e.text[:30]}' conf={e.confidence:.2f} {'✓' if e.is_interactive else ' '}") for e in els[:30]])
                except Exception as ex:
                    self.app.call_from_thread(lambda: out.write(f"[red]Error: {ex}[/red]"))
            _t.Thread(target=_run, daemon=True).start()
        elif e.button.id == "pv-colors":
            def _run():
                try:
                    pal = pixel_vision.detect_color_palette()
                    self.app.call_from_thread(lambda: [out.write(f"  {c['hex']}  {c['rgb']}") for c in pal])
                except Exception as ex:
                    self.app.call_from_thread(lambda: out.write(f"[red]Error: {ex}[/red]"))
            _t.Thread(target=_run, daemon=True).start()

class MAIKTUI(App):
    TITLE = "MAIK TUI"
    CSS = """
    Screen { background: #0a0a1a; }
    Header { background: #0a0a1a; color: #00ffcc; }
    Footer { background: #0a0a1a; }
    TabbedContent { height: 100%; }
    RichLog { border: solid #1a1a3e; padding: 1; height: 1fr; }
    Input { margin: 0 1; }
    Static#ask-title, Static#status-title, Static#council-title, Static#org-title, Static#wf-title, Static#api-title, Static#agents-title, Static#prompt-title, Static#sched-title, Static#mem-title, Static#lib-title, Static#vote-title, Static#probe-title, Static#sentinel-title, Static#sheriff-title, Static#session-title, Static#cog-title, Static#train-title, Static#pbt-title {
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
            with TabPane("Vote", id="vote"): yield VoteTab()
            with TabPane("Probe", id="probe"): yield ProbeTab()
            with TabPane("Sentinel", id="sentinel"): yield SentinelTab()
            with TabPane("Sheriff", id="sheriff"): yield SheriffTab()
            with TabPane("Session", id="session"): yield SessionTab()
            with TabPane("Cog", id="cog"): yield CogTab()
            with TabPane("Train", id="train"): yield TrainTab()
            with TabPane("PBT", id="pbt"): yield PBTab()
            with TabPane("🔮 MindMap", id="agenttree"): yield AgentTreeTab()
            with TabPane("🌐 GitHub", id="github"): yield GitHubTab()
            with TabPane("🤖 API Router", id="api-router"): yield ApiRouterTab()
            with TabPane("🔧 CLI", id="cli"): yield CLIPluginTab()
            with TabPane("🔑 Auth", id="auth"): yield AuthTab()
            with TabPane("👁 Vision", id="vision"): yield PixelVisionTab()
        yield Footer()

    def action_switch_tab(self, tab: str):
        tc = self.query_one(TabbedContent)
        tc.active = tab

    def on_mount(self):
        self.sub_title = f"Multi-Agent Intelligence Kernel  •  {council.num_ceos} CEOs  •  {len(api_configs)} APIs  •  {org_chart.total_count()['ceos']} org CEOs"

if __name__ == "__main__":
    app = MAIKTUI()
    app.run()
