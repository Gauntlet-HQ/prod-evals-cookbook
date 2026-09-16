#!/usr/bin/env python3
"""
Record agent traces for error analysis.

Runs each query in queries.yaml through Ask Acme and writes one JSON trace per
query into traces/. Traces are written in the same shape as the Stage 3 replay
fixtures, so anything recorded there can be dropped into traces/ and reviewed
with the same UI.

Usage:
    uv run python error_analysis/generate_traces.py
    uv run python error_analysis/generate_traces.py --only ea-004 ea-007
    uv run python error_analysis/generate_traces.py --force   # re-record existing
"""

import argparse
import json
import sys
import traceback
from datetime import datetime
from pathlib import Path

import yaml

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parent / "setup_agent"))

from orchestrator import ask_acme_with_trace  # noqa: E402

TRACES_DIR = HERE / "traces"


def normalize_tool_calls(raw: list[dict]) -> list[dict]:
    """Accept either the orchestrator shape or the Stage 3 fixture shape."""
    out = []
    for tc in raw:
        out.append(
            {
                "tool_name": tc.get("tool_name") or tc.get("tool", ""),
                "arguments": tc.get("arguments") or tc.get("args", {}),
                "result": tc.get("result", ""),
            }
        )
    return out


def record(entry: dict) -> dict:
    """Run one query and build a trace record."""
    query = entry["query"]
    started = datetime.now()

    try:
        trace = ask_acme_with_trace(query)
        response = trace.get("response", "")
        tool_calls = normalize_tool_calls(trace.get("tool_calls", []))
        error = None
    except Exception:
        response = ""
        tool_calls = []
        error = traceback.format_exc()

    elapsed = (datetime.now() - started).total_seconds()

    return {
        "session_id": entry["id"],
        "query": query,
        "probe": entry.get("probe", ""),
        "response": response,
        "tool_calls": tool_calls,
        "retrieved_sources": [],
        "source_contents": [],
        "timestamp": started.isoformat(timespec="seconds"),
        "duration_seconds": round(elapsed, 2),
        "error": error,
        "annotations": {},
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--only", nargs="*", metavar="ID", help="record only these query ids")
    ap.add_argument("--force", action="store_true", help="re-record traces that already exist")
    args = ap.parse_args()

    entries = yaml.safe_load((HERE / "queries.yaml").read_text())["queries"]
    if args.only:
        wanted = set(args.only)
        entries = [e for e in entries if e["id"] in wanted]
        missing = wanted - {e["id"] for e in entries}
        if missing:
            print(f"No such query id: {', '.join(sorted(missing))}")
            return 1

    TRACES_DIR.mkdir(exist_ok=True)

    recorded = skipped = failed = 0
    for i, entry in enumerate(entries, 1):
        path = TRACES_DIR / f"{entry['id']}.json"
        if path.exists() and not args.force:
            print(f"[{i}/{len(entries)}] {entry['id']}  skipped (exists, use --force)")
            skipped += 1
            continue

        print(f"[{i}/{len(entries)}] {entry['id']}  {entry['query'][:58]}...", flush=True)
        rec = record(entry)
        path.write_text(json.dumps(rec, indent=2) + "\n")

        if rec["error"]:
            print(f"          agent raised — recorded anyway ({path.name})")
            failed += 1
        else:
            tools = ", ".join(tc["tool_name"] for tc in rec["tool_calls"]) or "none"
            print(f"          {rec['duration_seconds']}s  tools: {tools}")
            recorded += 1

    print(f"\nRecorded {recorded}, skipped {skipped}, agent errors {failed}")
    print(f"Traces in {TRACES_DIR.relative_to(HERE.parent)}/")
    print("\nNext: uv run python error_analysis/review.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
