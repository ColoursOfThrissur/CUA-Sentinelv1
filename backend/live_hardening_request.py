"""Submit one Blender V2 build to an already-running local API and persist evidence.

This is intentionally a harness, not a pipeline shortcut: it exercises the same
``POST /api/blender/build`` route used by the application and leaves a durable
response or traceback when the caller disconnects.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path, help="JSON request body")
    parser.add_argument("evidence_dir", type=Path, help="Directory for durable result evidence")
    parser.add_argument("--url", default="http://127.0.0.1:8000/api/blender/build")
    args = parser.parse_args()

    body = args.request.read_bytes()
    args.evidence_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    record_path = args.evidence_dir / f"api_build_{stamp}.json"
    record = {"started_at": datetime.now(timezone.utc).isoformat(), "url": args.url}

    try:
        request = urllib.request.Request(
            args.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=3600) as response:
            response_body = response.read().decode("utf-8", errors="replace")
            record.update(
                {
                    "http_status": response.status,
                    "response": json.loads(response_body),
                    "finished_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    except urllib.error.HTTPError as exc:
        record.update(
            {
                "http_status": exc.code,
                "response_text": exc.read().decode("utf-8", errors="replace"),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    except Exception:
        record.update(
            {
                "exception": traceback.format_exc(),
                "finished_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    record_path.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(record_path)
    return 0 if record.get("http_status") == 200 else 1


if __name__ == "__main__":
    sys.exit(main())
