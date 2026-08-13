"""Debug why verifier grades are UNVERIFIED."""
import os
import sys
import logging

os.environ.setdefault("MAIK_DATA_DIR", "/tmp/maikdebugv")
logging.getLogger("litellm").setLevel(logging.ERROR)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from maik_kernel.live_execution import LiveExecution

live = LiveExecution()
print("ladder:", [e.name for e in live.ladder.entries])
try:
    v = live.verify("What is 7*8?", "56")
    print("RESULT:", v)
except Exception as e:  # noqa: BLE001
    print("EXCEPTION:", repr(e))
