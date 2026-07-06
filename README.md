# AIRA Scanner

**AI-Induced Risk Audit (AIRA)**
Detecting fail-soft patterns in modern software systems

---

## Overview

AIRA Scanner is a research tool for detecting fail-soft patterns in software systems, especially those developed with significant AI assistance.

These patterns include cases where systems:

* return success despite incomplete or failed operations
* degrade silently instead of failing explicitly
* obscure true system state under error conditions
* preserve the appearance of function while weakening actual guarantees

These behaviors are not always treated as conventional defects. But in reliability, governance, audit, and safety-sensitive systems, they directly affect trustworthiness.

---

## About

AIRA is a research initiative developed by **BDB Labs**.
Project homepage: **https://aira.bageltech.net**

The scanner exists to help identify a class of software risks that are often missed by traditional linting, style enforcement, and happy-path testing.

---

## Why this exists

Traditional software validation asks:

> “Does the system work?”

AIRA asks:

> **“Does the system tell the truth when it fails?”**

AIRA is designed to detect patterns where systems continue, degrade, or signal success in ways that may conceal broken guarantees.

---

## Research Direction

AIRA is motivated by the hypothesis that modern codebases—particularly those developed with significant AI assistance—may exhibit recurring fail-soft patterns such as:

* broad exception suppression
* distributed fallback logic
* ambiguous return contracts
* optimistic success signaling
* silent degradation of guarantees

This tool is intended to **measure and surface these patterns**, not to presume universal cause or make claims beyond the available evidence.

---

## What AIRA looks for

AIRA currently focuses on patterns such as:

* success integrity violations
* audit and evidence integrity gaps
* broad exception suppression
* distributed fallback and degraded execution
* bypass and override paths
* ambiguous return contracts
* parallel logic drift
* unsupervised background tasks
* environment-dependent safety drift
* startup integrity weaknesses
* deterministic reasoning drift
* source-to-output lineage gaps
* confidence misrepresentation
* failure-path test asymmetry
* retry and idempotency assumption drift

---

## Status

Early-stage research tool.
Initial scanner and rule set are live.
Empirical datasets and expanded detection rules are in progress.

## Install

Via Homebrew:

```bash
brew install BDB-Labs/aira-scanner/aira
```

Or from source:

```bash
git clone https://github.com/BDB-Labs/aira-scanner.git
pip install ./aira-scanner/CLI
```

## Documentation

For readers who need more than the landing-page overview:

- [CHANGELOG.md](./CHANGELOG.md) tracks major milestones
- [docs/EVOLUTION.md](./docs/EVOLUTION.md) explains how the scanner evolved from the original web prototype to the current research tool
- [docs/METHODOLOGY.md](./docs/METHODOLOGY.md) defines what AIRA measures, how the scan modes work, and what claims the tool should not make
- [docs/AIRA_CHECKS.md](./docs/AIRA_CHECKS.md) documents the 15 checks in practical terms
- [docs/PUBLIC_DATA_COLLECTION.md](./docs/PUBLIC_DATA_COLLECTION.md) documents curated public-repo collection for canonical research datasets
- [CLI/README.md](./CLI/README.md) documents the local, CI, and Homebrew scanner surface
- [SUPABASE_SCHEMA.sql](./SUPABASE_SCHEMA.sql), [SUPABASE_MIGRATION_V2.sql](./SUPABASE_MIGRATION_V2.sql), and [AIRTABLE_SCHEMA.md](./AIRTABLE_SCHEMA.md) document the current research sink contracts

---

## Runtime Notes

The scanner currently supports:

* `Auto` mode: routes through configured providers in order (Ollama → NVIDIA NIM → Groq → OpenRouter)
* deterministic static scanning through `/api/static-scan`
* Ollama model discovery in health surfaces, including available-model reporting and selected-model validation
* optional cloud providers:

  * `NVIDIA_API_KEY` with optional `NVIDIA_MODEL` (default: `stepfun-ai/step-3.7-flash`)
  * `GROQ_API_KEY` with optional `GROQ_MODEL` (default: `llama-3.1-8b-instant`)
  * `OPENROUTER_API_KEY` with `OPENROUTER_MODEL`
* browser heuristic fallback for local deterministic triage when both cloud routing and server-side static scanning are unavailable
* research submission through a server-side research backend
* preferred hosted backend: Supabase
* local/CI backend: JSONL append sink
* Airtable remains available only as a legacy compatibility fallback
* public web research submission is disabled by default; canonical records are intended for internal curated workflows
* CLI/CI aggregate-only submission with `aira scan --submit-research-aggregate`
* read-only CLI backend verification with `aira health --check-research`
* direct web backend verification with `/api/research-health` or `/api/supabase-health`

No research backend secret is exposed in the browser.

### Recommended zero-cost setup

For the current public scanner, the recommended path is:

* set `GROQ_API_KEY`
* optionally set `GROQ_MODEL`
* leave the UI on `Auto`

That gives AIRA a free structured-output cloud path with the browser heuristic scanner still available as the final fallback.

### Quick health check

To confirm Groq is wired without running a full scan:

```bash
curl http://localhost:3000/api/health
```

Or after deployment:

```bash
curl https://your-domain.example/api/health
```

You should see `groq` listed under `configured_providers` when `GROQ_API_KEY` is set.

To verify the configured research backend:

```bash
curl https://your-domain.example/api/research-health
```

For the preferred hosted path specifically:

```bash
curl https://your-domain.example/api/supabase-health
```

The recommended research storage layouts are documented in:

- [SUPABASE_SCHEMA.sql](./SUPABASE_SCHEMA.sql)
- [SUPABASE_MIGRATION_V2.sql](./SUPABASE_MIGRATION_V2.sql)
- [AIRTABLE_SCHEMA.md](./AIRTABLE_SCHEMA.md)

To probe the deterministic static scan route directly:

```bash
curl -X POST https://your-domain.example/api/static-scan \
  -H "Content-Type: application/json" \
  -d '{"lang":"python","code":"def ok():\n    return True\n"}'
```

### Recommended research backend

If you want to get away from Airtable, use Supabase for the hosted scanner:

```bash
RESEARCH_BACKEND=supabase
AIRA_ALLOW_PUBLIC_RESEARCH_SUBMISSIONS=false
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_TABLE=aira_submissions
SUPABASE_CHECKS_TABLE=aira_submission_checks
```

And use JSONL for local/CI collection:

```bash
AIRA_RESEARCH_JSONL=/absolute/path/to/aira-research.jsonl
```

### Supabase schema v2

Schema v2 keeps `public.aira_submissions` as the primary append-only stream and adds:

- sample stream identity: `sample_name`, `sample_version`
- attribution metadata: `attribution_class`, `source_id`, `source_kind`
- scoring metadata: `scanner_name`, `scanner_version`, `ruleset_version`, `scoring_version`
- derived trust metrics: `fti_score`, `risk_level`
- integrity fields: `submission_fingerprint`, `record_sha256`, `parent_record_sha256`
- normalized child rows in `public.aira_submission_checks`
- reproducibility manifests in `public.aira_sample_manifests`

For existing Supabase deployments, run [SUPABASE_MIGRATION_V2.sql](./SUPABASE_MIGRATION_V2.sql). New deployments can apply [SUPABASE_SCHEMA.sql](./SUPABASE_SCHEMA.sql) directly.

`sample_name`, `sample_version`, and `attribution_class` are the core caller-owned schema v2 inputs. `sample_version` defaults to `v1`, and `attribution_class` must be one of:

- `explicit_ai`
- `suspected_ai`
- `human_baseline`
- `unknown`

If `sample_name` is omitted, AIRA falls back to a conservative derived name so hosted web submissions do not break, but curated studies should set it explicitly to preserve lineage across repeated scans of the same sample stream.

### FTI-v1

Every Supabase submission is rescored server-side from `checks_json` using the stable FTI-v1 weights:

- `success_integrity=3`
- `audit_integrity=3`
- `exception_handling=3`
- `confidence_representation=3`
- `fallback_control=2`
- `bypass_controls=2`
- `return_contracts=2`
- `determinism=2`
- `idempotency_safety=2`
- `logic_consistency=1`
- `background_tasks=1`
- `environment_safety=1`
- `startup_integrity=1`
- `lineage=1`
- `test_coverage_symmetry=1`

Formula:

- `FAIL` contributes full weight
- `PASS` contributes `0`
- `UNKNOWN` contributes `0`
- `FTI = 100 - ((sum failed weights / sum all weights) * 100)`
- rounded to two decimals

Risk mapping:

- `>= 85.00` → `LOW_RISK`
- `>= 65.00 and < 85.00` → `MODERATE_RISK`
- `>= 40.00 and < 65.00` → `HIGH_RISK`
- `< 40.00` → `CRITICAL_RISK`

### Submission guarantees

Supabase schema v2 is intentionally append-only.

- prior submissions are not mutated by normal application flows
- duplicate submissions are coalesced by `submission_fingerprint`
- `record_sha256` is computed from the canonical persisted payload
- `parent_record_sha256` links each record to the most recent prior record in the same sample stream
- normalized `aira_submission_checks` rows are derived from aggregate-only counts, severities, weights, and statuses
- public web writes should remain disabled unless you intentionally want public traffic entering the curated study pipeline

The submission contract remains aggregate-only:

- source code is not sent
- snippets are not sent
- raw file contents are not sent
- child rows contain only check-level aggregate facts

### Curated public data collection

For canonical datasets built from public repos, use the manifest-driven collector instead of the public website:

```bash
aira collect ./docs/examples/public-collection.yaml --submit-research-aggregate
```

That flow shallow-clones public repos, scans them locally, and submits aggregate-only results plus `aira_sample_manifests` metadata from a documented sampling manifest. See [docs/PUBLIC_DATA_COLLECTION.md](./docs/PUBLIC_DATA_COLLECTION.md).

---

## Project Philosophy

AIRA is not primarily a bug detector.

It is a **truthfulness detector for software under failure**.

Its purpose is not to eliminate defects, but to identify conditions where defects can silently alter a system’s representation of its own correctness.

---

## Current Scope

AIRA should currently be understood as:

* a research scanner
* an evolving inspection framework
* a measurement tool for fail-soft behavior

It should not yet be treated as:

* a formal verifier
* a complete security audit
* a substitute for runtime testing or human review

---

## Contributing

Contributions are welcome, especially in these areas:

* new detection rules
* false-positive and false-negative reduction
* comparative scans across AI-assisted and non-AI-assisted codebases
* documentation improvements
* datasets and benchmark cases

---

## Repository Hygiene Roadmap

Short-term repo improvements include:

* sample scan outputs
* benchmark datasets
* rule calibration notes
* reproducible comparison fixtures
* cross-repo analysis tooling

---

## Final Note

AIRA is based on a simple but demanding question:

> **When a system fails, does it reveal that failure honestly—or does it preserve the appearance of success?**
