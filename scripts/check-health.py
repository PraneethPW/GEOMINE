"""Read-only external runner check; schedule separately with your chosen alert service."""
import json
import os
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

origin = os.environ.get("GEOMINE_API_ORIGIN", "https://geomine-api-production.up.railway.app").rstrip("/")
parsed = urlparse(origin)
if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
    raise SystemExit("Set GEOMINE_API_ORIGIN to an HTTPS API origin without credentials.")
checks = []
for path in ("/api/ready", "/api/health/worker"):
    try:
        with urlopen(Request(origin + path, headers={"Accept": "application/json"}), timeout=20) as response:
            body = json.load(response)
            good = body.get("status") in ("ready", "healthy")
            checks.append({"path": path, "http_status": response.status, "ok": good})
    except HTTPError as error:
        checks.append({"path": path, "http_status": error.code, "ok": False})
    except (URLError, TimeoutError, ValueError):
        checks.append({"path": path, "ok": False, "error": "unreachable or invalid response"})
print(json.dumps({"checks": checks, "ok": all(row["ok"] for row in checks)}))
sys.exit(0 if all(row["ok"] for row in checks) else 1)
