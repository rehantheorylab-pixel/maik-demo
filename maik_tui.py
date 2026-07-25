#!/usr/bin/env python3
"""MAIK TUI — Textual full-screen interactive terminal UI."""
import sys, os, asyncio, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Input, RichLog, TabbedContent, TabPane, Label, Button, ListView, ListItem
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

from config import TokenBudget, council
from router_engine import route, cache_stats
from tree_engine import execute
from learn_engine import learn, get_stats
from scheduler_engine import scheduler
from memory_engine import thought_vdb
from evolution_engine import pbt

class AskTab(Static):
    def compose(self):
        yield Static("[bold cyan]Ask MAIK[/bold cyan]", id="ask-title")
        yield Input(placeholder="Ask anything...", id="ask-input")
        yield RichLog(id="ask-output", highlight=True, markup=True)

    async def on_input_submitted(self, event: Input.Submitted):
        output = self.query_one("#ask-output", RichLog)
        output.clear()
        output.write("[cyan]Routing...[/cyan]")
        budget = TokenBudget(total=100000)
        r = route(event.value, "", budget)
        output.write(f"[bold]{r['ceo_name']}[/bold]  →  [cyan]{r['expert']}[/cyan]  (conf={r['confidence']:.0%})")
        output.write("[cyan]Executing...[/cyan]")
        result = execute(event.value, "", budget)
        output.clear()
        md = Markdown(result['solution'][:5000] or "(no output)")
        output.write(md)
        output.write(f"\n[dim]conf={result['confidence']:.0%}  agents={len(result['agents_used'])}[/dim]")
        learn(event.value, result['solution'][:500], "success", result['agents_used'], result['confidence'], 0, 0)

class StatusTab(Static):
    def on_mount(self):
        self.refresh_status()
        self.set_interval(3, self.refresh_status)

    def compose(self):
        yield Static("[bold cyan]System Status[/bold cyan]", id="status-title")
        yield RichLog(id="status-output", highlight=True, markup=True)

    def refresh_status(self):
        out = self.query_one("#status-output", RichLog)
        out.clear()
        stats = get_stats()
        cs = cache_stats()
        s = scheduler.stats()
        ps = pbt.stats()
        t = RichTable(box=None)
        t.add_column("Metric", style="cyan")
        t.add_column("Value")
        t.add_row("Runs", str(stats['total_runs']))
        t.add_row("Success Rate", f"{stats['success_rate']:.0%}")
        t.add_row("Cache", f"{cs['size']} entries ({cs['hit_rate']:.0%} hit)")
        t.add_row("Schedule", f"{s['queue_size']} queued")
        t.add_row("PBT Gen", str(ps['generation']))
        t.add_row("Council", f"{council.num_ceos} CEOs")
        t.add_row("Avg Confidence", f"{stats['avg_confidence']:.0%}")
        out.write(t)
        ceo_counts = {}
        try:
            from tree_engine import ceo_execution_breakdown
            ceo_counts = ceo_execution_breakdown()
        except:
            pass
        if ceo_counts:
            tt = RichTable(box=None, title="CEO Calls")
            tt.add_column("CEO", style="cyan")
            tt.add_column("Calls")
            for ceo_id, count in sorted(ceo_counts.items(), key=lambda x: -x[1])[:8]:
                tt.add_row(ceo_id, str(count))
            out.write(tt)

class CouncilTab(Static):
    def on_mount(self):
        self.refresh()

    def compose(self):
        yield Static("[bold cyan]Executive Council[/bold cyan]", id="council-title")
        yield RichLog(id="council-output", highlight=True, markup=True)

    def refresh(self):
        out = self.query_one("#council-output", RichLog)
        out.clear()
        t = RichTable(box=None)
        t.add_column("CEO", style="cyan", no_wrap=True)
        t.add_column("Name")
        t.add_column("Managers")
        t.add_column("APIs")
        t.add_column("Budget")
        for c in council.list_ceos():
            t.add_row(c['id'], c['name'], str(c['managers']), str(c['api_count']), c['budget'])
        out.write(t)

class ScheduleTab(Static):
    def compose(self):
        yield Static("[bold cyan]Scheduler[/bold cyan]", id="sched-title")
        yield Input(placeholder="Task description (Enter to add)", id="sched-input")
        yield RichLog(id="sched-output", highlight=True, markup=True)

    def on_mount(self):
        self.refresh_sched()

    async def on_input_submitted(self, event: Input.Submitted):
        if event.value:
            scheduler.enqueue(event.value, "general", 100, 0.5)
            self.refresh_sched()

    def refresh_sched(self):
        out = self.query_one("#sched-output", RichLog)
        out.clear()
        s = scheduler.stats()
        out.write(f"[bold]Queued:[/bold] {s['queue_size']}  [bold]Completed:[/bold] {s['completed']}  [bold]Running:[/bold] {s['running']}")
        next_tasks = scheduler.next_up(10)
        if next_tasks:
            t = RichTable(box=None)
            t.add_column("Urgency", style="yellow")
            t.add_column("Task")
            for nt in next_tasks:
                t.add_row(f"{nt['urgency']:.1f}", nt['desc'][:60])
            out.write(t)

class MemoryTab(Static):
    def compose(self):
        yield Static("[bold cyan]Memory & Thoughts[/bold cyan]", id="mem-title")
        yield Input(placeholder="Search query", id="mem-input")
        yield RichLog(id="mem-output", highlight=True, markup=True)

    async def on_input_submitted(self, event: Input.Submitted):
        query = event.value or "general"
        out = self.query_one("#mem-output", RichLog)
        out.clear()
        from memory_engine import l1_memory
        l1r = l1_memory.recall(query)
        tvdb = thought_vdb.query(query)
        if l1r:
            out.write("[bold cyan]L1 Memory[/bold cyan]")
            for r in l1r[:5]:
                out.write(f"  [dim]{r['score']:.2f}[/dim]  {r['value'][:80]}")
        if tvdb:
            out.write("\n[bold magenta]Thought VDB[/bold magenta]")
            for r in tvdb[:5]:
                tags = ", ".join(r.get('tags', [])[:2]) if r.get('tags') else ""
                out.write(f"  {r['confidence']:.0%}  {r['thought'][:80]}  [dim]{tags}[/dim]")

class MAIKTUI(App):
    TITLE = "MAIK TUI"
    SUB_TITLE = f"Multi-Agent Intelligence Kernel  •  {council.num_ceos} CEOs"
    CSS = """
    Screen { background: #0a0a1a; }
    Header { background: #0a0a1a; color: #00ffcc; }
    Footer { background: #0a0a1a; }
    TabbedContent { height: 100%; }
    RichLog { border: solid #1a1a3e; padding: 1; height: 1fr; }
    Input { margin: 0 1; }
    Static#ask-title, Static#status-title, Static#council-title, Static#sched-title, Static#mem-title {
        padding: 0 1; text-style: bold; background: #0d0d2b; }
    Button { margin: 1; }
    """
    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
        Binding("1", "switch_tab('ask')", "Ask"),
        Binding("2", "switch_tab('status')", "Status"),
        Binding("3", "switch_tab('council')", "Council"),
        Binding("4", "switch_tab('schedule')", "Schedule"),
        Binding("5", "switch_tab('memory')", "Memory"),
    ]

    def compose(self):
        yield Header()
        with TabbedContent(initial="ask"):
            with TabPane("Ask", id="ask"):
                yield AskTab()
            with TabPane("Status", id="status"):
                yield StatusTab()
            with TabPane("Council", id="council"):
                yield CouncilTab()
            with TabPane("Schedule", id="schedule"):
                yield ScheduleTab()
            with TabPane("Memory", id="memory"):
                yield MemoryTab()
        yield Footer()

    def action_switch_tab(self, tab: str):
        tc = self.query_one(TabbedContent)
        tc.active = tab

if __name__ == "__main__":
    app = MAIKTUI()
    app.run()
