#!/usr/bin/env python3
"""
Export reviewed traces.

Joins traces/ with annotations.json and writes every reviewed trace out as CSV,
JSON or Markdown. The UI has the same export built in; this is the version you
can run in a script or pipe somewhere.

Usage:
    uv run python error_analysis/export.py                       # CSV to stdout
    uv run python error_analysis/export.py --format md -o out.md
    uv run python error_analysis/export.py --scope errors --format json
    uv run python error_analysis/export.py --scope all           # include unreviewed
"""

import argparse
import csv
import io
import json
import sys
from pathlib import Path

HERE = Path(__file__).parent
COLUMNS = ["id", "query", "probe", "verdict", "note", "tools", "duration_seconds", "response"]


def load_rows(scope: str) -> list[dict]:
    ann_path = HERE / "annotations.json"
    ann = json.loads(ann_path.read_text()) if ann_path.exists() else {}

    rows = []
    for path in sorted((HERE / "traces").glob("*.json")):
        d = json.loads(path.read_text())
        tid = d.get("session_id", path.stem)
        a = ann.get(tid, {})
        reviewed = bool(a.get("verdict") or (a.get("note") or "").strip())

        if scope == "reviewed" and not reviewed:
            continue
        if scope == "errors" and a.get("verdict") != "error":
            continue

        tools = [tc.get("tool_name") or tc.get("tool", "") for tc in d.get("tool_calls", [])]
        rows.append(
            {
                "id": tid,
                "query": d.get("query", ""),
                "probe": d.get("probe", ""),
                "verdict": a.get("verdict", ""),
                "note": a.get("note", ""),
                "tools": " ".join(tools),
                "duration_seconds": d.get("duration_seconds", ""),
                "response": d.get("response", ""),
            }
        )
    return rows


def as_csv(rows: list[dict]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()


def as_markdown(rows: list[dict], total: int) -> str:
    out = ["# Error analysis", "", f"{len(rows)} of {total} traces", ""]
    for r in rows:
        out.append(f"## {r['id']} — {r['query']}")
        out.append("")
        out.append(
            f"**Verdict:** {r['verdict'] or '—'} | "
            f"**Tools:** {r['tools'] or 'none'} | **{r['duration_seconds']}s**"
        )
        out.append("")
        if r["probe"]:
            out.append(f"_Probe: {r['probe']}_")
            out.append("")
        out.append(f"**Note:** {r['note'] or '_none_'}")
        out.append("")
        out.append("<details><summary>Response</summary>")
        out.append("")
        out.append("```")
        out.append(r["response"])
        out.append("```")
        out.append("</details>")
        out.append("")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--format", choices=["csv", "json", "md"], default="csv")
    ap.add_argument("--scope", choices=["reviewed", "errors", "all"], default="reviewed")
    ap.add_argument("-o", "--out", help="write to a file instead of stdout")
    args = ap.parse_args()

    if not (HERE / "traces").exists():
        print("No traces. Run generate_traces.py first.", file=sys.stderr)
        return 1

    rows = load_rows(args.scope)
    total = len(list((HERE / "traces").glob("*.json")))

    if not rows:
        print(f"Nothing to export for scope={args.scope}.", file=sys.stderr)
        return 1

    if args.format == "csv":
        text = as_csv(rows)
    elif args.format == "json":
        text = json.dumps(rows, indent=2) + "\n"
    else:
        text = as_markdown(rows, total)

    if args.out:
        Path(args.out).write_text(text)
        print(f"Wrote {len(rows)} rows to {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
