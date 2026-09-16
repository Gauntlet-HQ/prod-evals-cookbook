#!/usr/bin/env python3
"""
Local error-analysis review UI.

Serves a single page that lets you click through recorded traces, read the
input and output, and annotate each one. Annotations are written straight to
annotations.json in this folder — no database, no dependencies, stdlib only.

Usage:
    uv run python error_analysis/review.py
    uv run python error_analysis/review.py --port 8900 --no-open
"""

import argparse
import json
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).parent
TRACES_DIR = HERE / "traces"
ANNOTATIONS = HERE / "annotations.json"
APP_HTML = HERE / "app.html"

_lock = threading.Lock()


def load_traces() -> list[dict]:
    """Read every trace file, newest-first by id order on disk."""
    traces = []
    for path in sorted(TRACES_DIR.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            print(f"  ! skipping {path.name}: {exc}")
            continue
        # Tolerate both the orchestrator shape and the Stage 3 fixture shape.
        tool_calls = [
            {
                "tool_name": tc.get("tool_name") or tc.get("tool", ""),
                "arguments": tc.get("arguments") or tc.get("args", {}),
            }
            for tc in data.get("tool_calls", [])
        ]
        traces.append(
            {
                "id": data.get("session_id") or path.stem,
                "query": data.get("query", ""),
                "probe": data.get("probe", ""),
                "response": data.get("response", ""),
                "tool_calls": tool_calls,
                "retrieved_sources": data.get("retrieved_sources", []),
                "duration_seconds": data.get("duration_seconds"),
                "timestamp": data.get("timestamp", ""),
                "error": data.get("error"),
            }
        )
    return traces


def load_annotations() -> dict:
    if not ANNOTATIONS.exists():
        return {}
    try:
        data = json.loads(ANNOTATIONS.read_text())
    except json.JSONDecodeError:
        print("  ! annotations.json is not valid JSON; starting from empty")
        return {}
    # Older files carried a failure_modes list; drop it on read so it disappears
    # from the file on the next save.
    for record in data.values():
        if isinstance(record, dict):
            record.pop("failure_modes", None)
    return data


def save_annotations(data: dict) -> None:
    """Atomic write, so an interrupted save cannot truncate your work."""
    tmp = ANNOTATIONS.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    tmp.replace(ANNOTATIONS)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):  # quieter console
        pass

    def _send(self, code: int, body: bytes, ctype: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        self._send(code, json.dumps(payload).encode(), "application/json; charset=utf-8")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            if not APP_HTML.exists():
                self._send(500, b"app.html is missing", "text/plain; charset=utf-8")
                return
            self._send(200, APP_HTML.read_bytes(), "text/html; charset=utf-8")
        elif self.path == "/api/data":
            with _lock:
                self._json(200, {"traces": load_traces(), "annotations": load_annotations()})
        else:
            self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_POST(self):
        if self.path != "/api/annotate":
            self._send(404, b"not found", "text/plain; charset=utf-8")
            return

        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            self._json(400, {"error": "empty body"})
            return

        try:
            payload = json.loads(self.rfile.read(length))
        except json.JSONDecodeError as exc:
            self._json(400, {"error": f"bad JSON: {exc}"})
            return

        trace_id = payload.get("id")
        if not trace_id:
            self._json(400, {"error": "missing id"})
            return

        record = {
            "verdict": payload.get("verdict", ""),
            "note": payload.get("note", ""),
            "updated": payload.get("updated", ""),
        }

        with _lock:
            data = load_annotations()
            if record["verdict"] or record["note"].strip():
                data[trace_id] = record
            else:
                data.pop(trace_id, None)  # cleared annotation removes the row
            save_annotations(data)
            reviewed = len(data)

        self._json(200, {"ok": True, "reviewed": reviewed})


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--no-open", action="store_true", help="do not open a browser")
    args = ap.parse_args()

    if not TRACES_DIR.exists() or not any(TRACES_DIR.glob("*.json")):
        print("No traces found in error_analysis/traces/.")
        print("Record some first:  uv run python error_analysis/generate_traces.py")
        return 1

    traces = load_traces()
    reviewed = len(load_annotations())
    url = f"http://localhost:{args.port}/"

    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        print(f"Could not bind port {args.port}: {exc}")
        print(f"Try another one:  uv run python error_analysis/review.py --port {args.port + 1}")
        return 1

    print(f"{len(traces)} traces, {reviewed} already annotated")
    print(f"Review UI: {url}")
    print("Annotations save to error_analysis/annotations.json as you type.")
    print("Ctrl+C to stop.")

    if not args.no_open:
        threading.Timer(0.5, webbrowser.open, args=(url,)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
