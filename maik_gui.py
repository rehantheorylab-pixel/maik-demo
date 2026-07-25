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
        # CEO list
        ceo_frame = ttk.LabelFrame(parent, text="CEOs", padding=5)
        ceo_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(ceo_frame, text="+ Add CEO", command=self.add_ceo).pack(side=tk.LEFT, padx=2)
        self.ceo_var = tk.StringVar(); self.ceo_combo = ttk.Combobox(ceo_frame, textvariable=self.ceo_var, width=20)
        self.ceo_combo.pack(side=tk.LEFT, padx=5)
        # Manager controls
        mgr_frame = ttk.LabelFrame(parent, text="Managers", padding=5)
        mgr_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(mgr_frame, text="+ Add Manager", command=self.add_manager).pack(side=tk.LEFT, padx=2)
        ttk.Button(mgr_frame, text="- Remove Manager", command=self.remove_manager).pack(side=tk.LEFT, padx=2)
        # Employee controls
        emp_frame = ttk.LabelFrame(parent, text="Employees", padding=5)
        emp_frame.pack(fill=tk.X, padx=5, pady=2)
        ttk.Button(emp_frame, text="+ Add Employee", command=self.add_employee).pack(side=tk.LEFT, padx=2)
        ttk.Button(emp_frame, text="- Remove Employee", command=self.remove_employee).pack(side=tk.LEFT, padx=2)
        # Mind map display
        self.mind_text = scrolledtext.ScrolledText(parent, font=("Consolas", 10), bg="#0a0a1a", fg="#d4d4d4")
        self.mind_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)
        ttk.Button(parent, text="Refresh Mind Map", command=self.refresh_mind).pack(pady=2)
        self.refresh_mind()

    def refresh_mind(self):
        self.mind_text.delete(1.0, tk.END)
        mind = org_chart.get_mind_map()
        ceos = list(mind.keys())
        self.ceo_combo["values"] = ceos
        if ceos and not self.ceo_var.get(): self.ceo_var.set(ceos[0])
        lines = ["=== CORPORATE HIERARCHY MIND MAP ==="]
        for ceo_id, cd in mind.items():
            lines.append(f"\n👤 CEO: {cd['name']} ({ceo_id})")
            mgrs = cd.get("managers",{})
            if not mgrs:
                lines.append("   └─ (no managers yet - click Add Manager)")
            for mgr_id, md in mgrs.items():
                lines.append(f"   ├─ 👤 Manager: {md['name']} ({mgr_id})")
                emps = md.get("employees", [])
                if not emps:
                    lines.append("   │   └─ (no employees yet - click Add Employee)")
                for e in emps:
                    lines.append(f"   │   ├─ 👤 {e['name']} ({e['role']}) {'🟢' if e['status']=='idle' else '🟡'} {e['tasks']} tasks")
        self.mind_text.insert(tk.END, "\n".join(lines))

    def add_ceo(self):
        cid = simpledialog.askstring("Add CEO", "CEO ID:")
        if not cid: return
        nm = simpledialog.askstring("Add CEO", "CEO Name:")
        if not nm: return
        org_chart.add_ceo(cid, nm); council.add_ceo(nm); self.refresh_mind()

    def add_manager(self):
        ceo_id = self.ceo_var.get()
        if not ceo_id: return
        mid = simpledialog.askstring("Add Manager", "Manager ID:")
        if not mid: return
        nm = simpledialog.askstring("Add Manager", "Manager Name:")
        if not nm: return
        m = org_chart.add_manager(ceo_id, mid, nm)
        if m: agent_tracker.register(mid, "manager")
        self.refresh_mind()

    def remove_manager(self):
        ceo_id = self.ceo_var.get()
        if not ceo_id: return
        mid = simpledialog.askstring("Remove Manager", "Manager ID to remove:")
        if not mid: return
        org_chart.remove_manager(ceo_id, mid); self.refresh_mind()

    def add_employee(self):
        ceo_id = self.ceo_var.get()
        if not ceo_id: return
        mid = simpledialog.askstring("Add Employee", "Under Manager ID:")
        if not mid: return
        eid = simpledialog.askstring("Add Employee", "Employee ID:")
        if not eid: return
        nm = simpledialog.askstring("Add Employee", "Employee Name:")
        if not nm: return
        role = simpledialog.askstring("Add Employee", "Role (default: employee):") or "employee"
        e = org_chart.add_employee(ceo_id, mid, eid, nm, role)
        if e: agent_tracker.register(eid, role)
        self.refresh_mind()

    def remove_employee(self):
        ceo_id = self.ceo_var.get()
        if not ceo_id: return
        mid = simpledialog.askstring("Remove Employee", "Manager ID:")
        if not mid: return
        eid = simpledialog.askstring("Remove Employee", "Employee ID to remove:")
        if not eid: return
        org_chart.remove_employee(ceo_id, mid, eid); self.refresh_mind()

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
                          ("Schedule", ScheduleTab), ("Memory", MemoryTab), ("Library", LibraryTab)]:
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
