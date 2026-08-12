"""System monitor — btop-style CPU/mem/disk/net/process dashboard.

Absorbs:
  - btop: real-time CPU, memory, disk, network, process tree
  - dust: disk usage visualization
  - duf: disk free info
Improves:
  - AI anomaly detection
  - Auto-remediation suggestions
"""

import os, time, json
from dataclasses import dataclass, field

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


@dataclass
class CPUInfo:
    percent: float = 0.0
    per_cpu: list = field(default_factory=list)
    count_logical: int = 0
    count_physical: int = 0
    freq_current: float = 0.0
    load_1m: float = 0.0
    load_5m: float = 0.0
    load_15m: float = 0.0
    stats: dict = field(default_factory=dict)


@dataclass
class MemoryInfo:
    total: int = 0
    available: int = 0
    percent: float = 0.0
    used: int = 0
    free: int = 0
    swap_total: int = 0
    swap_used: int = 0
    swap_percent: float = 0.0


@dataclass
class DiskInfo:
    partitions: list = field(default_factory=list)
    io_read: int = 0
    io_write: int = 0


@dataclass
class NetInfo:
    bytes_sent: int = 0
    bytes_recv: int = 0
    packets_sent: int = 0
    packets_recv: int = 0
    connections: int = 0
    interfaces: dict = field(default_factory=dict)


@dataclass
class ProcessInfo:
    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    status: str
    create_time: float
    username: str
    cmdline: str = ""


class SystemMonitor:
    """Cross-platform system monitor — btop-grade metrics."""

    def __init__(self):
        self._history = []
        self._prev_net = None
        self._net_time = time.time()

    def _check(self):
        if not HAS_PSUTIL:
            return {"error": "psutil not installed. Run: pip install psutil"}

    def cpu(self):
        self._check()
        if HAS_PSUTIL:
            return CPUInfo(
                percent=psutil.cpu_percent(interval=0.1),
                per_cpu=psutil.cpu_percent(interval=0.1, percpu=True),
                count_logical=psutil.cpu_count(logical=True),
                count_physical=psutil.cpu_count(logical=False) or 0,
                freq_current=getattr(psutil.cpu_freq(), "current", 0) or 0,
                load_1m=psutil.getloadavg()[0] if hasattr(psutil, "getloadavg") else 0,
                load_5m=psutil.getloadavg()[1] if hasattr(psutil, "getloadavg") else 0,
                load_15m=psutil.getloadavg()[2] if hasattr(psutil, "getloadavg") else 0,
                stats={"ctx_switches": psutil.cpu_stats().ctx_switches,
                       "interrupts": psutil.cpu_stats().interrupts,
                       "soft_interrupts": psutil.cpu_stats().soft_interrupts} if hasattr(psutil, "cpu_stats") else {},
            )
        return CPUInfo()

    def memory(self):
        self._check()
        if HAS_PSUTIL:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            return MemoryInfo(
                total=mem.total, available=mem.available,
                percent=mem.percent, used=mem.used, free=mem.free,
                swap_total=swap.total, swap_used=swap.used,
                swap_percent=swap.percent,
            )
        return MemoryInfo()

    def disks(self):
        self._check()
        partitions = []
        if HAS_PSUTIL:
            for part in psutil.disk_partitions():
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    partitions.append({
                        "device": part.device,
                        "mount": part.mountpoint,
                        "fstype": part.fstype,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    })
                except (PermissionError, OSError):
                    pass
            io = psutil.disk_io_counters()
            io_info = {"read_bytes": io.read_bytes, "write_bytes": io.write_bytes,
                       "read_count": io.read_count, "write_count": io.write_count} if io else {}
            return {"partitions": partitions, "io": io_info}
        return {"partitions": [], "io": {}}

    def network(self):
        self._check()
        if HAS_PSUTIL:
            net = psutil.net_io_counters()
            now = time.time()
            elapsed = now - self._net_time
            interfaces = {}
            if_addrs = psutil.net_if_addrs()
            for name, addrs in if_addrs.items():
                interfaces[name] = [{"address": a.address, "family": str(a.family)}
                                   for a in addrs[:3]]
            conns = []
            try:
                conns = psutil.net_connections(kind="inet")
            except (psutil.AccessDenied, PermissionError):
                pass
            result = NetInfo(
                bytes_sent=net.bytes_sent, bytes_recv=net.bytes_recv,
                packets_sent=net.packets_sent, packets_recv=net.packets_recv,
                connections=len(conns),
                interfaces=interfaces,
            )
            self._prev_net = net
            self._net_time = now
            return result
        return NetInfo()

    def processes(self, sort_by="cpu", limit=30):
        self._check()
        procs = []
        if HAS_PSUTIL:
            for p in psutil.process_iter(["pid", "name", "cpu_percent",
                                          "memory_percent", "status",
                                          "create_time", "username", "cmdline"]):
                try:
                    info = p.info
                    procs.append(ProcessInfo(
                        pid=info["pid"],
                        name=info["name"] or "?",
                        cpu_percent=info["cpu_percent"] or 0.0,
                        memory_percent=info["memory_percent"] or 0.0,
                        status=info["status"] or "?",
                        create_time=info["create_time"] or 0,
                        username=info["username"] or "?",
                        cmdline=" ".join(info["cmdline"] or [])[:120],
                    ))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            reverse = True
            key_map = {"cpu": "cpu_percent", "mem": "memory_percent",
                       "memory": "memory_percent", "pid": "pid",
                       "name": "name"}
            sort_key = key_map.get(sort_by, "cpu_percent")
            procs.sort(key=lambda x: getattr(x, sort_key, 0) or 0, reverse=reverse)
        return procs[:limit]

    def disk_usage(self, path="."):
        """Like dust — visualize disk usage."""
        if not HAS_PSUTIL:
            return {"error": "psutil required"}
        try:
            usage = psutil.disk_usage(os.path.abspath(path))
            return {
                "path": os.path.abspath(path),
                "total": usage.total,
                "used": usage.used,
                "free": usage.free,
                "percent": usage.percent,
            }
        except Exception as e:
            return {"error": str(e)}

    def summary(self):
        """Quick health dashboard."""
        self._check()
        cpu = self.cpu()
        mem = self.memory()
        disks = self.disks()
        net = self.network()
        procs = self.processes(limit=3)
        top_procs = [(p.name, p.cpu_percent, p.memory_percent) for p in procs]
        return {
            "cpu_percent": cpu.percent,
            "memory_percent": mem.percent,
            "memory_used_gb": round(mem.used / (1024**3), 1),
            "memory_total_gb": round(mem.total / (1024**3), 1),
            "disk_percent": disks["partitions"][0]["percent"] if disks["partitions"] else 0,
            "disk_used_gb": round(disks["partitions"][0]["used"] / (1024**3), 1) if disks["partitions"] else 0,
            "connections": net.connections,
            "processes": len(procs),
            "top_processes": top_procs,
        }

    def _format_bytes(self, b):
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if b < 1024:
                return f"{b:.1f}{unit}"
            b /= 1024
        return f"{b:.1f}PB"


sysmon = SystemMonitor()
