import re
import time
from dataclasses import dataclass, field
from typing import Optional

SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret[_-]?key|api[_-]?secret|app[_-]?secret)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"(?i)-----BEGIN\s+(RSA|DSA|EC|OPENSSH|PRIVATE)\s+KEY-----"),
    re.compile(r"(?i)(sk|pk)_(test|live)_[0-9a-zA-Z]{10,}"),
    re.compile(r"(?i)ghp_[0-9a-zA-Z]{36}"),
    re.compile(r"(?i)token\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"(?i)password\s*[:=]\s*['\"][^'\"]{4,}['\"]"),
]

TOXIC_PATTERNS = [
    re.compile(r"(?i)(you\s+are\s+(stupid|useless|terrible))"),
    re.compile(r"\b(kill\s+yourself|self.?destruct)\b"),
    re.compile(r"(?i)(hate\s+speech|racial\s+slur)"),
]

MALICIOUS_PATTERNS = [
    re.compile(r"(?i)rm\s+-rf\s+/\s*(;|\||&&|\$)"),
    re.compile(r"(?i)(DROP|TRUNCATE)\s+(TABLE|DATABASE)"),
    re.compile(r"(?i)(sudo\s+)?(chmod\s+777|chown\s+\S+\s+/)"),
    re.compile(r"(?i)(curl|wget)\s+\S+\s*(\||;|\$\(|\`)\s*(bash|sh|python)"),
    re.compile(r"(?i)eval\s*\(\s*(input|request|user_input|raw_input)"),
]

class PurityFilter:
    def __init__(self):
        self._rules: list[dict] = []
        self._violations: list[dict] = []

    def add_rule(self, name: str, check_fn, action: str = "block", severity: str = "medium"):
        self._rules.append({"name": name, "check": check_fn, "action": action, "severity": severity})

    def check(self, text: str, context: Optional[dict] = None) -> dict:
        findings = []
        secrets = []
        for i, pat in enumerate(SECRET_PATTERNS):
            matches = pat.findall(text)
            if matches:
                secrets.append({"pattern": i, "type": "secret", "count": len(matches)})
        for pat in TOXIC_PATTERNS:
            matches = pat.findall(text)
            if matches:
                findings.append({"pattern": pat.pattern[:40], "type": "toxic", "count": len(matches)})
        for pat in MALICIOUS_PATTERNS:
            matches = pat.findall(text)
            if matches:
                findings.append({"pattern": pat.pattern[:40], "type": "malicious", "count": len(matches)})
        for rule in self._rules:
            try:
                if rule["check"](text):
                    findings.append({"pattern": rule["name"], "type": "custom", "count": 1, "severity": rule["severity"]})
            except Exception:
                pass
        has_violation = len(findings) > 0 or len(secrets) > 0
        action = "block" if has_violation else "pass"
        if has_violation and len(findings) <= 1 and all(f.get("severity") == "low" for f in findings):
            action = "transform"
        result = {
            "pure": not has_violation,
            "action": action,
            "findings": findings[:5],
            "secrets_detected": len(secrets) > 0,
            "secret_count": len(secrets),
        }
        if has_violation:
            self._violations.append({
                "time": time.time(), "findings": findings, "secrets": len(secrets),
                "text_preview": text[:100],
            })
        return result

    def filter_text(self, text: str, context: Optional[dict] = None) -> str:
        result = self.check(text, context)
        if result["action"] == "block":
            redacted = text
            for pat in SECRET_PATTERNS:
                redacted = pat.sub("[REDACTED]", redacted)
            for pat in MALICIOUS_PATTERNS:
                redacted = pat.sub("[BLOCKED]", redacted)
            return f"[PURITY_BLOCK: {len(result['findings'])} violation(s)]\n{redacted[:2000]}"
        return text

    def violation_count(self) -> int:
        return len(self._violations)

    def recent_violations(self, n: int = 5) -> list[dict]:
        return self._violations[-n:]

purity = PurityFilter()
