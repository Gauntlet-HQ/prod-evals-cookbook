# Error Analysis

> Not a stage. A workbench for reading traces one at a time and writing down what went wrong.

The eval stages tell you **whether** something broke. Error analysis tells you **what kind**
of thing breaks — which is what you need before you can decide what to fix. It is manual on
purpose: you read the input and output, and you write the error down in your own words.

```bash
uv run python error_analysis/generate_traces.py   # 1. record traces (~2 min, costs API calls)
uv run python error_analysis/review.py            # 2. click through and annotate
uv run python error_analysis/export.py            # 3. export what you reviewed
```

All three run from the repo root.

## How it works

| File | Purpose |
|------|---------|
| `queries.yaml` | The review set. Each query has a `probe` saying which weakness it aims at |
| `generate_traces.py` | Runs each query through Ask Acme, writes one JSON per trace to `traces/` |
| `review.py` | Local server (stdlib only, no deps) on `:8899` serving the UI |
| `app.html` | The UI — one trace at a time, verdict + notes |
| `export.py` | Writes reviewed traces out as CSV, JSON or Markdown |
| `annotations.json` | Your work. The only file here you cannot regenerate — **commit it** |

Traces use the same shape as the Stage 3 replay fixtures, so you can drop anything from
`stage_3_replay_harnesses/fixtures/` into `traces/` and review it with the same UI.

## The UI

Left column lists every trace with a status dot — grey unreviewed, red error, green fine.
The main panel shows the query, the tool calls with their arguments, and the full response.

Annotations save to `annotations.json` as you type, roughly a third of a second after you
stop. There is no save button and nothing to submit.

| Key | Does |
|-----|------|
| `j` / `k` | Next / previous trace |
| `e` | Mark as error |
| `o` | Mark as looks right |
| `n` | Jump to the notes box |
| `Esc` | Leave the notes box |

### Exporting

The header has a scope picker (**Reviewed** / **Errors only**) and four buttons: **CSV**,
**JSON**, **MD** download a file; **Copy** puts markdown on your clipboard. Every export
carries the id, query, probe, verdict, note, tools, duration and full response.

The same thing from the command line:

```bash
uv run python error_analysis/export.py                        # CSV to stdout
uv run python error_analysis/export.py --format md -o out.md
uv run python error_analysis/export.py --scope all            # include unreviewed
```

## How to actually do the analysis

Go through every trace and describe what went wrong in plain language. Do not try to
categorise as you go — naming the failure types before you have read the data just
recovers the categories you already expected.

Write concretely: *"claimed 0 refunds for Q4 2025, but the table has no 2025 rows at all —
that is an empty result reported as a measured zero."* Concrete beats tidy.

Categorising comes later, as a separate pass over your own notes, once you can see the
whole set. Export the reviewed rows and do that pass wherever you prefer.

## Turning findings into evals

An error you saw more than once is a candidate for a permanent check:

- Recurring, easy to assert → a Stage 1 golden set case
- A whole area is weak → Stage 2 labeled scenarios for coverage
- Needs the exact same inputs every run → a Stage 3 replay fixture
- Quality judgment, not pass/fail → a Stage 4 rubric dimension

That is the loop: analyze errors, promote the repeatable ones into evals, re-run, look again.

## Notes

- `queries.yaml` is deliberately adversarial — false premises, unanswerable questions,
  missing documents. A clean run means the probes were too easy, not that the agent is
  perfect. Add real production questions as you collect them.
- Re-recording is skipped for traces that already exist; pass `--force` to overwrite,
  or `--only ea-004 ea-007` to redo specific ones.
- Clearing a trace's verdict and note removes it from `annotations.json`.
