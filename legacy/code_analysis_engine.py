"""Code Analysis Engine — radon (complexity/MI) + AST (deps, call graph, dead code, refactoring)."""
from __future__ import annotations
import ast, re, os, json, time, itertools
from pathlib import Path
from typing import Optional
from collections import Counter, defaultdict

try:
    from radon.complexity import cc_visit, cc_rank
    from radon.metrics import mi_visit, mi_rank
    HAS_RADON = True
except ImportError:
    HAS_RADON = False

EXCLUDE_DIRS = {"__pycache__", ".git", ".venv", "node_modules", "dist", "build", ".egg-info", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
STDLIB_MODULES = {
    "os", "sys", "re", "json", "time", "math", "random", "collections", "pathlib",
    "typing", "hashlib", "uuid", "dataclasses", "functools", "itertools", "abc",
    "enum", "io", "base64", "copy", "datetime", "threading", "subprocess", "ast",
    "inspect", "textwrap", "string", "struct", "tempfile", "shutil", "glob",
    "logging", "warnings", "traceback", "pprint", "argparse", "configparser",
    "csv", "xml", "html", "http", "urllib", "socket", "ssl", "email", "json",
    "pickle", "shelve", "dbm", "sqlite3", "bz2", "gzip", "zipfile", "tarfile",
    "haslib", "hmac", "secrets", "numbers", "decimal", "fractions", "statistics",
    "operator", "bisect", "array", "weakref", "types", "copyreg", "enum",
    "asyncio", "concurrent", "multiprocessing", "queue", "contextvars",
    "signal", "mmap", "ctypes", "platform", "errno",
}


class CodeAnalyzer:
    """AST + radon hybrid: cyclomatic complexity, maintainability index, deps, call graphs, dead code."""

    def __init__(self, workspace: str = "."):
        self.workspace = Path(workspace).resolve()
        self._cache: dict[str, dict] = {}

    def _resolve(self, path: str) -> Path:
        p = Path(path)
        return (self.workspace / p).resolve() if not p.is_absolute() else p.resolve()

    # ── Per-file analysis ──────────────────────────────────────────

    def analyze_file(self, path: str) -> dict:
        fp = self._resolve(path)
        if not fp.exists():
            return {"error": f"File not found: {path}"}
        text = fp.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text, filename=str(fp))
        except SyntaxError as e:
            return {"error": f"Syntax error: {e}", "file": str(fp)}
        result = {
            "file": str(fp.relative_to(self.workspace)),
            "size": len(text),
            "lines": len(text.splitlines()),
            "imports": self._get_imports(tree),
            "classes": self._get_classes(tree),
            "functions": self._get_functions(tree),
            "complexity": self._get_complexity(text),
            "maintainability": self._get_maintainability(text),
            "metrics": self._get_metrics(tree, text),
            "dependencies": self._get_dependencies(text),
            "dead_code": self._find_dead_code(tree, text),
        }
        self._cache[str(fp)] = result
        return result

    def analyze_project(self, path: str = ".", include: str = "*.py") -> dict:
        base = self._resolve(path)
        results = {}
        for fp in base.rglob(include):
            if any(ex in str(fp) for ex in EXCLUDE_DIRS):
                continue
            try:
                r = self.analyze_file(str(fp))
                if "error" not in r:
                    results[str(fp.relative_to(self.workspace))] = r
            except Exception:
                pass
        return self._summarize(results)

    # ── Import extraction ──────────────────────────────────────────

    def _get_imports(self, tree: ast.AST) -> list[dict]:
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({"type": "import", "module": alias.name, "alias": alias.asname})
            elif isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                for alias in node.names:
                    imports.append({"type": "from", "module": mod, "name": alias.name, "alias": alias.asname})
        return imports

    def _get_classes(self, tree: ast.AST) -> list[dict]:
        classes = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [self._node_name(b) for b in node.bases]
                methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                classes.append({
                    "name": node.name,
                    "bases": bases,
                    "methods": methods,
                    "method_count": len(methods),
                    "decorators": [self._node_name(d) for d in node.decorator_list],
                    "line": node.lineno,
                })
        return classes

    def _get_functions(self, tree: ast.AST) -> list[dict]:
        funcs = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = [a.arg for a in node.args.args]
                funcs.append({
                    "name": node.name,
                    "args": args,
                    "arg_count": len(args),
                    "decorators": [self._node_name(d) for d in node.decorator_list],
                    "line": node.lineno,
                })
        return funcs

    # ── Complexity (radon) ─────────────────────────────────────────

    def _get_complexity(self, text: str) -> dict:
        if not HAS_RADON:
            return self._fallback_complexity(text)
        try:
            blocks = cc_visit(text)
            by_func = {b.name: b.complexity for b in blocks}
            total = sum(by_func.values())
            return {
                "total": total,
                "functions": by_func,
                "avg": total / max(len(by_func), 1),
                "rank": max((cc_rank(c) for c in by_func.values()), default="A"),
            }
        except Exception:
            return self._fallback_complexity(text)

    def _fallback_complexity(self, text: str) -> dict:
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return {"total": 0, "functions": {}, "avg": 0, "rank": "A"}
        by_func = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                by_func[node.name] = self._cyclomatic(node)
        total = sum(by_func.values())
        return {"total": total, "functions": by_func, "avg": total / max(len(by_func), 1), "rank": "A"}

    def _cyclomatic(self, node) -> int:
        c = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.And, ast.Or, ast.Assert)):
                c += 1
            elif isinstance(child, ast.Try):
                c += len(child.handlers)
            elif isinstance(child, ast.ExceptHandler):
                c += 1
        return c

    # ── Maintainability Index (radon) ──────────────────────────────

    def _get_maintainability(self, text: str) -> dict:
        if not HAS_RADON:
            return {"mi": 100.0, "rank": "A"}
        try:
            mi = mi_visit(text, multi=False)
            return {"mi": round(mi, 1), "rank": mi_rank(mi)}
        except Exception:
            return {"mi": 100.0, "rank": "A"}

    # ── Metrics ────────────────────────────────────────────────────

    def _get_metrics(self, tree: ast.AST, text: str) -> dict:
        lines = text.splitlines()
        total = len(lines)
        code = sum(1 for l in lines if l.strip() and not l.strip().startswith("#"))
        comments = sum(1 for l in lines if l.strip().startswith("#"))
        blanks = sum(1 for l in lines if not l.strip())
        docstrings = sum(1 for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Module)) and ast.get_docstring(n))
        return {
            "total_lines": total,
            "code_lines": code,
            "comment_lines": comments,
            "blank_lines": blanks,
            "docstrings": docstrings,
            "comment_ratio": round(comments / max(code, 1), 3),
        }

    def _get_dependencies(self, text: str) -> list[str]:
        deps = set()
        for m in re.finditer(r"^(?:from|import)\s+(\w+)", text, re.MULTILINE):
            deps.add(m.group(1))
        return sorted(d for d in deps if d not in STDLIB_MODULES)[:30]

    # ── Dead code detection ────────────────────────────────────────

    def _find_dead_code(self, tree: ast.AST, text: str) -> list[dict]:
        defined = set()
        called = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                called.add(node.func.id)
        private_defined = {n for n in defined if n.startswith("_") and not n.startswith("__")}
        unused = private_defined - called
        return [{"name": n, "line": 0} for n in sorted(unused)]

    # ── Call graph ─────────────────────────────────────────────────

    def call_graph(self, path: str) -> dict:
        fp = self._resolve(path)
        if not fp.exists():
            return {"error": "File not found"}
        text = fp.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return {"error": "Syntax error"}
        graph = {}
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                calls = set()
                for child in ast.walk(node):
                    if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                        calls.add(child.func.id)
                graph[node.name] = sorted(calls)
        return {"file": str(fp.relative_to(self.workspace)), "graph": graph}

    # ── References ─────────────────────────────────────────────────

    def find_references(self, name: str, path: str = ".") -> list[dict]:
        base = self._resolve(path)
        refs = []
        for fp in base.rglob("*.py"):
            if any(ex in str(fp) for ex in EXCLUDE_DIRS):
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if name in line and not line.strip().startswith("#"):
                        refs.append({
                            "file": str(fp.relative_to(self.workspace)),
                            "line": i,
                            "content": line.strip()[:150],
                        })
            except Exception:
                pass
        return refs[:100]

    # ── Search ─────────────────────────────────────────────────────

    def search_code(self, pattern: str, path: str = ".", include: str = "*.py") -> dict:
        base = self._resolve(path)
        regex = re.compile(pattern, re.IGNORECASE)
        results = []
        for fp in base.rglob(include):
            if any(ex in str(fp) for ex in EXCLUDE_DIRS):
                continue
            try:
                text = fp.read_text(encoding="utf-8", errors="ignore")
                for i, line in enumerate(text.splitlines(), 1):
                    if regex.search(line):
                        results.append({"file": str(fp.relative_to(self.workspace)), "line": i, "content": line.strip()[:200]})
            except Exception:
                pass
        return {"pattern": pattern, "matches": len(results), "results": results[:500]}

    # ── Refactoring suggestions ────────────────────────────────────

    def refactor_suggestions(self, path: str) -> list[dict]:
        fp = self._resolve(path)
        if not fp.exists():
            return [{"error": "File not found"}]
        text = fp.read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(text)
        except SyntaxError:
            return [{"error": "Syntax error"}]
        suggestions = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if len(node.args.args) > 6:
                    suggestions.append({
                        "type": "too_many_args",
                        "name": node.name,
                        "detail": f"{len(node.args.args)} arguments",
                        "line": node.lineno,
                    })
                comp = self._cyclomatic(node)
                if comp > 10:
                    suggestions.append({
                        "type": "high_complexity",
                        "name": node.name,
                        "detail": f"cyclomatic complexity {comp}",
                        "line": node.lineno,
                    })
            elif isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
                if len(methods) > 15:
                    suggestions.append({
                        "type": "god_class",
                        "name": node.name,
                        "detail": f"{len(methods)} methods — consider splitting",
                        "line": node.lineno,
                    })
        unused = self._find_dead_code(tree, text)
        for u in unused:
            suggestions.append({
                "type": "unused_private",
                "name": u["name"],
                "detail": "defined but never called",
            })
        return suggestions

    # ── Summarize project ──────────────────────────────────────────

    def _summarize(self, results: dict) -> dict:
        n_files = len(results)
        n_lines = sum(r["metrics"]["total_lines"] for r in results.values() if "metrics" in r)
        n_funcs = sum(len(r["functions"]) for r in results.values())
        n_classes = sum(len(r["classes"]) for r in results.values())
        n_complex = sum(r["complexity"]["total"] for r in results.values() if "complexity" in r)
        deps = Counter()
        for r in results.values():
            for d in r.get("dependencies", []):
                deps[d] += 1
        mis = [r["maintainability"]["mi"] for r in results.values() if "maintainability" in r]
        return {
            "files": n_files,
            "lines": n_lines,
            "functions": n_funcs,
            "classes": n_classes,
            "complexity": n_complex,
            "avg_complexity": round(n_complex / max(n_funcs, 1), 2),
            "avg_maintainability": round(sum(mis) / max(len(mis), 1), 1) if mis else 100.0,
            "top_dependencies": deps.most_common(20),
            "file_details": results,
        }

    def stats(self) -> dict:
        return {"cached_files": len(self._cache)}

    @staticmethod
    def _node_name(node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{CodeAnalyzer._node_name(node.value)}.{node.attr}"
        if isinstance(node, ast.Subscript):
            return f"{CodeAnalyzer._node_name(node.value)}[{CodeAnalyzer._node_name(node.slice)}]"
        if isinstance(node, ast.Call):
            return CodeAnalyzer._node_name(node.func)
        if isinstance(node, ast.Constant):
            return str(node.value)
        return str(node)[:50]


analyzer = CodeAnalyzer()
