"""AI Enhancement Engine — powers all AI improvements across every phase.

Central module that all AI-enhanced features call.
Leverages multi-model routing (Claude/GPT/Gemini) from api_router.
"""

import os, re, json, subprocess, sys, time, difflib
from pathlib import Path

try:
    from api_router import router
    HAS_ROUTER = True
except ImportError:
    HAS_ROUTER = False


def _ai_call(prompt, system=None, max_tokens=2000):
    if not HAS_ROUTER:
        return "[AI engine requires api_router — no router found]"
    try:
        resp = router.call(prompt, system=system, max_tokens=max_tokens)
        if isinstance(resp, dict):
            return resp.get("content", resp.get("text", str(resp)))
        return str(resp)
    except Exception as e:
        return f"[AI call failed: {e}]"


class AIEnhance:
    """AI-powered enhancements for every tool."""

    # ============================================================
    # PHASE 1: Search & Data AI improvements
    # ============================================================

    def semantic_search(self, query, file_paths=None):
        """AI-powered code search: 'find functions that handle auth'"""
        context = ""
        if file_paths:
            snippets = []
            for fp in file_paths[:10]:
                try:
                    with open(fp, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()[:2000]
                    snippets.append(f"=== {fp} ===\n{content}")
                except OSError:
                    continue
            context = "\n\n".join(snippets)
        prompt = f"""Given this natural language query: "{query}"

{'Search through these files and return the most relevant matches with file paths and line numbers:' if context else 'I need to search code for this. Return relevant file patterns, function names, and what to look for.'}

{context[:8000] if context else ''}

Return results as a JSON array of {{"file":"path","line":N,"snippet":"code","relevance":"reason"}}"""
        result = _ai_call(prompt, system="You are a code search engine. Return ONLY valid JSON.", max_tokens=3000)
        return self._try_parse(result, query)

    def schema_infer(self, data_sample, data_format="json"):
        """Infer schema from data sample."""
        prompt = f"""Analyze this {data_format.upper()} data and infer its schema:

{data_sample[:4000]}

Return a JSON schema definition with: field names, types, descriptions, constraints (required/optional/nullable)."""
        result = _ai_call(prompt, system="You are a schema inference engine. Return JSON schema.", max_tokens=2000)
        return self._try_parse(result, {"error": "Could not infer schema"})

    def ai_query_builder(self, natural_query, data_format="json"):
        """Build a jq/yq query from natural language."""
        prompt = f"""Convert this natural language request into a {data_format.upper()} query:

"{natural_query}"

Return ONLY the query string, no explanation."""
        return _ai_call(prompt, system=f"You are a {data_format.upper()} query builder. Return ONLY the query.", max_tokens=500)

    # ============================================================
    # PHASE 2: Git & Coding AI improvements
    # ============================================================

    def explain_diff(self, diff_text):
        """Explain a diff in plain English."""
        if not diff_text or len(diff_text.strip()) < 10:
            return "No diff to explain."
        prompt = f"""Explain this code diff in plain English. Cover:
1. What files changed and why
2. What the actual logic change is
3. Any potential risks or issues

```diff
{diff_text[:6000]}
```"""
        return _ai_call(prompt, system="You are a code review assistant. Be concise and accurate.", max_tokens=2000)

    def generate_commit_message(self, diff_text):
        """Generate a conventional commit message from diff."""
        if not diff_text or len(diff_text.strip()) < 10:
            return "chore: no significant changes"
        prompt = f"""Generate a conventional commit message from this diff.
Format: type(scope): description

Types: feat, fix, chore, refactor, docs, test, style, perf

Diff:
```diff
{diff_text[:5000]}
```

Return ONLY the commit message (subject line + optional body)."""
        return _ai_call(prompt, system="You are a git commit message generator. Be concise.", max_tokens=500)

    def summarize_pr(self, pr_data):
        """Generate AI PR summary."""
        prompt = f"""Summarize this pull request for reviewers:

{json.dumps(pr_data, indent=2)[:5000]}

Return: summary, key changes, testing notes, risks."""
        return _ai_call(prompt, system="You are a PR review assistant. Be thorough but concise.", max_tokens=2000)

    def resolve_conflict_hint(self, conflict_text):
        """Suggest conflict resolution strategy."""
        prompt = f"""Analyze this merge conflict and suggest the best resolution:

```
{conflict_text[:4000]}
```

Explain: what each side changed, the recommended resolution, and why."""
        return _ai_call(prompt, system="You are a merge conflict resolver.", max_tokens=2000)

    # ============================================================
    # PHASE 3: System AI improvements
    # ============================================================

    def detect_anomaly(self, metrics):
        """Detect system anomalies from metrics."""
        prompt = f"""Analyze these system metrics for anomalies:

{json.dumps(metrics, indent=2)[:4000]}

Return: anomalies found (type, severity, value), possible causes, recommended actions.
Format as JSON: {{"anomalies":[{{"type":"cpu","severity":"high","value":95,"cause":"...","action":"..."}}]}}"""
        result = _ai_call(prompt, system="You are a system monitoring AI. Detect anomalies.", max_tokens=2000)
        return self._try_parse(result, {"anomalies": []})

    def suggest_cleanup(self, disk_info):
        """Suggest disk cleanup actions."""
        large_dirs = disk_info.get("large_dirs", [])
        prompt = f"""Analyze disk usage and suggest cleanup actions:
{json.dumps(large_dirs[:20], indent=2) if large_dirs else "Large directories found on disk"}

Return JSON: {{"suggestions":[{{"target":"path","action":"delete/compress/archive","size_mb":100,"reason":"..."}}]}}"""
        result = _ai_call(prompt, system="You are a system cleanup advisor.", max_tokens=2000)
        return self._try_parse(result, {"suggestions": []})

    # ============================================================
    # PHASE 4: Agent Loop AI improvements
    # ============================================================

    def route_to_model(self, task, available_models=None):
        """Route task to best AI model."""
        if not HAS_ROUTER:
            return "[no router]"
        try:
            result = router.route(task)
            return result
        except Exception as e:
            return {"error": str(e)}

    def enhance_prompt(self, user_input):
        """Enhance user input into a better prompt for the coding agent."""
        prompt = f"""Rewrite this user request into a clearer, more actionable prompt for an AI coding agent:

Original: "{user_input}"

Enhanced version (direct, specific, actionable):"""
        return _ai_call(prompt, system="You are a prompt engineering assistant.", max_tokens=500)

    def _try_parse(self, text, fallback):
        """Try to parse JSON from AI response, return fallback dict on failure."""
        if isinstance(text, (dict, list)):
            return text
        try:
            # Find JSON in the response
            match = re.search(r'(\[.*\]|\{.*\})', text, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            return json.loads(text)
        except (json.JSONDecodeError, AttributeError, TypeError):
            return fallback if isinstance(fallback, (dict, list)) else {"result": text}


ai_enhance = AIEnhance()
