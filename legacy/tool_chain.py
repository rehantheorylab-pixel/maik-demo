"""Tool chain — compose multiple CLI commands into pipelines.

Absorbs:
  - Claude Code: composed tools, multi-step workflows
  - Custom: chainable steps with output passing, conditionals, retries
"""

import os, json, subprocess, sys, time, shlex
from pathlib import Path


CHAINS_DIR = Path.home() / ".maik" / "chains"


def _ensure_dir():
    CHAINS_DIR.mkdir(parents=True, exist_ok=True)


def _chain_path(name):
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    return CHAINS_DIR / f"{safe}.json"


class ToolChain:
    """Define and execute multi-step tool pipelines."""

    def __init__(self):
        _ensure_dir()

    # --- Definition ---

    def define(self, name, steps, description=""):
        steps = list(steps)
        for i, step in enumerate(steps):
            if "id" not in step:
                step["id"] = f"step_{i+1}"
            if "tool" not in step or "args" not in step:
                raise ValueError(f"Step {i} needs 'tool' and 'args'")
        chain = {
            "name": name,
            "description": description,
            "steps": steps,
            "created": time.time(),
            "updated": time.time(),
        }
        path = _chain_path(name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(chain, f, indent=2)
        return chain

    def get(self, name):
        path = _chain_path(name)
        if not path.exists():
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def delete(self, name):
        path = _chain_path(name)
        if path.exists():
            path.unlink()
            return True
        return False

    def list_chains(self):
        chains = []
        for path in sorted(CHAINS_DIR.glob("*.json")):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    c = json.load(f)
                chains.append({"name": c["name"], "description": c.get("description", ""),
                               "steps": len(c["steps"]), "updated": c.get("updated", 0)})
            except (json.JSONDecodeError, OSError):
                continue
        return chains

    # --- Execution ---

    def run(self, name, inputs=None, verbose=True):
        chain = self.get(name)
        if not chain:
            return {"error": f"Chain '{name}' not found"}
        inputs = inputs or {}
        outputs = {}
        results = []
        for step in chain["steps"]:
            if verbose:
                print(f"  [{step['id']}] {step.get('tool', '?')} ...", end=" ", flush=True)
            args = self._interpolate(step["args"], inputs, outputs)
            try:
                stdout, stderr, code = self._execute(step["tool"], args)
                step_result = {"id": step["id"], "tool": step["tool"], "success": code == 0,
                               "stdout": stdout[:500], "stderr": stderr[:200], "exit_code": code}
                if step.get("capture"):
                    outputs[step["capture"]] = stdout.strip()
                if step.get("output_var"):
                    outputs[step["output_var"]] = stdout.strip()
                if verbose:
                    print("OK" if code == 0 else f"FAIL (code {code})")
                results.append(step_result)
                if code != 0 and step.get("stop_on_fail", True):
                    if verbose:
                        print(f"  Chain stopped at step '{step['id']}' — exit code {code}")
                    break
            except Exception as e:
                results.append({"id": step["id"], "tool": step["tool"],
                                "success": False, "error": str(e)})
                if verbose:
                    print(f"ERROR: {e}")
                break
        return {"chain": name, "steps": results, "outputs": outputs,
                "success": all(r["success"] for r in results)}

    def _interpolate(self, args, inputs, outputs):
        result = {}
        for k, v in args.items():
            if isinstance(v, str):
                for key, val in {**inputs, **outputs}.items():
                    v = v.replace(f"${{{key}}}", val)
                result[k] = v
            else:
                result[k] = v
        return result

    def _execute(self, tool, args):
        cmd = self._build_cmd(tool, args)
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        return p.stdout, p.stderr, p.returncode

    def _build_cmd(self, tool, args):
        if tool == "python":
            code = args.get("code", "")
            return [sys.executable, "-c", code]
        elif tool == "shell":
            script = args.get("script", "")
            if sys.platform == "win32":
                return ["cmd", "/c", script]
            return ["sh", "-c", script]
        else:
            cmd = [tool]
            for k, v in args.items():
                if k in ("capture", "output_var", "stop_on_fail"):
                    continue
                cmd.append(f"--{k}" if len(k) > 1 else f"-{k}")
                if v is not True:
                    cmd.append(str(v))
            return cmd


tool_chain = ToolChain()
