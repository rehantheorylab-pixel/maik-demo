import time, random
from dataclasses import dataclass, field

@dataclass
class SentinelAlert:
    level: str
    source: str
    message: str
    timestamp: float = field(default_factory=time.time)

class SentinelMonitor:
    def __init__(self):
        self._alerts: list[SentinelAlert] = []
        self._health_snapshots: list[dict] = []

    def record_health(self, metrics: dict):
        snapshot = {**metrics, "timestamp": time.time()}
        self._health_snapshots.append(snapshot)
        if len(self._health_snapshots) > 100:
            self._health_snapshots = self._health_snapshots[-100:]

    def alert(self, level: str, source: str, message: str):
        self._alerts.append(SentinelAlert(level, source, message))

    def health(self) -> dict:
        if not self._health_snapshots:
            return {"status": "unknown", "uptime": 0, "agents_active": 0, "alerts": 0}
        latest = self._health_snapshots[-1]
        recent_alerts = sum(1 for a in self._alerts if time.time() - a.timestamp < 300)
        return {
            "status": "healthy" if recent_alerts < 3 else "degraded",
            "uptime": time.time() - self._health_snapshots[0]["timestamp"],
            "agents_active": latest.get("agents_active", 0),
            "alerts": recent_alerts,
            "total_alerts": len(self._alerts),
            "cpu": latest.get("cpu", 0),
            "memory": latest.get("memory", 0),
        }

    def recent_alerts(self, limit: int = 10) -> list[dict]:
        return [{"level": a.level, "source": a.source, "message": a.message,
                 "time": time.strftime("%H:%M:%S", time.localtime(a.timestamp))}
                for a in self._alerts[-limit:]]

    def history(self, limit: int = 20) -> list[dict]:
        return [{"status": s.get("status", "?"), "agents": s.get("agents_active", 0),
                 "cpu": s.get("cpu", 0), "memory": s.get("memory", 0),
                 "time": time.strftime("%H:%M:%S", time.localtime(s["timestamp"]))}
                for s in self._health_snapshots[-limit:]]

sentinel = SentinelMonitor()
