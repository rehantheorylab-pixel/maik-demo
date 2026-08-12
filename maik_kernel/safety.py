"""Safety gate — kept from maik-demo v2 (audit-verified): stop-light,
budget tripwires, per-CEO spend checks before execution."""

from .config import Config, CEOProfile


class SafetyGate:
    STOP_COLORS = ["green", "yellow", "red"]

    def __init__(self, config: Config):
        self.config = config
        self.violations = 0

    def stop_light(self) -> str:
        worst = 0
        for ceo in self.config.ceos:
            pct = self.config.budgets.warn_pct(ceo)
            if pct >= 0.95:
                worst = 2
            elif pct >= 0.85 and worst < 2:
                worst = 1
        return self.STOP_COLORS[worst]

    def check(self, ceo: CEOProfile) -> None:
        pct = self.config.budgets.warn_pct(ceo)
        if pct >= 1.0:
            self.violations += 1
            raise RuntimeError(f"BUDGET_DENIED: CEO {ceo.domain} at {pct:.0%} of budget")
        if pct >= 0.95:
            self.violations += 1

    def status(self) -> dict:
        return {
            "stop_light": self.stop_light(),
            "violations": self.violations,
            "budgets": self.config.budgets.breakdown(self.config.ceos),
        }
