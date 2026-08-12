#!/usr/bin/env python3
"""MAIK Desktop GUI — full-featured management interface with hierarchy builder."""
import sys, os, json, threading, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext, messagebox, simpledialog
except ImportError:
    print("tkinter not available. Install python3-tk or use 'maik interactive' instead.")
    sys.exit(1)

from config import TokenBudget, council, api_configs, WORKFLOW_CHAINS, APIConfig
from router_engine import route, cache_stats
from tree_engine import execute, ceo_execution_breakdown
from learn_engine import learn, get_stats
from scheduler_engine import scheduler
from memory_engine import thought_vdb, l1_memory
from evolution_engine import pbt
from safety_engine import stop_light
from meta_controller import prompt_selector, workflow_engine, PROMPT_TEMPLATES
from corporate_engine import org_chart, agent_tracker, corp_library
from governance_engine import voting_engine, logic_probe, sentinel, sheriff, session_manager, cognitive_controls, pbt_tracker, training
from session_compactor import session_archiver, summary_generator, compaction_manager
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
from mindmap_ui import render_mind_map_json, render_tree_text, MindMapWidget
from unified_vision import unified_vision

class NotebookTab:
    def __init__(self, parent, app):
        self.parent = parent
        self.app = app

class AskTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        frame = ttk.LabelFrame(parent, text="Ask MAIK", padding=5)
        frame.pack(fill=tk.X, padx=5, pady=2)
        self.input_text = tk.Text(frame, height=3, font=("Consolas", 11), wrap=tk.WORD)
        self.input_text.pack(fill=tk.X, pady=2)
        self.input_text.bind("<Control-Return>", lambda e: self.do_ask())
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X, pady=3)
        ttk.Button(btn_frame, text="Ask", command=self.do_ask, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Route Only", command=self.do_route, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Execute Only", command=self.do_execute, width=10).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Clear", command=self.clear, width=8).pack(side=tk.RIGHT, padx=2)
        ttk.Label(btn_frame, text="Domain:").pack(side=tk.RIGHT, padx=2)
        self.domain_var = tk.StringVar(value="")
        ttk.Combobox(btn_frame, textvariable=self.domain_var, values=["","code","math","planning","creative","research","security","general"], width=10).pack(side=tk.RIGHT, padx=2)
        out_frame = ttk.LabelFrame(parent, text="Response", padding=5)
        out_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.output = scrolledtext.ScrolledText(out_frame, font=("Consolas", 10), wrap=tk.WORD, bg="#1e1e1e", fg="#d4d4d4", insertbackground="white")
        self.output.pack(fill=tk.BOTH, expand=True)

    def log(self, text, tag=""):
        self.output.insert(tk.END, text + "\n")
        self.output.see(tk.END)

    def clear(self):
        self.output.delete(1.0, tk.END)

    def do_ask(self):
        problem = self.input_text.get(1.0, tk.END).strip()
        if not problem: return
        self.clear()
        self.app.set_status("Routing...")
        domain = self.domain_var.get()
        threading.Thread(target=self._run_ask, args=(problem, domain), daemon=True).start()

    def _run_ask(self, problem, domain):
        try:
            budget = TokenBudget(total=100000)
            r = route(problem, domain, budget)
            self.app.win.after(0, self.log, f"--- {r['ceo_name']} -> {r['expert']} (conf={r['confidence']:.0%})")
            self.app.set_ceo(f"CEO: {r['ceo_name']}")
            self.app.set_status("Executing...")
            result = execute(problem, domain, budget)
            self.app.win.after(0, self.log, result['solution'][:5000] or "(no output)")
            learn(problem, result['solution'][:500], "success", result['agents_used'], result['confidence'], 0, 0)
            summary = f"conf={result['confidence']:.0%} depth={result['depth']} agents={len(result['agents_used'])}"
            self.app.win.after(0, self.log, f"\n--- {summary} ---")
            self.app.set_status("Done")
        except Exception as e:
            self.app.win.after(0, self.log, f"Error: {e}")
            self.app.set_status("Error")

    def do_route(self):
        problem = self.input_text.get(1.0, tk.END).strip()
        if not problem: return
        self.clear(); self.app.set_status("Routing...")
        r = route(problem, self.domain_var.get(), TokenBudget(total=100000))
        self.log(f"CEO: {r['ceo_name']} ({r['ceo']})"); self.log(f"Expert: {r['expert']}")
        self.log(f"Conf: {r['confidence']:.0%}"); self.log(f"Model: {r['model']}")
        self.log(f"Cached: {r['cached']}"); self.app.set_ceo(f"CEO: {r['ceo_name']}"); self.app.set_status("Routed")

    def do_execute(self):
        problem = self.input_text.get(1.0, tk.END).strip()
        if not problem: return
        self.clear(); self.app.set_status("Executing...")
        threading.Thread(target=self._run_exec, args=(problem, self.domain_var.get()), daemon=True).start()

    def _run_exec(self, problem, domain):
        try:
            result = execute(problem, domain, TokenBudget(total=100000))
            self.app.win.after(0, self.log, result['solution'][:5000] or "(no output)")
            summary = f"conf={result['confidence']:.0%} depth={result['depth']} agents={len(result['agents_used'])}"
            self.app.win.after(0, self.log, f"\n--- {summary} ---"); self.app.set_status("Done")
        except Exception as e:
            self.app.win.after(0, self.log, f"Error: {e}"); self.app.set_status("Error")

class StatusTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        self.frame = ttk.LabelFrame(parent, text="System Status", padding=5)
        self.frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.text = scrolledtext.ScrolledText(self.frame, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4", height=15)
        self.text.pack(fill=tk.BOTH, expand=True)
        btn_frame = ttk.Frame(parent); btn_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=2)
        self.refresh()

    def refresh(self):
        self.text.delete(1.0, tk.END)
        stats = get_stats(); cs = cache_stats(); s = scheduler.stats(); ps = pbt.stats()
        at = agent_tracker.stats(); oc = org_chart.total_count()
        lines = [
            f"System Status ({time.strftime('%H:%M:%S')})", "="*50,
            f"Runs:           {stats['total_runs']}",
            f"Success Rate:   {stats['success_rate']:.0%}",
            f"Avg Confidence: {stats['avg_confidence']:.0%}",
            f"Avg Tokens:     {stats['avg_tokens']:.0f}",
            f"Cache:          {cs['size']} entries ({cs['hit_rate']:.0%} hit)",
            f"PBT Gen:        {ps['generation']}",
            f"Schedule:       {s['queue_size']} queued, {s['completed']} done",
            f"Council:        {council.num_ceos} CEOs ({council.profile})",
            f"API Configs:    {len(api_configs)}",
            f"Stop Light:     {stop_light.status().upper()}",
            f"",
            f"Corporate Hierarchy", "-"*30,
            f"CEOs:       {oc['ceos']}",
            f"Managers:   {oc['managers']}",
            f"Employees:  {oc['employees']}",
            f"",
            f"Agent Tracking", "-"*30,
            f"Total:      {at['total']}",
            f"Active:     {at['active']}",
            f"Avg ELO:    {at['avg_elo']}",
            f"Avg Success:{at['avg_success_rate']:.1%}",
            f"",
            f"ELO Leaderboard", "-"*30,
        ]
        for a in agent_tracker.leaderboard(5):
            lines.append(f"  {a['id']:<16} ELO:{a['elo']:<6} {a['success_rate']:.0%} {a['status']}")
        self.text.insert(tk.END, "\n".join(lines))

class CouncilTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        # Top: council table
        top_frame = ttk.LabelFrame(parent, text="Executive Council", padding=5)
        top_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.tree = ttk.Treeview(top_frame, columns=("id","name","managers","apis","budget"), show="headings", height=6)
        self.tree.heading("id", text="CEO ID"); self.tree.heading("name", text="Name")
        self.tree.heading("managers", text="Managers"); self.tree.heading("apis", text="APIs")
        self.tree.heading("budget", text="Budget")
        self.tree.column("id", width=120); self.tree.column("name", width=180)
        self.tree.column("managers", width=70); self.tree.column("apis", width=60); self.tree.column("budget", width=200)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        btn_frame = ttk.Frame(parent); btn_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(btn_frame, text="Add CEO", command=self.add_ceo_dialog).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Remove CEO", command=self.remove_ceo).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=2)
        # Bottom: mind map
        self.mind_text = scrolledtext.ScrolledText(parent, font=("Consolas", 9), bg="#0d0d2b", fg="#00ffcc", height=8)
        self.mind_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.refresh()

    def refresh(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for c in council.list_ceos():
            self.tree.insert("", tk.END, values=(c['id'], c['name'], c['managers'], c['api_count'], c['budget']))
        self.mind_text.delete(1.0, tk.END)
        mind = org_chart.get_mind_map()
        if mind:
            lines = ["┌─ ORG CHART MIND MAP ───────────────────┐"]
            for ceo_id, cd in mind.items():
                lines.append(f"│ 👤 {cd['name']} ({ceo_id})")
                for mgr_id, md in cd.get("managers",{}).items():
                    lines.append(f"│   ├─ 👤 {md['name']} ({mgr_id})")
                    for e in md.get("employees",[]):
                        lines.append(f"│   │   ├─ 👤 {e['name']} ({e['role']})")
                lines.append("│")
            self.mind_text.insert(tk.END, "\n".join(lines) + "\n")

    def add_ceo_dialog(self):
        d = tk.Toplevel(self.app.win); d.title("Add CEO"); d.geometry("400x200")
        ttk.Label(d, text="CEO ID:").pack(pady=2)
        id_var = tk.StringVar(value="ceo-"); ttk.Entry(d, textvariable=id_var).pack(pady=2, padx=10, fill=tk.X)
        ttk.Label(d, text="CEO Name:").pack(pady=2)
        name_var = tk.StringVar(); ttk.Entry(d, textvariable=name_var).pack(pady=2, padx=10, fill=tk.X)
        def confirm():
            cid = id_var.get().strip(); nm = name_var.get().strip()
            if cid and nm:
                oc = org_chart.add_ceo(cid, nm)
                council.add_ceo(nm, ["general","custom"])
                self.refresh(); self.app.set_status(f"Added CEO: {nm}")
            d.destroy()
        ttk.Button(d, text="Add", command=confirm).pack(pady=10)

    def remove_ceo(self):
        sel = self.tree.selection()
        if not sel: return
        vals = self.tree.item(sel[0], "values")
        if messagebox.askyesno("Confirm", f"Remove CEO {vals[0]}?"):
            org_chart.remove_ceo(vals[0]); council.remove_ceo(vals[0])
            self.refresh(); self.app.set_status(f"Removed CEO: {vals[0]}")

class OrgTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        cf = ttk.Frame(parent)
        cf.pack(fill=tk.X, padx=5, pady=2)
        self.cl = ttk.Label(cf, text="", font=("Segoe UI", 9, "bold"))
        self.cl.pack(side=tk.LEFT)
        bf = ttk.Frame(parent)
        bf.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(bf, text="+ Add CEO", command=self.add_ceo).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="+ Sub-Agent", command=self.add_sub_agent).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="- Remove", command=self.remove_node).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="Details", command=self.show_details).pack(side=tk.LEFT, padx=2)
        ttk.Button(bf, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=2)
        tf = ttk.LabelFrame(parent, text="Org Hierarchy", padding=5)
        tf.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.tv = ttk.Treeview(tf, columns=("type","sub","desc","status"), show="tree headings")
        self.tv.heading("#0", text="Name/ID")
        self.tv.heading("type", text="Type")
        self.tv.heading("sub", text="Sub-Agents")
        self.tv.heading("desc", text="Descendants")
        self.tv.heading("status", text="Status")
        self.tv.column("#0", width=300)
        self.tv.column("type", width=80)
        self.tv.column("sub", width=80)
        self.tv.column("desc", width=80)
        self.tv.column("status", width=80)
        self.tv.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.tv.bind("<<TreeviewSelect>>", self.on_sel)
        df = ttk.LabelFrame(parent, text="Agent Details", padding=5)
        df.pack(fill=tk.BOTH, padx=5, pady=2)
        self.dt = scrolledtext.ScrolledText(df, font=("Consolas",9), bg="#1e1e1e", fg="#d4d4d4", height=6)
        self.dt.pack(fill=tk.BOTH, expand=True)
        self.refresh()

    def _pop(self, pi, cd):
        for nid, nd in sorted(cd.items()):
            nm = nd["name"]; nt = nd.get("type","agent")
            sb = nd.get("sub_agents",0); dc = nd.get("descendants",0)
            ad = nd.get("agent_data",{}); st = ad.get("status","?")
            lbl = f"{nm} ({nid})"
            ii = self.tv.insert(pi, tk.END, iid=nid, text=lbl, values=(nt,sb,dc,st))
            if nd.get("children"):
                self._pop(ii, nd["children"])

    def refresh(self):
        for i in self.tv.get_children(): self.tv.delete(i)
        mind = org_chart.get_mind_map()
        for cid, cd in sorted(mind.items()):
            nm = cd["name"]; nt = cd.get("type","ceo")
            sb = cd.get("sub_agents",0); dc = cd.get("descendants",0)
            ad = cd.get("agent_data",{}); st = ad.get("status","?")
            lbl = f"{nm} ({cid})"
            ii = self.tv.insert("", tk.END, iid=cid, text=lbl, values=(nt,sb,dc,st))
            if cd.get("children"):
                self._pop(ii, cd["children"])
        c = org_chart.total_count()
        self.cl.config(text=f"Total: {c['total']} | CEOs: {c['ceos']} | Sub: {c['sub_agents']}")

    def on_sel(self, e):
        sel = self.tv.selection()
        if not sel: return
        nid = sel[0]
        self.dt.delete(1.0, tk.END)
        d = agent_tracker.stats(nid)
        self.dt.insert(tk.END, json.dumps(d, indent=2) if d else f"No data for {nid!r}.")

    def add_ceo(self):
        cid = simpledialog.askstring("Add CEO","CEO ID:")
        if not cid: return
        nm = simpledialog.askstring("Add CEO","CEO Name:")
        if not nm: return
        org_chart.add_ceo(cid,nm); self.app.refresh_profile(); self.refresh()

    def add_sub_agent(self):
        sel = self.tv.selection()
        if not sel: messagebox.showinfo("Info","Select a parent first."); return
        pid = sel[0]
        cid = simpledialog.askstring("Add Sub-Agent",f"ID (under {pid}):")
        if not cid: return
        nm = simpledialog.askstring("Add Sub-Agent","Name:")
        if not nm: return
        role = simpledialog.askstring("Add Sub-Agent","Type:") or "agent"
        org_chart.add_child(pid,cid,nm,role); self.refresh()

    def remove_node(self):
        sel = self.tv.selection()
        if not sel: return
        nid = sel[0]
        if messagebox.askyesno("Confirm",f"Remove {nid!r}?"):
            org_chart.remove_node(nid); self.app.refresh_profile(); self.refresh()

    def show_details(self):
        sel = self.tv.selection()
        if not sel: messagebox.showinfo("Info","Select a node first."); return
        nid = sel[0]
        self.dt.delete(1.0, tk.END)
        d = agent_tracker.stats(nid)
        self.dt.insert(tk.END, json.dumps(d, indent=2) if d else f"No data for {nid!r}.")



class WorkflowTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Workflow Chains", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        self.chain_var = tk.StringVar()
        chains = list(WORKFLOW_CHAINS.keys())
        self.chain_combo = ttk.Combobox(top, textvariable=self.chain_var, values=chains, width=20)
        self.chain_combo.pack(side=tk.LEFT, padx=5)
        if chains: self.chain_var.set(chains[0])
        ttk.Button(top, text="Show Details", command=self.show_details).pack(side=tk.LEFT, padx=2)
        mid = ttk.LabelFrame(parent, text="Run Workflow", padding=5)
        mid.pack(fill=tk.X, padx=5, pady=2)
        self.task_var = tk.StringVar()
        ttk.Entry(mid, textvariable=self.task_var, width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(mid, text="Run", command=self.run_chain).pack(side=tk.LEFT, padx=2)
        self.output = scrolledtext.ScrolledText(parent, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4")
        self.output.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        ttk.Button(parent, text="Refresh Runs", command=self.list_runs).pack(pady=2)
        self.list_runs()

    def log(self, text): self.output.insert(tk.END, text + "\n"); self.output.see(tk.END)

    def show_details(self):
        self.output.delete(1.0, tk.END)
        cid = self.chain_var.get()
        chain = WORKFLOW_CHAINS.get(cid, {})
        if not chain: return
        self.log(f"Chain: {chain['name']} ({len(chain['steps'])} steps)")
        self.log("="*50)
        for i, step in enumerate(chain["steps"]):
            self.log(f"Step {i+1}: {step.id} | Role: {step.role}")
            self.log(f"  Prompt: {step.system_prompt[:100]}...")
            self.log("")

    def run_chain(self):
        cid = self.chain_var.get(); task = self.task_var.get()
        if not cid or not task: return
        self.output.delete(1.0, tk.END)
        self.log(f"Running: {cid} on '{task}'...")
        self.log("="*50)
        threading.Thread(target=self._do_run, args=(cid, task), daemon=True).start()

    def _do_run(self, cid, task):
        try:
            result = workflow_engine.run_all_simulated(cid, task)
            self.app.win.after(0, self.log, f"Run ID: {result['run_id']} | Duration: {result['duration_s']:.2f}s")
            for out in result["outputs"]:
                self.app.win.after(0, self.log, f"  {out}")
            self.app.win.after(0, self.list_runs)
        except Exception as e:
            self.app.win.after(0, self.log, f"Error: {e}")

    def list_runs(self):
        pass

class ApiTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="API Configurations", padding=5)
        top.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.tree = ttk.Treeview(top, columns=("id","provider","model","key","enabled"), show="headings", height=6)
        self.tree.heading("id", text="ID"); self.tree.heading("provider", text="Provider")
        self.tree.heading("model", text="Model"); self.tree.heading("key", text="Key Prefix")
        self.tree.heading("enabled", text="Enabled")
        self.tree.column("id", width=80); self.tree.column("provider", width=100)
        self.tree.column("model", width=200); self.tree.column("key", width=100); self.tree.column("enabled", width=60)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        btn_frame = ttk.Frame(parent); btn_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(btn_frame, text="Add API", command=self.add_api).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Remove API", command=self.remove_api).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Toggle", command=self.toggle_api).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=2)
        self.refresh()

    def refresh(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        for a in api_configs:
            self.tree.insert("", tk.END, values=(a.id, a.provider, a.model, a.key_prefix + "...", "✓" if a.enabled else "✗"))

    def add_api(self):
        d = tk.Toplevel(self.app.win); d.title("Add API"); d.geometry("400x250")
        ttk.Label(d, text="Provider (e.g., openrouter):").pack(pady=2)
        pv = tk.StringVar(); ttk.Entry(d, textvariable=pv).pack(pady=2, padx=10, fill=tk.X)
        ttk.Label(d, text="Model:").pack(pady=2)
        mv = tk.StringVar(); ttk.Entry(d, textvariable=mv).pack(pady=2, padx=10, fill=tk.X)
        def confirm():
            if pv.get() and mv.get():
                ap = APIConfig(f"api-{len(api_configs)+1}", pv.get(), mv.get())
                api_configs.append(ap); self.refresh(); self.app.set_status(f"Added API: {pv.get()}/{mv.get()}")
            d.destroy()
        ttk.Button(d, text="Add", command=confirm).pack(pady=10)

    def remove_api(self):
        sel = self.tree.selection()
        if not sel: return
        vals = self.tree.item(sel[0], "values")
        if messagebox.askyesno("Confirm", f"Remove API {vals[0]}?"):
            for i, a in enumerate(api_configs):
                if a.id == vals[0]: api_configs.pop(i); break
            self.refresh()

    def toggle_api(self):
        sel = self.tree.selection()
        if not sel: return
        vals = self.tree.item(sel[0], "values")
        for a in api_configs:
            if a.id == vals[0]: a.enabled = not a.enabled; break
        self.refresh()

class AgentsTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Agent Performance", padding=5)
        top.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.tree = ttk.Treeview(top, columns=("id","role","elo","tasks","success","status"), show="headings", height=10)
        self.tree.heading("id", text="Agent ID"); self.tree.heading("role", text="Role")
        self.tree.heading("elo", text="ELO"); self.tree.heading("tasks", text="Tasks")
        self.tree.heading("success", text="Success %"); self.tree.heading("status", text="Status")
        self.tree.column("id", width=120); self.tree.column("role", width=80); self.tree.column("elo", width=60)
        self.tree.column("tasks", width=50); self.tree.column("success", width=70); self.tree.column("status", width=60)
        self.tree.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        btn_frame = ttk.Frame(parent); btn_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(btn_frame, text="Register Agent", command=self.register_agent).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=2)
        self.refresh()

    def refresh(self):
        for item in self.tree.get_children(): self.tree.delete(item)
        stats = agent_tracker.stats()
        for aid, info in stats["agents"].items():
            self.tree.insert("", tk.END, values=(aid, info["role"], info["elo"], info["tasks"], f"{info['success_rate']:.0%}", info["status"]))

    def register_agent(self):
        aid = simpledialog.askstring("Register Agent", "Agent ID:")
        if not aid: return
        role = simpledialog.askstring("Register Agent", "Role:")
        if not role: return
        agent_tracker.register(aid, role); self.refresh(); self.app.set_status(f"Registered: {aid}")

class PromptTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Prompt Templates", padding=5)
        top.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.role_var = tk.StringVar()
        roles = list(PROMPT_TEMPLATES.keys())
        self.role_combo = ttk.Combobox(top, textvariable=self.role_var, values=roles, width=20)
        self.role_combo.pack(pady=5)
        if roles: self.role_var.set(roles[0])
        ttk.Label(top, text="Custom Prompt:").pack(anchor=tk.W, padx=5)
        self.prompt_text = tk.Text(top, height=5, font=("Consolas", 10))
        self.prompt_text.pack(fill=tk.X, padx=5, pady=2)
        btn_frame = ttk.Frame(top); btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="Set Custom", command=self.set_prompt).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Reset to Default", command=self.reset_prompt).pack(side=tk.LEFT, padx=2)
        self.preview = scrolledtext.ScrolledText(top, font=("Consolas", 9), bg="#1e1e1e", fg="#d4d4d4", height=10)
        self.preview.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        ttk.Button(top, text="Preview", command=self.preview_prompt).pack(pady=2)

    def set_prompt(self):
        role = self.role_var.get(); content = self.prompt_text.get(1.0, tk.END).strip()
        if role and content:
            prompt_selector.set_custom_prompt(role, content)
            self.app.set_status(f"Custom prompt set for: {role}")

    def reset_prompt(self):
        role = self.role_var.get()
        if role: prompt_selector.reset_role(role); self.app.set_status(f"Reset: {role}")

    def preview_prompt(self):
        self.preview.delete(1.0, tk.END)
        role = self.role_var.get()
        result = prompt_selector.select_prompt(role, "example task", "previous output")
        self.preview.insert(tk.END, result)

class ScheduleTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Schedule Tasks", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        self.task_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.task_var, width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(top, text="Add Task", command=self.add_task).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        ttk.Button(parent, text="Refresh", command=self.refresh).pack(pady=2)
        self.refresh()

    def add_task(self):
        desc = self.task_var.get()
        if desc: scheduler.enqueue(desc, "general", 100, 0.5); self.task_var.set(""); self.refresh()

    def refresh(self):
        self.text.delete(1.0, tk.END)
        s = scheduler.stats()
        lines = [f"Queued: {s['queue_size']}  |  Running: {s['running']}  |  Completed: {s['completed']}  |  Budget: {s['budget_spent']:.0f}"]
        next_tasks = scheduler.next_up(10)
        if next_tasks:
            lines.append("\nNext Up:")
            for nt in next_tasks:
                lines.append(f"  [{nt['urgency']:.1f}] {nt['desc'][:60]} -> {nt['agent']}")
        self.text.insert(tk.END, "\n".join(lines))

class MemoryTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Memory & Thoughts", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        self.query_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.query_var, width=50).pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        ttk.Button(top, text="Search", command=self.search).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Inject Thought", command=self.inject_thought).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def search(self):
        self.text.delete(1.0, tk.END)
        query = self.query_var.get() or "general"
        l1r = l1_memory.recall(query)
        tvdb = thought_vdb.query(query)
        lines = [f"=== L1 Memory (query: {query}) ==="]
        for r in l1r[:5]:
            lines.append(f"  [{r['score']:.2f}] {r['value'][:100]}")
        lines.append(f"\n=== Thought VDB ===")
        for r in tvdb[:5]:
            lines.append(f"  [{r['confidence']:.0%}] {r['thought'][:100]}")
        self.text.insert(tk.END, "\n".join(lines))

    def inject_thought(self):
        thought = self.query_var.get()
        if thought:
            thought_vdb.inject("gui", thought, [])
            self.text.insert(tk.END, f"\n[+] Thought injected: {thought[:60]}")

class LibraryTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Corporate Library", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Show Stats", command=self.show_stats).pack(side=tk.LEFT, padx=2)
        self.query_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.query_var, width=30).pack(side=tk.LEFT, padx=5)
        ttk.Button(top, text="Search", command=self.search).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def show_stats(self):
        self.text.delete(1.0, tk.END)
        s = corp_library.stats()
        lines = [
            "=== Corporate Library Stats ===",
            f"Total Libraries: {s['total_libraries']}",
            f"Total Agents:    {s['total_agents']}",
            f"Total Usage:     {s['total_usage']}",
            f"Avg Quality:     {s['avg_quality']:.2f}",
        ]
        self.text.insert(tk.END, "\n".join(lines))

    def search(self):
        self.text.delete(1.0, tk.END)
        query = self.query_var.get()
        if not query: return
        results = corp_library.search(query)
        lines = [f"=== Search: '{query}' ==="]
        for r in results:
            lines.append(f"  [{r['id']}] {r['name']} v{r['version']} - {r['domain']} (quality: {r['quality']:.2f})")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No results.")

class VoteTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Voting & Consensus", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Create", command=self.create_vote).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="List", command=self.list_votes).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Results", command=self.show_results).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def create_vote(self):
        topic = simpledialog.askstring("Create Vote", "Topic:")
        if not topic: return
        v = voting_engine.create_vote(topic)
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Vote created: {json.dumps(v, indent=2)}")

    def list_votes(self):
        self.text.delete(1.0, tk.END)
        votes = voting_engine.list_votes()
        lines = ["=== Open Votes ==="]
        for v in votes:
            lines.append(f"  [{v['id']}] {v['topic']} — {v['status']} ({len(v['votes'])} votes)")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No votes.")

    def show_results(self):
        self.text.delete(1.0, tk.END)
        votes = voting_engine.list_votes()
        lines = ["=== All Vote Results ==="]
        for v in votes:
            lines.append(f"\n[{v['id']}] {v['topic']} ({v['status']})")
            for vv in v.get('votes', []):
                lines.append(f"  - {vv['voter']}: {vv['vote']}")
            if v.get('result'):
                lines.append(f"  Result: {v['result']}")
        self.text.insert(tk.END, "\n".join(lines))

class ProbeTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Logic Probe", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="List", command=self.list_thoughts).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Flagged", command=self.show_flagged).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Resolve", command=self.resolve).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def list_thoughts(self):
        self.text.delete(1.0, tk.END)
        thoughts = logic_probe.list_thoughts()
        lines = ["=== Probed Thoughts ==="]
        for t in thoughts[-20:]:
            lines.append(f"  [{t['id']}] {t['content'][:60]} — {t.get('status','?')}")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No thoughts.")

    def show_flagged(self):
        self.text.delete(1.0, tk.END)
        flagged = logic_probe.list_flagged()
        lines = ["=== Flagged Contradictions ==="]
        for f in flagged:
            lines.append(f"  {f['thought_ids']}: {f['reason']}")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No flagged.")

    def resolve(self):
        tid = simpledialog.askstring("Resolve", "Thought ID:")
        if not tid: return
        logic_probe.resolve_flagged(tid)
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Resolved thought {tid}.")

class SentinelTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Sentinel Monitor", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Status", command=self.show_status).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Alerts", command=self.show_alerts).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="History", command=self.show_history).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def show_status(self):
        self.text.delete(1.0, tk.END)
        s = sentinel.get_status()
        self.text.insert(tk.END, json.dumps(s, indent=2))

    def show_alerts(self):
        self.text.delete(1.0, tk.END)
        alerts = sentinel.get_alerts()
        lines = ["=== Recent Alerts ==="]
        for a in alerts[-20:]:
            lines.append(f"  {a['time']} [{a['level']}] {a['message']}")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No alerts.")

    def show_history(self):
        self.text.delete(1.0, tk.END)
        h = sentinel.get_history()
        lines = ["=== Health History ==="]
        for entry in h[-30:]:
            lines.append(f"  {entry['time']} — health={entry['health']}")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No history.")

class SheriffTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Sheriff Rules", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="List", command=self.list_rules).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Add", command=self.add_rule).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Toggle", command=self.toggle_rule).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def list_rules(self):
        self.text.delete(1.0, tk.END)
        rules = sheriff.list_rules()
        lines = ["=== Sheriff Rules ==="]
        for r in rules:
            lines.append(f"  [{r['id']}] {r['name']} — enabled={r['enabled']} severity={r['severity']}")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No rules.")

    def add_rule(self):
        name = simpledialog.askstring("Add Rule", "Rule name:")
        if not name: return
        rule = sheriff.add_rule(name)
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Rule added: {rule}")

    def toggle_rule(self):
        rid = simpledialog.askstring("Toggle Rule", "Rule ID:")
        if not rid: return
        r = sheriff.toggle_rule(rid)
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Rule {rid} enabled={r}.")

class SessionTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Session Manager", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Start", command=self.start_session).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="End", command=self.end_session).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Active", command=self.show_active).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="List", command=self.list_sessions).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def start_session(self):
        s = session_manager.start_session()
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Session started: {json.dumps(s, indent=2)}")

    def end_session(self):
        s = session_manager.end_session()
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Session ended: {json.dumps(s, indent=2) if s else 'No active session.'}")

    def show_active(self):
        self.text.delete(1.0, tk.END)
        a = session_manager.get_active()
        self.text.insert(tk.END, json.dumps(a, indent=2) if a else "No active session.")

    def list_sessions(self):
        self.text.delete(1.0, tk.END)
        sessions = session_manager.list_sessions()
        lines = ["=== Sessions ==="]
        for s in sessions[-20:]:
            lines.append(f"  [{s['id']}] started={s['start']} status={s.get('status','?')}")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No sessions.")

class CogTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Cognitive Controls", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Settings", command=self.show_settings).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Set Friction", command=self.set_friction).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Set Heat", command=self.set_heat).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def show_settings(self):
        self.text.delete(1.0, tk.END)
        s = cognitive_controls.get_settings()
        self.text.insert(tk.END, json.dumps(s, indent=2))

    def set_friction(self):
        val = simpledialog.askfloat("Set Friction", "Friction level (0.0-1.0):", minvalue=0.0, maxvalue=1.0)
        if val is None: return
        cognitive_controls.set_friction(val)
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Friction set to {val}")

    def set_heat(self):
        val = simpledialog.askfloat("Set Heat", "Heat level (0.0-1.0):", minvalue=0.0, maxvalue=1.0)
        if val is None: return
        cognitive_controls.set_heat(val)
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Heat set to {val}")

class TrainTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Training", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Tasks", command=self.show_tasks).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Add Repo", command=self.add_repo).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Add Pattern", command=self.add_pattern).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="List Patterns", command=self.list_patterns).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def show_tasks(self):
        self.text.delete(1.0, tk.END)
        tasks = training.get_tasks()
        lines = ["=== Training Tasks ==="]
        for t in tasks:
            lines.append(f"  [{t['id']}] {t['name']} — {t.get('status','?')}")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No tasks.")

    def add_repo(self):
        url = simpledialog.askstring("Add Repo", "Repository URL:")
        if not url: return
        r = training.add_repo(url)
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Repo added: {r}")

    def add_pattern(self):
        key = simpledialog.askstring("Add Pattern", "Pattern key:")
        val = simpledialog.askstring("Add Pattern", "Pattern value:")
        if not key or not val: return
        training.add_pattern(key, val)
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Pattern '{key}' stored.")

    def list_patterns(self):
        self.text.delete(1.0, tk.END)
        key = simpledialog.askstring("List Patterns", "Key (or leave blank):") or ""
        patterns = training.get_patterns(key) if key else training.get_all_patterns()
        lines = ["=== Patterns ==="]
        for p in patterns:
            lines.append(f"  {p['key']}: {p['value'][:60]}")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No patterns.")

class PBTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="PBT Evolution", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Status", command=self.show_status).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="History", command=self.show_history).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Population", command=self.show_pop).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def show_status(self):
        self.text.delete(1.0, tk.END)
        s = pbt_tracker.get_status()
        self.text.insert(tk.END, json.dumps(s, indent=2))

    def show_history(self):
        self.text.delete(1.0, tk.END)
        h = pbt_tracker.get_history()
        lines = ["=== Fitness History ==="]
        for entry in h[-30:]:
            lines.append(f"  gen={entry['gen']} best={entry['best_fitness']:.4f} avg={entry['avg_fitness']:.4f}")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No history.")

    def show_pop(self):
        self.text.delete(1.0, tk.END)
        p = pbt_tracker.get_population()
        lines = ["=== Population ==="]
        for item in p:
            lines.append(f"  {item['name']} — fitness={item['fitness']:.4f}")
        self.text.insert(tk.END, "\n".join(lines) if lines else "No population.")

class CompactTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Session Compaction", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="List", command=self.list_sessions).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Search", command=self.search).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def list_sessions(self):
        self.text.delete(1.0, tk.END)
        all_s = session_archiver.get_all()
        lines = ["=== Compacted Sessions ==="]
        for s in all_s:
            lines.append(f"  [{s['id']}] {s['label']} — {s['messages']} msgs")
        self.text.insert(tk.END, '\n'.join(lines) if lines else "No sessions.")

    def search(self):
        q = simpledialog.askstring("Search", "Search query:")
        if not q: return
        self.text.delete(1.0, tk.END)
        r = session_archiver.search_content(q)
        lines = [f"=== Search: '{q}' ==="]
        for hit in r[:10]:
            lines.append(f"  {hit['session']}: {hit['context'][:100]}")
        self.text.insert(tk.END, '\n'.join(lines) if lines else "No matches.")

class FileTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="File Access", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Info", command=self.show_info).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Grep", command=self.do_grep).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Glob", command=self.do_glob).pack(side=tk.LEFT, padx=2)
        ttk.Label(top, text="Path:").pack(side=tk.LEFT, padx=5)
        self.path_var = tk.StringVar(value=".")
        ttk.Entry(top, textvariable=self.path_var, width=20).pack(side=tk.LEFT)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def show_info(self):
        self.text.delete(1.0, tk.END)
        r = file_agent.info(self.path_var.get())
        self.text.insert(tk.END, json.dumps(r, indent=2) if "error" not in r else r["error"])

    def do_grep(self):
        pat = simpledialog.askstring("Grep", "Pattern:")
        if not pat: return
        self.text.delete(1.0, tk.END)
        r = file_agent.search(pat, self.path_var.get())
        lines = [f"=== Grep '{pat}' ({r['matches']} matches) ==="]
        for res in r["results"][:30]:
            lines.append(f"  {res['file']}:{res['line']} {res['content'][:80]}")
        self.text.insert(tk.END, '\n'.join(lines))

    def do_glob(self):
        pat = simpledialog.askstring("Glob", "Pattern:")
        if not pat: return
        self.text.delete(1.0, tk.END)
        r = file_agent.glob(pat)
        lines = [f"=== Glob '{pat}' ({r['matches']} files) ==="]
        for f in r["files"][:30]:
            lines.append(f"  {f}")
        self.text.insert(tk.END, '\n'.join(lines))

class BrowseTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Browser", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Navigate", command=self.navigate).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Screenshot", command=self.screenshot).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="State", command=self.show_state).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Close", command=self.close_browser).pack(side=tk.LEFT, padx=2)
        self.url_var = tk.StringVar(value="https://google.com")
        ttk.Entry(top, textvariable=self.url_var, width=30).pack(side=tk.LEFT, padx=5)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def navigate(self):
        self.text.delete(1.0, tk.END)
        r = browser.navigate(self.url_var.get())
        self.text.insert(tk.END, f"Title: {r.get('title','?')}\nStatus: {r['status']}\n\n{r.get('text_preview','')[:2000]}")

    def screenshot(self):
        b64 = browser.screenshot()
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Screenshot taken: {len(b64)} bytes" if b64 else "Failed")

    def show_state(self):
        self.text.delete(1.0, tk.END)
        s = browser.get_state()
        lines = ["=== Interactive Elements ==="]
        for el in s.get("elements", [])[:20]:
            lines.append(f"  {el['tag']} '{el['text'][:30]}' at ({el['center_x']},{el['center_y']})")
        self.text.insert(tk.END, '\n'.join(lines))

    def close_browser(self):
        browser.close()
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, "Browser closed.")

class ComputerTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Computer Use", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Screenshot", command=self.screenshot).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Position", command=self.position).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Windows", command=self.windows).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Demo Notepad", command=self.demo).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def screenshot(self):
        b64 = computer.screenshot()
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Desktop screenshot: {len(b64)} bytes" if b64 else "Failed")

    def position(self):
        p = computer.get_position()
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, f"Mouse: ({p['x']}, {p['y']})")

    def windows(self):
        self.text.delete(1.0, tk.END)
        wins = computer.list_windows()
        lines = ["=== Open Windows ==="]
        for w in wins:
            lines.append(f"  {w.get('title','')[:80]} (visible: {w.get('visible','?')})")
        self.text.insert(tk.END, '\n'.join(lines))

    def demo(self):
        computer.open_notepad()
        self.text.delete(1.0, tk.END)
        self.text.insert(tk.END, "Notepad opened and text typed!")

class CodeTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Code Analysis", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Analyze", command=self.analyze).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Refs", command=self.find_refs).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Suggestions", command=self.suggestions).pack(side=tk.LEFT, padx=2)
        self.path_var = tk.StringVar(value=".")
        ttk.Entry(top, textvariable=self.path_var, width=20).pack(side=tk.LEFT, padx=5)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def analyze(self):
        self.text.delete(1.0, tk.END)
        r = analyzer.analyze_file(self.path_var.get()) if self.path_var.get().endswith('.py') else analyzer.analyze_project(self.path_var.get())
        self.text.insert(tk.END, json.dumps(r, indent=2, default=str)[:5000])

    def find_refs(self):
        name = simpledialog.askstring("Find Refs", "Symbol name:")
        if not name: return
        r = analyzer.find_references(name, self.path_var.get())
        self.text.delete(1.0, tk.END)
        lines = [f"=== References to '{name}' ==="]
        for ref in r[:30]:
            lines.append(f"  {ref['file']}:{ref['line']} {ref['content'][:80]}")
        self.text.insert(tk.END, '\n'.join(lines))

    def suggestions(self):
        self.text.delete(1.0, tk.END)
        r = analyzer.refactor_suggestions(self.path_var.get())
        self.text.insert(tk.END, json.dumps(r, indent=2) if r else "No suggestions.")

class ResearchTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Web Research", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Search", command=self.search).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Fetch", command=self.fetch).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Deep Research", command=self.deep).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def search(self):
        q = simpledialog.askstring("Search", "Query:")
        if not q: return
        self.text.delete(1.0, tk.END)
        r = researcher.search(q)
        lines = [f"=== Search: '{q}' ==="]
        for res in r["results"][:10]:
            lines.append(f"  {res['title'][:60]}\n    {res['url']}\n    {res.get('snippet','')[:80]}")
        self.text.insert(tk.END, '\n'.join(lines))

    def fetch(self):
        url = simpledialog.askstring("Fetch", "URL:")
        if not url: return
        self.text.delete(1.0, tk.END)
        r = researcher.fetch_page(url)
        self.text.insert(tk.END, r.get('content','Error: '+r.get('error','?'))[:5000])

    def deep(self):
        topic = simpledialog.askstring("Deep Research", "Topic:")
        if not topic: return
        self.text.delete(1.0, tk.END)
        r = researcher.research(topic)
        self.text.insert(tk.END, f"Pages: {r['pages_fetched']}\nSynthesis: {r['synthesis']['summary']}\n\n")
        for sec in r['synthesis'].get('sections',[]):
            self.text.insert(tk.END, f"\n{sec['topic']}: {sec['mentioned_in']} sources\n")
            for src in sec['sources'][:3]:
                self.text.insert(tk.END, f"  {src['title'][:60]}\n")

class GitHubTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="GitHub", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="User", command=self.show_user).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Repos", command=self.list_repos).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Issues", command=self.list_issues).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Search", command=self.search_repo).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def show_user(self):
        self.text.delete(1.0, tk.END); u = github.get_user()
        self.text.insert(tk.END, json.dumps(u, indent=2) if isinstance(u, dict) else str(u))

    def list_repos(self):
        self.text.delete(1.0, tk.END); repos = github.list_repos()
        for r in repos[:20]: self.text.insert(tk.END, f"{r['full_name']} ★{r['stars']} [{r['language']}]\n")

    def list_issues(self):
        owner = simpledialog.askstring("Issues", "Owner:") or ""
        repo = simpledialog.askstring("Issues", "Repo:") or ""
        if not owner or not repo: return
        self.text.delete(1.0, tk.END); issues = github.list_issues(owner, repo)
        for i in issues[:20]: self.text.insert(tk.END, f"#{i['number']} {i['title']} [{i['state']}]\n")

    def search_repo(self):
        q = simpledialog.askstring("Search", "Query:") or ""
        if not q: return
        self.text.delete(1.0, tk.END); repos = github.search_repos(q)
        for r in repos[:15]: self.text.insert(tk.END, f"{r['name']} ★{r['stars']} - {r.get('description','')[:60]}\n")

class ApiRouterTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="API Router", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="List", command=self.list_apis).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Classify", command=self.classify).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Call", command=self.call_api).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Stats", command=self.show_stats).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def list_apis(self):
        self.text.delete(1.0, tk.END)
        for p in api_router.list_providers():
            c = ', '.join(p['capabilities'][:3])
            key = '✓' if p['has_key'] else '✗'
            en = 'ON' if p['enabled'] else 'OFF'
            self.text.insert(tk.END, f"{p['name']:<20} {p['model']:<30} {c:<20} key:{key} {en}\n")

    def classify(self):
        task = simpledialog.askstring("Classify", "Task:") or ""
        if not task: return
        self.text.delete(1.0, tk.END)
        r = api_router.route(task)
        self.text.insert(tk.END, f"Task: {task}\nCapability: {r['capability']}\nProvider: {r['provider']}\nModel: {r['model']}\nFallbacks: {', '.join(r.get('fallback_chain',[])[:3])}")

    def call_api(self):
        task = simpledialog.askstring("Call API", "Task:") or ""
        if not task: return
        self.text.delete(1.0, tk.END); self.text.insert(tk.END, "Calling...\n"); self.app.win.update()
        import threading as _t; _t.Thread(target=self._call, args=(task,), daemon=True).start()

    def _call(self, task):
        r = api_router.call(task)
        self.app.win.after(0, lambda: self.text.insert(tk.END, f"Provider: {r.get('provider','?')}\nModel: {r.get('model','?')}\nContent: {(r.get('content','') or r.get('error',''))[:2000]}"))

    def show_stats(self):
        self.text.delete(1.0, tk.END); s = api_router.stats()
        self.text.insert(tk.END, json.dumps(s, indent=2))

class CLIPluginTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="CLI Plugins", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="List", command=self.list_p).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Run", command=self.run_p).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Register", command=self.register_p).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Stats", command=self.pstats).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def list_p(self):
        self.text.delete(1.0, tk.END)
        for p in cli_plugins.list_plugins():
            status = '✅' if p['installed'] else '❌'
            self.text.insert(tk.END, f"{status} {p['name']:<15} {p['command']:<20} {p['description'][:50]} v{p.get('version','')}\n")

    def run_p(self):
        name = simpledialog.askstring("Run Plugin", "Plugin name:") or ""
        if not name: return
        self.text.delete(1.0, tk.END); self.text.insert(tk.END, f"Running {name}...\n")
        r = cli_plugins.run(name)
        self.text.insert(tk.END, f"Success: {r.get('success')}\nStdout: {r.get('stdout','')[:2000]}\nStderr: {r.get('stderr','')[:500]}")

    def register_p(self):
        from cli_plugin import CLIPlugin
        name = simpledialog.askstring("Register", "Plugin name:") or ""
        cmd = simpledialog.askstring("Register", "Command:") or ""
        if name and cmd:
            r = cli_plugins.register_plugin(CLIPlugin(name, cmd))
            self.text.delete(1.0, tk.END); self.text.insert(tk.END, json.dumps(r, indent=2))

    def pstats(self):
        self.text.delete(1.0, tk.END); s = cli_plugins.stats()
        self.text.insert(tk.END, json.dumps(s, indent=2))

class AuthTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Auth Manager", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Status", command=self.show_status).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Set Key", command=self.set_key).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="List", command=self.list_keys).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Remove", command=self.rm_key).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def show_status(self):
        self.text.delete(1.0, tk.END); s = auth.status()
        self.text.insert(tk.END, json.dumps(s, indent=2))

    def set_key(self):
        svc = simpledialog.askstring("Set Key", "Service (openai/anthropic/google):") or ""
        key = simpledialog.askstring("Set Key", "API Key:") or ""
        if svc and key:
            r = auth.set_api_key(svc, key, svc)
            self.text.delete(1.0, tk.END); self.text.insert(tk.END, json.dumps(r, indent=2))

    def list_keys(self):
        self.text.delete(1.0, tk.END); svcs = auth.list_services()
        for s in svcs:
            self.text.insert(tk.END, f"{s['service']:<20} {s.get('provider',''):<15} age:{s['age_days']:.0f}d\n")

    def rm_key(self):
        svc = simpledialog.askstring("Remove Key", "Service:") or ""
        if svc:
            r = auth.remove_api_key(svc)
            self.text.delete(1.0, tk.END); self.text.insert(tk.END, json.dumps(r, indent=2))

class AgentTreeTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Agent Workflow", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Delegations", command=self.show_delegations).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Events", command=self.show_events).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Stats", command=self.show_stats).pack(side=tk.LEFT, padx=2)
        self.mindmap_frame = ttk.Frame(parent)
        self.mindmap_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        self.mindmap_widget = MindMapWidget(self.mindmap_frame)
        self.mindmap_widget.pack(fill=tk.BOTH, expand=True)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4", height=8)
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def refresh(self):
        self.mindmap_widget.refresh()
        self.text.delete(1.0, tk.END); self.text.insert(tk.END, render_tree_text())

    def show_delegations(self):
        self.text.delete(1.0, tk.END); self.mindmap_widget.refresh()
        for d in agent_tree.delegation_history(20):
            self.text.insert(tk.END, f"{d.get('time',''):.0f} {d['delegated_to']:<20} {d['task'][:50]} -> {' > '.join(d.get('path',[]))}\n")

    def show_events(self):
        self.text.delete(1.0, tk.END)
        for e in agent_tree.get_events(limit=20):
            self.text.insert(tk.END, f"{e['time']:.0f} [{e['type']}] {json.dumps(e['data'])[:80]}\n")

    def show_stats(self):
        self.text.delete(1.0, tk.END); s = agent_tree.stats()
        self.text.insert(tk.END, json.dumps(s, indent=2))

class PixelVisionTab(NotebookTab):
    def __init__(self, parent, app):
        super().__init__(parent, app)
        top = ttk.LabelFrame(parent, text="Pixel Vision", padding=5)
        top.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(top, text="Describe", command=self.describe).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Elements", command=self.elements).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Colors", command=self.colors).pack(side=tk.LEFT, padx=2)
        ttk.Button(top, text="Pick Color", command=self.pick_color).pack(side=tk.LEFT, padx=2)
        self.text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#1e1e1e", fg="#d4d4d4")
        self.text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

    def describe(self):
        self.text.delete(1.0, tk.END); self.text.insert(tk.END, "Capturing screen...\n"); self.app.win.update()
        import threading as _t; _t.Thread(target=self._desc, daemon=True).start()

    def _desc(self):
        try:
            d = pixel_vision.describe_screen()
            self.app.win.after(0, lambda: self.text.insert(tk.END, json.dumps({k:v for k,v in d.items() if k != 'screenshot_b64'}, indent=2)))
        except Exception as e:
            self.app.win.after(0, lambda: self.text.insert(tk.END, f"Error: {e}"))

    def elements(self):
        self.text.delete(1.0, tk.END)
        import threading as _t
        def _run():
            try:
                els = pixel_vision.detect_elements()
                self.app.win.after(0, lambda: [self.text.insert(tk.END, f"{e.type:<10} at ({e.x},{e.y}) {e.width}x{e.height} text='{e.text[:30]}' conf={e.confidence:.2f} {'✓' if e.is_interactive else ' '}\n") for e in els[:50]])
            except Exception as ex:
                self.app.win.after(0, lambda: self.text.insert(tk.END, f"Error: {ex}"))
        _t.Thread(target=_run, daemon=True).start()

    def colors(self):
        self.text.delete(1.0, tk.END)
        import threading as _t
        def _run():
            try:
                pal = pixel_vision.detect_color_palette()
                self.app.win.after(0, lambda: [self.text.insert(tk.END, f"  {c['hex']}  {c['rgb']}\n") for c in pal])
            except Exception as ex:
                self.app.win.after(0, lambda: self.text.insert(tk.END, f"Error: {ex}"))
        _t.Thread(target=_run, daemon=True).start()

    def pick_color(self):
        x = simpledialog.askinteger("Pick Color", "X:") or 0
        y = simpledialog.askinteger("Pick Color", "Y:") or 0
        self.text.delete(1.0, tk.END); c = unified_vision.get_pixel_color_at(x, y)
        self.text.insert(tk.END, f"Color at ({x},{y}): {c}")

class MAIKGUI:
    def __init__(self):
        self.win = tk.Tk()
        self.win.title("MAIK — Multi-Agent Intelligence Kernel")
        self.win.geometry("1100x780")
        self.win.minsize(800, 600)
        style = ttk.Style()
        style.theme_use("clam")
        # Top bar
        top = ttk.Frame(self.win)
        top.pack(fill=tk.X, padx=5, pady=3)
        ttk.Label(top, text="MAIK", font=("Segoe UI", 16, "bold")).pack(side=tk.LEFT)
        self.profile_label = ttk.Label(top, text="", font=("Segoe UI", 9))
        self.profile_label.pack(side=tk.LEFT, padx=10)
        self.refresh_profile()
        # Notebook with tabs
        self.notebook = ttk.Notebook(self.win)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=3)
        # Create all tabs
        self.tabs = {}
        for name, cls in [("Ask", AskTab), ("Status", StatusTab), ("Council", CouncilTab),
                           ("Org Chart", OrgTab), ("Workflow", WorkflowTab), ("APIs", ApiTab),
                           ("Agents", AgentsTab), ("Prompts", PromptTab),
                           ("Schedule", ScheduleTab), ("Memory", MemoryTab), ("Library", LibraryTab),
                           ("Vote", VoteTab), ("Probe", ProbeTab), ("Sentinel", SentinelTab),
                           ("Sheriff", SheriffTab), ("Session", SessionTab), ("Cog", CogTab),
                           ("Train", TrainTab), ("PBT", PBTab),
                           ("Compact", CompactTab), ("File", FileTab), ("Browse", BrowseTab),
                           ("Computer", ComputerTab), ("Code", CodeTab), ("Research", ResearchTab),
                           ("🔮 MindMap", AgentTreeTab), ("🌐 GitHub", GitHubTab),
                           ("🤖 API Router", ApiRouterTab), ("🔧 CLI Plugins", CLIPluginTab),
                           ("🔑 Auth", AuthTab), ("👁 Pixel Vision", PixelVisionTab)]:
            frame = ttk.Frame(self.notebook)
            self.notebook.add(frame, text=name)
            self.tabs[name] = cls(frame, self)
        # Status bar
        self.status_bar = ttk.Frame(self.win)
        self.status_bar.pack(fill=tk.X, padx=5, pady=2)
        self.status_label = ttk.Label(self.status_bar, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.ceo_label = ttk.Label(self.status_bar, text="", relief=tk.SUNKEN, width=30, anchor=tk.W)
        self.ceo_label.pack(side=tk.RIGHT, padx=2)
        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)

    def refresh_profile(self):
        self.profile_label.config(text=f"{council.num_ceos} CEOs — {council.profile} — {len(api_configs)} APIs — {org_chart.total_count()['ceos']} org CEOs")

    def set_status(self, text):
        self.status_label.config(text=text)
        self.win.update_idletasks()

    def set_ceo(self, text):
        self.ceo_label.config(text=text)
        self.win.update_idletasks()

    def run(self):
        self.win.mainloop()

if __name__ == "__main__":
    MAIKGUI().run()
