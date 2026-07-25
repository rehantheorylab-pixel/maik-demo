#!/usr/bin/env python3
"""MAIK Desktop GUI — tkinter-based interface."""

import sys, os, json, threading
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import tkinter as tk
    from tkinter import ttk, scrolledtext
except ImportError:
    print("tkinter not available. Install python3-tk or use 'maik interactive' instead.")
    sys.exit(1)

from config import TokenBudget, council
from router_engine import route
from tree_engine import execute
from learn_engine import learn, get_stats

class MAIKGUI:
    def __init__(self):
        self.win = tk.Tk()
        self.win.title("MAIK — Multi-Agent Intelligence Kernel")
        self.win.geometry("900x700")
        self.win.minsize(700, 500)

        style = ttk.Style()
        style.theme_use("clam")

        top = ttk.Frame(self.win)
        top.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(top, text="MAIK", font=("Segoe UI", 18, "bold")).pack(side=tk.LEFT)
        self.profile_label = ttk.Label(top, text="", font=("Segoe UI", 10))
        self.profile_label.pack(side=tk.LEFT, padx=10)
        self.refresh_profile()

        input_frame = ttk.LabelFrame(self.win, text="Ask MAIK", padding=5)
        input_frame.pack(fill=tk.X, padx=10, pady=5)

        self.input_text = tk.Text(input_frame, height=3, font=("Consolas", 11), wrap=tk.WORD)
        self.input_text.pack(fill=tk.X, pady=2)
        self.input_text.bind("<Control-Return>", lambda e: self.do_ask())

        btn_frame = ttk.Frame(input_frame)
        btn_frame.pack(fill=tk.X, pady=3)

        ttk.Button(btn_frame, text="Ask", command=self.do_ask, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Route Only", command=self.do_route, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Execute Only", command=self.do_execute, width=12).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Clear", command=self.clear_output, width=8).pack(side=tk.RIGHT, padx=2)
        ttk.Label(btn_frame, text=" Domain:").pack(side=tk.RIGHT, padx=2)
        self.domain_var = tk.StringVar(value="")
        ttk.Combobox(btn_frame, textvariable=self.domain_var, values=["code","math","planning","creative","research","security","general"],
                     width=12).pack(side=tk.RIGHT, padx=2)

        output_frame = ttk.LabelFrame(self.win, text="Response", padding=5)
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.output_text = scrolledtext.ScrolledText(
            output_frame, font=("Consolas", 10), wrap=tk.WORD, bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white"
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)

        self.status_bar = ttk.Frame(self.win)
        self.status_bar.pack(fill=tk.X, padx=10, pady=2)

        self.status_label = ttk.Label(self.status_bar, text="Ready", relief=tk.SUNKEN, anchor=tk.W)
        self.status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.ceo_label = ttk.Label(self.status_bar, text="", relief=tk.SUNKEN, width=30, anchor=tk.W)
        self.ceo_label.pack(side=tk.RIGHT, padx=2)

        self.win.protocol("WM_DELETE_WINDOW", self.win.destroy)

    def refresh_profile(self):
        self.profile_label.config(text=f"{council.num_ceos} CEOs — {council.profile} profile")

    def log(self, text, tag=""):
        self.output_text.insert(tk.END, text + "\n", tag)
        self.output_text.see(tk.END)

    def clear_output(self):
        self.output_text.delete(1.0, tk.END)

    def set_status(self, text):
        self.status_label.config(text=text)
        self.win.update_idletasks()

    def set_ceo(self, text):
        self.ceo_label.config(text=text)
        self.win.update_idletasks()

    def do_ask(self):
        problem = self.input_text.get(1.0, tk.END).strip()
        if not problem:
            return
        self.clear_output()
        self.set_status("Routing...")
        domain = self.domain_var.get()
        threading.Thread(target=self._run_ask, args=(problem, domain), daemon=True).start()

    def _run_ask(self, problem, domain):
        try:
            budget = TokenBudget(total=100000)
            r = route(problem, domain, budget)
            self.win.after(0, self.log, f"─── {r['ceo_name']} ──→ {r['expert']} (conf={r['confidence']:.0%})", "header")
            self.win.after(0, self.set_ceo, f"CEO: {r['ceo_name']}")
            self.win.after(0, self.set_status, "Executing...")
            result = execute(problem, domain, budget)
            output = result['solution'][:5000] or "(no output)"
            self.win.after(0, self.log, output)
            learn(problem, output[:500], "success", result['agents_used'], result['confidence'], 0, 0)
            summary = f"conf={result['confidence']:.0%} depth={result['depth']} agents={len(result['agents_used'])}"
            self.win.after(0, self.log, f"\n─── {summary} ───", "summary")
            self.win.after(0, self.set_status, "Done")
        except Exception as e:
            self.win.after(0, self.log, f"Error: {e}")
            self.win.after(0, self.set_status, "Error")

    def do_route(self):
        problem = self.input_text.get(1.0, tk.END).strip()
        if not problem:
            return
        self.clear_output()
        self.set_status("Routing...")
        domain = self.domain_var.get()
        r = route(problem, domain, TokenBudget(total=100000))
        self.log(f"CEO:       {r['ceo_name']} ({r['ceo']})")
        self.log(f"Expert:    {r['expert']}")
        self.log(f"Type:      {r['problem_type']}")
        self.log(f"Conf:      {r['confidence']:.0%}")
        self.log(f"Model:     {r['model']}")
        self.log(f"Cached:    {r['cached']}")
        self.set_ceo(f"CEO: {r['ceo_name']}")
        self.set_status("Routed")

    def do_execute(self):
        problem = self.input_text.get(1.0, tk.END).strip()
        if not problem:
            return
        self.clear_output()
        self.set_status("Executing...")
        domain = self.domain_var.get()
        threading.Thread(target=self._run_execute, args=(problem, domain), daemon=True).start()

    def _run_execute(self, problem, domain):
        try:
            result = execute(problem, domain, TokenBudget(total=100000))
            output = result['solution'][:5000] or "(no output)"
            self.win.after(0, self.log, output)
            summary = f"conf={result['confidence']:.0%} depth={result['depth']} agents={len(result['agents_used'])}"
            self.win.after(0, self.log, f"\n─── {summary} ───", "summary")
            self.win.after(0, self.set_status, "Done")
        except Exception as e:
            self.win.after(0, self.log, f"Error: {e}")
            self.win.after(0, self.set_status, "Error")

    def run(self):
        self.win.mainloop()

if __name__ == "__main__":
    MAIKGUI().run()
