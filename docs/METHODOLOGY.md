# AIRA Scanner Methodology

This document explains what AIRA measures, how it measures it, and what claims the scanner should and should not make.

## 1. Research Posture

AIRA is a measurement tool for fail-soft behavior in software systems.

It is not:

- a formal verifier
- a complete security audit
- a proof of AI authorship
- a substitute for runtime testing or human review

Its purpose is narrower:

- identify patterns that can conceal failure
- make those patterns legible across repos and runs
- support empirical comparison, especially in AI-assisted codebases

## 2. The Core Unit Of Analysis

AIRA evaluates code against 15 named checks.

Those checks are intended to capture failure-truthfulness patterns such as:

- success being returned after critical operations fail
- silent degradation instead of explicit failure
- broad exception suppression
- bypass or override paths that weaken assurance
- ambiguous return contracts that blur failure and absence

Two checks are intentionally reserved for human review:

- `C07` Parallel Logic Drift
- `C12` Source-to-Output Lineage

These remain `UNKNOWN` in automated output.

## 3. Scan Modes

AIRA supports three scan modes.

### Static

Deterministic built-in analysis only.

This is the canonical baseline for the project because it is:

- inspectable
- reproducible
- available without a provider

### LLM

Provider-assisted analysis only.

This is useful for exploratory comparison and targeted review, but it is not treated as inherently more trustworthy than deterministic scanning.

### Hybrid

Merges static and LLM findings.

This allows provider-assisted signal to supplement the deterministic baseline while preserving deterministic coverage when the LLM path fails or smooths over issues.

## 4. Language Support

Current supported source types:

- Python: `.py`
- JavaScript: `.js`, `.mjs`, `.cjs`
- TypeScript: `.ts`
- JSX/TSX: `.jsx`, `.tsx`

The static engine skips common build, virtualenv, and dependency directories.

## 5. Deterministic Engine

The deterministic engine is the methodological backbone of AIRA.

### Python

Python analysis is parser-backed using Python’s AST and rule-specific structural checks.

### JavaScript And TypeScript

JavaScript-family analysis uses parser-backed logic when `esprima` is available and falls back to lighter lexical logic when it is not.

The separate error-inventory and graph layers use pinned Tree-sitter JavaScript, TypeScript, JSX, and TSX grammars. Tree-sitter recovery nodes are preserved as parser diagnostics; lexical recovery remains explicitly partial.

### Test Coverage Asymmetry

`C14` is evaluated through dedicated test-surface analysis rather than only per-file lexical checks.

## 6. LLM-Assisted Analysis

LLM-assisted scans use a normalized JSON audit contract.

Important constraints:

- the scanner requests structured output only
- automated LLM output is normalized before use
- `C07` and `C12` are forcibly kept `UNKNOWN`
- the project treats LLM output as optional augmentation, not ground truth

Provider support is deliberately flexible:

- local OpenAI-compatible endpoints
- Ollama
- NVIDIA NIM
- Groq
- OpenRouter

For canonical research studies, methodology must be locked before collection:

- the deterministic CLI baseline is `--engine static`, which uses no LLM model; record the model as `none` / not applicable
- the first-study model-assisted comparison is pinned to `--provider groq --model llama-3.1-8b-instant` when reproduced through the CLI
- any other LLM-assisted study must pin the provider and exact provider model identifier with CLI arguments or environment variables
- do not use `--provider auto`, floating model aliases such as `latest` or `current`, or an unset provider model for canonical records
- capture the scanner version, ruleset version, scoring version, sample manifest, repository ref, resolved commit SHA, scan mode, provider, model, provider health output, and per-sample scan JSON alongside the results

The web app has its own routed provider surface and health checks. The CLI has a local-first provider order and explicit health/probe commands.

## 7. Fallback Semantics

Fallback behavior is explicit because it affects research quality.

### Web App

Current order:

1. configured cloud or Ollama route
2. deterministic server-side static scan
3. browser-only heuristics

The browser-only heuristic path is intentionally treated as the weakest form of result and should be interpreted as triage output.

### CLI

The CLI remains useful with no provider configured at all because the static engine is first-class.

If hybrid mode is requested and the LLM path fails, the scanner records that it fell back to static-only behavior.

Browser-only fallback records partial completeness and cannot promote an unevaluated check to `PASS`.

## 8. Result Semantics

Each automated check resolves to one of:

- `PASS`
- `FAIL`
- `UNKNOWN`

`UNKNOWN` does not mean “safe.” It means the scanner cannot responsibly automate the conclusion.

Each finding also includes:

- check id
- check name
- severity
- file
- line
- description
- optional snippet

For reproducible studies, findings also include deterministic location metadata:

- stable finding, semantic, and location fingerprints
- a normalized boundary type, such as exception handler, fallback branch, environment gate, return contract, async task, or retry/write boundary
- enclosing function/class context where available
- normalized line position within the file
- parser or heuristic provenance for the context metadata

This metadata supports model-vs-static comparison without sending source code to the aggregate research backend. Single-run comparisons can use `aira compare static.json model.json`; repeated location-aware studies should use `aira study run` to preserve raw per-sample JSONL and `aira study compare` to aggregate misses by model, check, boundary type, and sample.

Comparison version `aira-comparison-v2` uses one-to-one finding matches. A semantic fingerprint is never sufficient by itself: both findings must first identify the same canonical repository-relative artifact. Absolute paths, parent traversal, and basename-only equivalence are not accepted as location identity.

Scan completeness is reported separately from finding counts. `files_discovered` is the in-scope manifest, while `files_analyzed`, `files_partial`, `files_failed`, and `files_omitted` describe what the selected engine actually evaluated. `files_scanned` means fully analyzed artifacts. A rule can be `PASS` only when all in-scope artifacts were fully analyzed with sufficient capability; parse failures, unsupported parser paths, truncation, and omissions preserve `UNKNOWN` for unproven rules.

## 9. Non-Scoring Error Inventory And Graph

`aira inventory-errors` records observations rather than defects. `aira-error-signal-v1` covers handlers, raises/throws, returns and status codes, logs, retries, fallbacks, async ownership, cleanup, and side effects. Every signal includes a canonical artifact, exact region, symbol, structural path, parser health, confidence, and evidence hash. Signal identity excludes line numbers so whitespace and line shifts do not manufacture a new semantic event.

`aira error-graph` projects those signals into `aira-error-graph-v1`. It adds evidence-backed edges for containment, sequence, catching, propagation, wrapping/cause erasure, status returns, logging, retry, fallback, side-effect ordering, async relationships, and conservatively resolved calls. Unresolved or ambiguous calls remain explicit graph nodes.

Neither layer changes canonical check status, FTI-v1, finding thresholds, or research submission claims. Pattern candidates remain a later, separately calibrated phase.

## 10. Severity Semantics

Severity is heuristic and should be interpreted as prioritization guidance, not mathematical truth.

General intent:

- `HIGH`: clear concealment of failure or weakening of system guarantees
- `MEDIUM`: materially risky ambiguity or structural weakness that needs review
- `LOW`: softer signal, often distributed fallback or best-effort behavior that may still be acceptable in context

## 11. Research Submission Posture

The scanner supports aggregate-only research submission.

What is sent:

- check statuses
- total findings
- overall severity totals
- per-check finding counts
- per-check severity matrices
- scan mode / provider / model metadata
- CI metadata when available

What is not sent:

- raw source code
- snippets
- file paths from findings
- raw file contents

Preferred backends:

- Supabase for hosted collection
- JSONL for local and CI collection

Airtable remains supported only as a compatibility fallback.

For Supabase schema v2, AIRA treats the submission stream as append-only and derives a normalized per-check table from the aggregate payload. The server recomputes FTI-v1 and risk bands from `checks_json` rather than trusting caller-supplied scores.

## 12. Claims AIRA Should Not Make

AIRA should not be used to claim:

- that a repo is “safe” because it passed
- that AI definitely wrote the flagged code
- that every flagged pattern is a defect
- that every absence of a finding implies strong assurance

The right language is:

- observed
- measured
- suggests
- may indicate

not:

- proves
- guarantees
- all AI-generated code behaves this way

## 13. Known Limitations

The scanner still has important limitations.

- Cross-file call resolution is intentionally conservative; dynamic, external, and ambiguous calls remain unresolved.
- The graph records behavior but does not yet classify cross-location relationships as defects or candidates.
- Browser-only heuristics are intentionally lower-confidence than deterministic server-side analysis.
- LLM-assisted repo-scale audits can become optimistic or lossy when prompts are truncated.
- `C07` and `C12` still require human review by design.
- Benchmark datasets and formal calibration studies are still in progress.

## 14. Practical Interpretation

The safest way to use AIRA today is:

1. treat static output as the baseline measurement
2. use hybrid or LLM modes as comparison and augmentation
3. review `HIGH` findings first
4. do not suppress the `UNKNOWN` posture on human-review checks
5. preserve raw JSON outputs when comparing engines or models
6. use JSONL study rows for multi-sample or multi-model boundary analysis
7. preserve provenance about which engine produced the result

That posture keeps AIRA useful without letting the tool overclaim what it knows.
