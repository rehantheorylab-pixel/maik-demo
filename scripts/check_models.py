"""Check which model ids are available on the sandbox LLM proxy."""
import os
import urllib.request
import urllib.error
import json

base = os.environ.get("OPENAI_API_BASE", "").rstrip("/")
key = os.environ.get("OPENAI_API_KEY", "")
url = f"{base}/models"
req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
try:
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode())
    ids = [m["id"] for m in data.get("data", [])]
    print("AVAILABLE MODELS:", ids)
except urllib.error.HTTPError as e:
    print("HTTP ERROR", e.code, e.read().decode()[:500])
except Exception as e:  # noqa: BLE001
    print("ERROR", repr(e))
