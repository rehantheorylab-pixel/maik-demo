import json
import subprocess
import time
import hashlib
from dataclasses import dataclass, field
from typing import Optional

class ExpertBridge:
    def __init__(self):
        self._sessions: dict[str, dict] = {}
        self._expert_registry: dict[str, dict] = {}

    def register_expert(self, name: str, command: str, args: Optional[list[str]] = None,
                        input_type: str = "json", output_type: str = "json"):
        self._expert_registry[name] = {
            "command": command, "args": args or [],
            "input_type": input_type, "output_type": output_type,
        }

    def call_expert(self, name: str, input_data: dict, timeout: int = 10) -> dict:
        expert = self._expert_registry.get(name)
        if not expert:
            return {"error": f"Expert '{name}' not found", "status": "error"}
        session_id = hashlib.md5(f"{time.time()}:{name}".encode()).hexdigest()[:8]
        self._sessions[session_id] = {
            "expert": name, "started_at": time.time(), "status": "running",
        }
        try:
            input_str = json.dumps(input_data)
            result = subprocess.run(
                [expert["command"]] + expert["args"],
                input=input_str, capture_output=True, text=True,
                timeout=timeout,
            )
            output = json.loads(result.stdout) if result.stdout else {"stdout": result.stdout, "stderr": result.stderr}
            self._sessions[session_id]["status"] = "completed"
            self._sessions[session_id]["output"] = str(output)[:200]
            return {"output": output, "status": "completed", "session_id": session_id, "return_code": result.returncode}
        except subprocess.TimeoutExpired:
            self._sessions[session_id]["status"] = "timeout"
            return {"error": "timeout", "status": "timeout", "session_id": session_id}
        except FileNotFoundError:
            return {"error": f"Command '{expert['command']}' not found", "status": "error"}
        except Exception as e:
            return {"error": str(e), "status": "error"}

    def session_status(self, session_id: str) -> Optional[dict]:
        return self._sessions.get(session_id)

    def stats(self) -> dict:
        return {
            "sessions": len(self._sessions),
            "experts": len(self._expert_registry),
            "completed": sum(1 for s in self._sessions.values() if s["status"] == "completed"),
            "running": sum(1 for s in self._sessions.values() if s["status"] == "running"),
        }

expert_bridge = ExpertBridge()
expert_bridge.register_expert("code_expert", "python", ["-c", "import sys,json;print(json.dumps({'analyzed':True}))"])
expert_bridge.register_expert("math_expert", "python", ["-c", "import sys,json;print(json.dumps({'evaluated':True}))"])
