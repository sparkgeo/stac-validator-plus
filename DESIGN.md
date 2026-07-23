# STAC Validator Plus — Design Document

**Status:** Draft for implementation · **Date:** 2026-07-23 · **Author:** John Donovan (jdonovan@sparkgeo.com)

## 1. Purpose

Combine deterministic Python STAC validation (from `../eodh-validator`) with LLM-based
semantic review (from `../claude-stac-validator`) into a single tool that produces one
categorized Markdown report for a STAC Item.

**Flow:** User provides a STAC Item → deterministic Python checks run → the Item *and*
those findings are passed to Claude to catch **other** (semantic) issues → all findings
merge into one categorized JSON result → rendered to Markdown.

The guiding principle is a clean division of labour: **let deterministic code do what it
does exactly (schema conformance, mechanical lint), and let Claude do what code cannot
(judgment, cross-field semantics, spec interpretation).**

## 2. Scope

### v1 (this document)
- **Unit of work:** a single STAC **Item**. An arbitrary Item is assumed representative
  of its collection.
- **Input:** a local file **or** a URL (via `fsspec`/`httpx`).
- **Interface:** CLI only.
- **Output:** Markdown report to stdout by default; `-o` to persist; `--json` for raw JSON.

### V2 (explicitly deferred)
- Accept a **Collection/Catalog** and validate recursively down the tree, as
  `eodh-validator` does today.
- A **FastAPI** wrapper — deferred until we understand real per-run time/cost, and because
  a proper API needs async job submission (`202` + status polling), since a run takes
  many seconds to a minute+.

## 3. Pipeline architecture

```
        ┌──────────────┐
input → │ 0. Load+Gate │ ── fatal? ──→ validation-only report (skip Claude)
        └──────┬───────┘
               │ passes
        ┌──────▼───────────────────────────┐
        │ 1. Deterministic Python checks    │   (parallel-safe, pure)
        │   • stac-validator (schema)       │
        │   • stac-check Linter (lint)      │
        │   • registered plugins (heuristic)│
        └──────┬────────────────────────────┘
               │ deterministic Findings
        ┌──────▼────────────────────────────┐
        │ 2. Claude stage (Python-driven)    │
        │   examine × N (given known         │
        │   findings, told to find OTHERS)   │
        │   → dedup (if N>1) → categorize    │
        └──────┬────────────────────────────┘
               │ Claude Findings
        ┌──────▼───────┐
        │ 3. Merge      │  deterministic + Claude → single Finding list
        └──────┬───────┘
        ┌──────▼───────┐
        │ 4. Render     │  JSON (canonical) → Jinja2 → Markdown
        └──────────────┘
```

Python is the orchestrator of the whole pipeline; the Claude sub-orchestration
(fan-out/dedup/categorize) is also driven from Python (see §8), not delegated to a
Claude Code workflow/skill.

## 4. Core data model

One normalized `Finding` type is the contract that **every** source emits into — schema
validator, linter, each plugin, and Claude. Modelled with **Pydantic** (also used to
validate Claude's JSON output).

```python
class Category(StrEnum):
    VALIDATION   = "validation"      # JSON / structural / non-STAC-specific errors (the gate)
    CORE         = "core"            # core STAC spec compliance
    BEST_PRACTICE = "best-practice"  # recommendations
    EXTENSION    = "extension"       # extension-related

class Confidence(StrEnum):
    NORMATIVE = "normative"   # grounded in spec/schema text — authoritative
    HEURISTIC = "heuristic"   # seen-in-the-wild pattern — advisory

class Reference(BaseModel):
    title: str
    href: str
    version: str | None = None      # numeric versions prefixed "v"; else "latest"

class Finding(BaseModel):
    source: str                     # "stac-validator" | "stac-check" | "<plugin>" | "claude"
    category: Category
    confidence: Confidence
    message: str                    # human-worded; field/property names in back-ticks
    json_path: str | None = None    # e.g. "properties.sar:instrument_mode"
    references: list[Reference] = []

class ValidationReport(BaseModel):
    item_id: str
    source_uri: str
    generated_on: str
    gated: bool                     # True if we stopped at the gate (Claude skipped)
    findings: list[Finding]
    usage: UsageSummary | None      # tokens/cost accumulated across Claude calls
```

- **Category** is the primary axis (Claude produces steadier output grouping by
  category than by a judged severity). No separate severity scale.
- **source + confidence** together let a heuristic plugin finding sit beside a hard schema
  failure without pretending to equal authority.

## 5. Stage 0 — Load & validation gate

`backend/loader.py` + `backend/gate.py`.

- **Load:** resolve local path or URL with `fsspec` (local, S3, http) / `httpx`; read bytes;
  parse JSON; build a `pystac.Item`.
- **Soft gate — stop before Claude only when:**
  1. input is not parseable JSON, **or**
  2. it's valid JSON but not identifiably a STAC Item (`type != "Feature"`, or
     `stac_version` missing).
- A schema-**invalid-but-parseable** Item does **not** stop — it still proceeds to Claude
  (Claude can often explain *why* it's wrong better than a raw schema error).
- On a gate stop: emit a `validation`-category report and exit early (saves credits).

## 6. Stage 1 — Deterministic Python checks

All checkers are pure and parallel-safe; each returns `list[Finding]`.

| Checker | Library | Emits | Confidence |
|---|---|---|---|
| Schema | `stac-validator` | `core` (+ `validation`) | `normative` |
| Lint | `stac-check` `Linter` | `best-practice`, some `core` | `normative` |
| Extension heuristics | in-tree plugin (§7) | `extension` | `heuristic` (may be `normative`) |

- `stac-validator` is the **authoritative** conformance verdict — the one thing the LLM is
  never trusted to do.
- `stac-check` config carries over from `eodh-validator/stac-check.config.yaml`
  (e.g. `geometry_coordinates_order: false`, `max_links`, `max_properties`).
- `extensions.json` is **shipped pre-built** as package data (`data/extensions.json`).
  Its *generation* (`get_extensions.py`, which scrapes the `stac-extensions` GitHub org)
  is a separate offline concern refreshed periodically — **never** run at validation time.

## 7. Plugin architecture

For pragmatic, seen-in-the-wild checks with tailored messages, kept out of the core.

- **Discovery: explicit in-tree registry** (decorator). Chosen deliberately — the tool is
  run by us on providers' catalogs, so when a new violation pattern emerges we add an
  in-tree plugin in minutes, with no packaging, entry-point, or third-party wait.
- **Interface — pure and idempotent:**
  ```python
  @register
  class ExtensionHeuristics:
      name = "extension-heuristics"      # → Finding.source
      def check(self, item: Item, context: PluginContext) -> list[Finding]: ...
  ```
- **`PluginContext`** carries shared, pre-loaded resources so plugins don't re-fetch:
  the raw item `dict`, the parsed `pystac.Item`, and the loaded `extensions.json` metadata.
- Plugins default to `confidence="heuristic"`; may emit `normative` when a check is
  genuinely spec-grounded.
- **First plugin:** the extension checks ported from `eodh-validator/main.py`
  (`test_item_extensions`) — maturity warnings, Item-vs-Collection scope, declared-but-unused
  extensions, used-but-undeclared prefixes, unknown prefixes, nested-property advice.
  The core **dogfoods** the public plugin interface via this plugin.
- Plugins are **toggleable by name** in config (disable noisy ones per catalog).
- Plugin findings feed both the report and the "already known" set injected into Claude.

## 8. Stage 2 — Claude (headless `claude -p`, Python-orchestrated)

### Invocation
- Runs `claude -p` as a **subprocess** (Enterprise seat login — **no API key**).
- **Ops constraint:** any host running this must have an authenticated `claude` CLI.
- `--output-format json` (session metadata wrapping a free-text `result`).
- `--allowedTools WebFetch` restricted to STAC domains: `github.com`,
  `raw.githubusercontent.com`, `stac-extensions.github.io` — keeps the doc-restricted,
  cite-your-sources behaviour from `claude-stac-validator`.
- Structured output: prompt hard for JSON, then **validate with Pydantic**, retrying the
  call a small capped number of times on parse/validation failure.
- **Output extraction (defensive):** headless Claude may wrap the JSON in prose or in a
  ```` ```json ```` fence even when told not to. Before Pydantic validation, `runner.py`
  extracts the JSON payload: take `result` from the `--output-format json` envelope, strip
  any surrounding markdown fences, and if it still isn't parseable, scan for the outermost
  balanced `{...}` block. Only then validate; a failure here counts against the retry cap.

### Orchestration (`backend/claude/orchestrator.py`)
1. **Examine × N** (`examine_runs`, default low, configurable — the main cost lever).
   Each run is given the Item **and** the deterministic findings, told *"these are already
   known; find **other** issues."* Runs bounded by `max_concurrent`.
   - **Compact injection:** the known findings are injected in a **stripped-down form —
     `message` + `json_path` only, not full `references`** — because they are repeated on
     *every* parallel examine pass and full reference lists would multiply token cost with
     no analytical benefit (Claude only needs to know *what* is already covered, not its
     citations). The full findings are still preserved for the report.
2. **Dedup** — only when `N > 1`; merge semantically equivalent issues, keep best wording,
   union references.
3. **Categorize** — group Claude's net-new findings into `core` / `best-practice` /
   `extension`.

Prompt text and JSON schemas are **lifted from `claude-stac-validator/stac-review.js`**
(`EXAMINE_PROMPT`, `DEDUP_PROMPT`, `VALIDATE_PROMPT`) into `backend/claude/prompts.py`,
adapted to (a) receive known findings and (b) emit the `Finding` shape.

### Model
- **Default: Sonnet**, passed explicitly to every call for reproducibility.
- **Opus optional** via config/flag. Rationale: moving most mechanical work into Python
  may leave Sonnet sufficient for semantics; revisit the default if not.

## 9. Stages 3–4 — Merge & render

- **Merge:** concatenate deterministic + Claude findings into one list (no re-reconciliation
  needed — Claude was told to produce only *net-new* issues).
- **JSON is canonical.** The Markdown report is a pure renderer over the `ValidationReport`.
- **Template:** evolve `claude-stac-validator/report.md.jinja2` to the 4-category layout
  (validation / core / best-practice / extension), with a summary count table and,
  per finding, its `source`, `confidence`, and reference links.

## 10. CLI surface

`curl`-style: stdout by default, `-o` to persist.

```
stac-validator-plus <ITEM>            # file path or URL
  -o, --output PATH                   # write report to file/dir (auto-name in a dir); default stdout
      --json                          # also emit the raw canonical JSON
      --config PATH                   # config file (default: ./stac-validator-plus.toml)
      --model {sonnet|opus|<id>}      # override model
      --examine-runs N                # fan-out count
      --max-turns N                   # per claude -p call
      --timeout SECONDS               # per subprocess
      --max-concurrent N              # concurrent claude subprocesses
      --no-plugin NAME / --no-check NAME
      --wall-clock-budget SECONDS     # abort run (best-effort)
      --token-budget N                # abort between stages when exceeded (best-effort)
```

Built with `rich-click` (existing `cli` extra). `api.py` stays as a minimal stub for V2.

## 11. Configuration

- **File:** `stac-validator-plus.toml` (CWD or `--config`), parsed with stdlib `tomllib`
  (no YAML dep). CLI flags override file values per run.
- **Settings model** (Pydantic): `model`, `examine_runs`, `max_turns`,
  `subprocess_timeout`, `max_concurrent`, `wall_clock_budget`, `token_budget`,
  `enabled_plugins`, `enabled_checkers`, `webfetch_allowlist`.

## 12. Credit / time guardrails

- `examine_runs` — primary cost lever (dial to 1 for cheap, up for thorough).
- `--max-turns` — caps each agentic loop / runaway doc-fetching.
- Per-subprocess **timeout** — kill hung calls.
- `max_concurrent` — cap simultaneous subprocesses.
- **Wall-clock budget** — overall timer; abort remaining stages.
- **Token/cost budget** — *best-effort*: not enforceable within a single `claude -p` call,
  but the orchestrator accumulates usage from each `--output-format json` response and
  aborts **before the next stage** once exceeded. Honest caveat stated to users.
- Fallback per author: manually tune prompts to balance cost vs detail.

## 13. Proposed module layout

```
src/stac_validator_plus/
  __init__.py  __main__.py
  cli.py                     # rich-click entrypoint
  api.py                     # minimal FastAPI stub (V2)
  config.py                  # tomllib load + flag override → Settings
  models.py                  # Finding, Reference, ValidationReport, enums (Pydantic)
  pipeline.py                # orchestrates gate → checks → claude → merge → render
  backend/
    loader.py                # fsspec/httpx load + JSON parse + pystac.Item
    gate.py                  # Stage 0 soft gate
    checks/
      schema.py              # stac-validator wrapper → Findings
      lint.py                # stac-check Linter wrapper → Findings
    plugins/
      __init__.py            # @register registry, PluginContext, discovery
      extensions.py          # ported extension heuristics (first plugin)
    claude/
      runner.py              # subprocess claude -p, json output, timeout, retry, usage
      orchestrator.py        # examine fan-out → dedup → categorize
      prompts.py             # prompt templates lifted from stac-review.js
  report/
    render.py                # Jinja2
    templates/report.md.jinja2
  data/
    extensions.json          # pre-built package data
```

## 14. Dependencies

Add to `pyproject.toml`: `stac-validator`, `stac-check`, `pystac`, `pydantic`.
Already present: `pystac-client`, `jinja2`, `httpx`, `fsspec`, `loguru`; `rich-click`
(cli extra). Dev: `pytest`, `ruff` (present).

## 15. Testing

- **Pure units:** gate, each checker, each plugin — deterministic, no network, no Claude.
- **Claude stage:** mock the `runner.py` subprocess boundary; assert orchestration
  (fan-out count, dedup, categorize) and Pydantic-validation/retry behaviour on
  malformed model output.
- **Fixtures:** reuse example Items from `claude-stac-validator/examples/`.
- **Render:** golden-file test of Markdown against a known `ValidationReport`.

## 16. Security notes

- **Do not commit secrets.** `eodh-validator/main.py` currently contains a hardcoded bearer
  token and DroneDB admin credentials — these must be scrubbed and rotated (tracked
  separately; not carried into this project). This tool takes auth for remote fetches via
  env/config only.
- WebFetch is restricted to the STAC documentation domain allowlist.
- Plugins execute in-process — keep them in-tree and reviewed (a reason the registry is
  explicit, not a directory scan of arbitrary files).

## 17. Open questions / future

- V2 recursion strategy (sampling one Item per collection vs all).
- V2 async FastAPI job model once per-run time/cost is measured.
- Whether Sonnet's semantic recall is sufficient or Opus should become the default.
- Periodic refresh cadence and CI for the shipped `extensions.json`.
```
