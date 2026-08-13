"""Stub provider — deterministic local stand-in for LLM endpoints.

Purpose: lets the entire kernel (router -> executor -> cascade -> pattern cache
-> bench_truth) be exercised while external endpoints are unreachable
(e.g., sandbox DNS outages, or a user with zero API keys). In production,
disable MAIK_STUB=1 and the stub is never used — the ProviderLadder free
gateways take over.

The stub is deliberately smarter than random: it recognizes common problem
shapes (arithmetic, simple facts) so cascade + benchmark pipelines behave
realistically.
"""

import re
import time
from typing import Dict, List, Optional


def _solve_arithmetic(text: str) -> Optional[str]:
    """Solve contained arithmetic safely."""
    m = re.search(r"([\d\.\s\+\-\*/\(\)\^]+)", text)
    if not m:
        return None
    expr = m.group(1).replace("^", "**")
    try:
        val = eval(expr, {"__builtins__": {}}, {})  # noqa: S307
        if isinstance(val, (int, float)) and not isinstance(val, complex):
            return str(int(val) if isinstance(val, float) and val.is_integer() else round(val, 6))
    except Exception:
        pass
    return None


def _stub_answer(messages: List[dict]) -> str:
    user = " ".join(m.get("content", "") for m in messages if m.get("role") == "user")
    low = user.lower()
    # arithmetic (incl. "17 x 23" spellings)
    for op, pats in {
            "*": [r"(\d+)\s*(?:x|\*)\s*(\d+)"],
            "+": [r"(\d+)\s*\+\s*(\d+)"],
            "-": [r"(\d+)\s*\-\s*(\d+)"],
            "/": [r"(\d+)\s*/\s*(\d+)"],
    }.items():
        m = None
        for pat in pats:
            m = re.search(pat, low)
            if m:
                break
        if m:
            a = float(m.group(1))
            b = float(m.group(2))
            res = {"*": a*b, "+": a+b, "-": a-b, "/": a/b if b else float("nan")}
            r = res[op]
            if r != r:  # nan
                continue
            return str(int(r) if isinstance(r, float) and r.is_integer() else round(r, 4))
    # canned knowledge seeds (Phase E benchmark problems)
    canned = {
        "capital of france": "Paris",
        "largest planet": "Jupiter",
        "speed of light": "299792458 m/s",
        "boiling point of water": "100 degrees Celsius at sea level",
        "atomic number of carbon": "6",
    }
    for key, val in canned.items():
        if key in low:
            return val
    return "The stub provider cannot answer this question live. (MAIK_STUB active — connect real providers for production use.)"


def stub_call(model: str, messages: List[dict], temperature: float = 0.2,
              max_tokens: int = 2048) -> dict:
    """Drop-in compatible with ProviderLadder.call return shape."""
    t0 = time.time()
    content = _stub_answer(messages)
    # simulate realistic latency + token usage
    time.sleep(0.05)
    pt = sum(len(m.get("content", "").split()) for m in messages)
    ct = len(content.split())
    return {
        "content": content, "provider": "stub", "model_used": f"stub/{model}",
        "prompt_tokens": pt, "completion_tokens": ct, "cost_usd": 0.0,
        "duration_s": time.time() - t0,
    }
