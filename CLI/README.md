# AIRA Scanner — AI-Induced Risk Audit

**Version 1.2.1**  
*Bagelle Parris Vargas Consulting | bageltech.net*  
*Jurisprudential AI Governance Initiative*

---

## What Is This?

AIRA is a static analysis tool that detects a specific class of failure modes in AI-generated or AI-assisted code — failure modes that are **not random**, but **systematically produced by training incentives**.

The core claim:

> AI coding agents are reward-shaped toward human approval signals. Visible failure is a strong negative signal. Therefore, AI-generated code will systematically suppress, absorb, or reroute failure states — not from incompetence, but from incentive alignment.

AIRA implements 15 checks derived from empirical observation of these patterns across real AI-assisted codebases. Two checks (C07, C12) require human review; 13 are fully automated.

---

## Installation

### Homebrew

```bash
brew install BDB-Labs/aira-scanner/aira
```

Or tap once and use the short name:

```bash
brew tap BDB-Labs/aira-scanner
brew install aira
```

For the latest unreleased code:

```bash
brew install --HEAD BDB-Labs/aira-scanner/aira
```

### From source

```bash
git clone https://github.com/BDB-Labs/aira-scanner.git
pip install ./aira-scanner/CLI
```

**Requirements:** Python 3.9+, PyYAML

---

## Usage

### CLI

```bash
# Static scan a directory (terminal output)
aira scan ./my-project

# Hybrid scan using your local/model provider configuration
aira scan ./my-project --engine hybrid

# LLM-only scan against a local OpenAI-compatible endpoint
aira scan ./my-project --engine llm --provider openai-compatible --base-url http://localhost:1234/v1 --model gpt-oss-120b

# Health check provider wiring
aira health

# List supported providers and env vars
aira providers

# Scan with YAML report
aira scan ./my-project --output yaml

# Scan with JSON report (for CI/CD integration)
aira scan ./my-project --output json --out-file report.json

# Compare deterministic and model-assisted JSON outputs
aira scan ./my-project --engine static --output json --out-file static.json
aira scan ./my-project --engine llm --provider ollama --model minimax-m2:cloud --output json --out-file model.json
aira compare static.json model.json --output json --out-file suppression-matrix.json

# Exclude directories
aira scan ./my-project --exclude node_modules,dist,build

# Fail on MEDIUM or above instead of only HIGH
aira scan ./my-project --fail-on medium

# Submit aggregate-only results to the configured research backend
aira scan ./my-project --output json --submit-research-aggregate \
  --sample-name github:my-org/my-project \
  --sample-version 2026-03 \
  --attribution-class suspected_ai

# Verify research backend connectivity without writing a record
aira health --check-research

# Collect a curated public-repo dataset from a manifest
aira collect ./docs/examples/public-collection.yaml --submit-research-aggregate
```

### VS Code Extension

Install from the VS Code Marketplace (search "AIRA Scanner") or from the `.vsix` file.

- Right-click any file or folder → **AIRA: Scan**
- Command palette → **AIRA: Scan Workspace** or **AIRA: Scan Current File**
- Findings appear in the **Problems** panel with severity markers

---

## The 15 AIRA Checks

| ID  | Check | Automatable |
|-----|-------|-------------|
| C01 | Success Integrity | ✓ |
| C02 | Audit / Evidence Integrity | ✓ |
| C03 | Broad Exception Suppression | ✓ |
| C04 | Distributed Fallback / Degraded Execution | ✓ (partial) |
| C05 | Bypass / Override Paths | ✓ |
| C06 | Ambiguous Return Contracts | ✓ |
| C07 | Parallel Logic Drift | Human review |
| C08 | Unsupervised Background Tasks | ✓ |
| C09 | Environment-Dependent Safety | ✓ |
| C10 | Startup Integrity | ✓ |
| C11 | Deterministic Reasoning Drift | ✓ |
| C12 | Source-to-Output Lineage | Human review |
| C13 | Confidence Misrepresentation | ✓ |
| C14 | Test Coverage Asymmetry | ✓ |
| C15 | Retry / Idempotency Assumption Drift | ✓ |

---

## Supported Languages

- Python (.py)
- JavaScript (.js, .mjs, .cjs)
- TypeScript (.ts)
- JSX/TSX (.jsx, .tsx)

---

## Provider Modes

AIRA CLI supports:

- `static`: deterministic built-in analysis only
- `llm`: provider-assisted analysis only
- `hybrid`: merge static and LLM findings

Provider routing is local-first:

1. OpenAI-compatible local endpoint
2. Ollama
3. NVIDIA NIM
4. Groq
5. OpenRouter

The web app also now uses a deterministic server-side static scan before falling back to browser-only heuristics. That static scan is parser-backed for Python and, when `esprima` is installed, parser-backed for JavaScript as well.

Useful environment variables:

```bash
# OpenAI-compatible local or hosted endpoint
export AIRA_OPENAI_BASE_URL="http://localhost:1234/v1"
export AIRA_OPENAI_MODEL="gpt-oss-120b"

# Ollama
export AIRA_OLLAMA_MODEL="qwen3:32b"
export AIRA_OLLAMA_HOST="http://127.0.0.1:11434"

# Discover available Ollama models and validate the selected one
aira health --json

# NVIDIA NIM (default model: stepfun-ai/step-3.7-flash)
export NVIDIA_API_KEY="..."
export NVIDIA_MODEL="stepfun-ai/step-3.7-flash"

# Groq (default model: llama-3.1-8b-instant)
export GROQ_API_KEY="..."
export GROQ_MODEL="llama-3.1-8b-instant"

# Preferred hosted backend: Supabase
export RESEARCH_BACKEND="supabase"
export AIRA_ALLOW_PUBLIC_RESEARCH_SUBMISSIONS="false"
export SUPABASE_URL="https://your-project.supabase.co"
export SUPABASE_SERVICE_ROLE_KEY="..."
export SUPABASE_TABLE="aira_submissions"
export SUPABASE_CHECKS_TABLE="aira_submission_checks"

# Recommended schema v2 research metadata
export AIRA_SAMPLE_NAME="github:my-org/my-project"
export AIRA_SAMPLE_VERSION="2026-03"
export AIRA_ATTRIBUTION_CLASS="suspected_ai"
export AIRA_SOURCE_ID="my-org/my-project"
export AIRA_SOURCE_KIND="repo"
export AIRA_SCANNER_VERSION="1.3.0"
export AIRA_RULESET_VERSION="1.3.0"

# Local/CI backend: newline-delimited JSON
export AIRA_RESEARCH_JSONL="/absolute/path/to/aira-research.jsonl"

# Airtable legacy compatibility fallback
export AIRTABLE_BASE_ID="app..."
export AIRTABLE_TABLE="Submissions"
export AIRTABLE_TOKEN="pat..."
```

## Location-Aware Output

JSON and YAML scan output now includes deterministic finding identity metadata:

- `fingerprint`: stable per-finding identifier using check, location, snippet, boundary, and enclosing scope
- `semantic_fingerprint`: location-tolerant identifier for comparing similar findings across runs
- `location_fingerprint`: check + file + line + boundary identifier
- `boundary_type`: normalized failure boundary such as `exception_handler`, `fallback_branch`, `environment_gate`, `return_contract`, or `retry_write_boundary`
- `context`: parser/heuristic context including enclosing function/class, line count, normalized line position, and AST path when available
- `evidence`: normalized snippet evidence and whether the context came from structural parsing or heuristics

For model-vs-static studies, keep the raw JSON outputs from each run and compare them with:

```bash
aira compare static.json model.json --line-window 5
```

The comparison output reports static findings, model findings, same-location matches, model misses, model-only findings, static-FAIL/model-PASS check suppression, and counts by AIRA check and boundary type.

## Research Submission

The CLI can submit **aggregate-only** study data to the configured research backend:

```bash
aira scan . --output json --submit-research-aggregate \
  --sample-name github:my-org/my-project \
  --sample-version 2026-03 \
  --attribution-class suspected_ai
```

What is sent:

- AIRA check statuses
- severity totals
- total findings
- failed/passed/unknown check counts
- per-check finding counts
- per-check severity matrices
- scan mode / provider / model metadata
- CI metadata when available
- schema v2 lineage fields such as `submission_fingerprint` and `record_sha256`
- normalized per-check rows for `aira_submission_checks`

What is **not** sent:

- source code
- file paths from findings
- snippets
- raw file contents

### Research backends

Recommended:

- Supabase for the hosted web scanner
- JSONL for local and CI collection
- Airtable only as a legacy compatibility fallback

If you still use Airtable, the CLI remains compatible with the current minimal schema already implied by the web app proxy, and will populate richer optional fields when present:

- `Check Count JSON`
- `Check Severity JSON`
- `Checks Passed`
- `Checks Unknown`
- `Files Scanned`
- `Scan Mode`
- `Provider`
- `Model`
- `Target Kind`
- `CI Workflow`
- `CI Run ID`
- `CI Ref`

If one of those optional fields does not exist in Airtable yet, the CLI drops it and retries instead of failing the entire submission.

The recommended storage layouts are documented in:

- [SUPABASE_SCHEMA.sql](../SUPABASE_SCHEMA.sql)
- [SUPABASE_MIGRATION_V2.sql](../SUPABASE_MIGRATION_V2.sql)
- [AIRTABLE_SCHEMA.md](../AIRTABLE_SCHEMA.md)

### Supabase schema v2 requirements

For curated Supabase submissions, provide or preconfigure:

- `sample_name`: stable stream identifier for the code sample or repo under study
- `sample_version`: stream version label; defaults to `v1`
- `attribution_class`: one of `explicit_ai`, `suspected_ai`, `human_baseline`, `unknown`

Recommended CLI flags:

```bash
aira scan . --output json --submit-research-aggregate \
  --sample-name github:my-org/my-project \
  --sample-version 2026-03 \
  --attribution-class suspected_ai \
  --source-id my-org/my-project \
  --source-kind repo
```

Hosted and CLI Supabase submissions recompute FTI-v1 from `checks_json` on write, persist only aggregate facts, and treat the submission stream as append-only. Duplicate submissions are coalesced by `submission_fingerprint`.

For the hosted web app, keep `AIRA_ALLOW_PUBLIC_RESEARCH_SUBMISSIONS=false` unless you explicitly want public web traffic writing into the curated dataset.

### Curated public-repo collection

If you want the canonical dataset to come from public repos rather than public web users, use the collector:

```bash
aira collect ./docs/examples/public-collection.yaml --submit-research-aggregate
```

The collector:

- reads a YAML or JSON sampling manifest
- shallow-clones each public repo
- optionally checks out a specified ref
- runs AIRA locally
- submits aggregate-only results with schema v2 sample metadata
- upserts `aira_sample_manifests` rows when the backend is Supabase

Useful flags:

- `--output json`
- `--out-file collection.json`
- `--keep-repos`
- `--checkout-root /tmp/aira-collect`

See [docs/PUBLIC_DATA_COLLECTION.md](../docs/PUBLIC_DATA_COLLECTION.md) and [docs/examples/public-collection.yaml](../docs/examples/public-collection.yaml).

### FTI-v1

FTI-v1 uses the following stable weights:

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

---

## Output Format

AIRA produces structured YAML or JSON conforming to the AIRA v1.2 specification:

```yaml
aira_scan:
  version: "1.2"
  target: /path/to/project
  scanned_at: 2026-03-27T...
  summary:
    files_scanned: 48
    findings_total: 12
    by_severity:
      HIGH: 4
      MEDIUM: 6
      LOW: 2
  ai_failure_audit:
    success_integrity: FAIL
    exception_handling: FAIL
    # ... all 15 checks
  findings:
    - check_id: C03
      check_name: BROAD EXCEPTION SUPPRESSION
      severity: HIGH
      file: src/governance.py
      line: 142
      description: "Broad exception handler that logs but does not re-raise..."
      snippet: "except Exception as e:"
```

---

## CI/CD Integration

```yaml
# GitHub Actions example
- name: Run AIRA scan
  run: |
    pip install "git+https://github.com/BDB-Labs/aira-scanner.git#subdirectory=CLI"
    aira scan . --output json --out-file aira-report.json
  # Exit code 1 if HIGH severity findings found
```

---

## Research Data

AIRA was developed as part of the **Jurisprudential AI Governance Initiative** to empirically characterize training-induced failure patterns in AI-generated code. If you run AIRA on your codebase and would like to contribute anonymized findings to the research dataset, contact: **bill@bageltech.net**

---

## Citation

If you use AIRA in research or tooling, please cite:

> Parris, W.M. (2026). *AIRA: AI-Induced Risk Audit — A Structured Inspection Framework for AI-Generated Code Failure Patterns*. Bagelle Parris Vargas Consulting / Jurisprudential AI Governance Initiative.

---

## License

MIT License — Copyright © 2026 William M. Parris / Bagelle Parris Vargas Consulting
