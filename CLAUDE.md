# CLAUDE.md — AIRA Scanner Development Handbook

## Project Overview

**AIRA Scanner** (AI-Induced Risk Audit) is a research tool for detecting fail-soft patterns in software systems—especially those developed with significant AI assistance.

**Core Question**: "Does the system tell the truth when it fails?"

AIRA identifies systems that:
- Return success despite incomplete or failed operations
- Degrade silently instead of failing explicitly
- Obscure true system state under error conditions
- Preserve appearance of function while weakening guarantees

**Key Facts:**
- Command-line linter + rule engine
- Detects ~15+ fail-soft pattern categories
- Works on Python codebases
- Published as `aira-scanner` on PyPI and Homebrew
- Research-driven: empirical validation in progress

## Repository Structure

```
aira-scanner/
├── aira/                             # Main package
│   ├── rules/                        # Detection rule definitions
│   │   ├── success_integrity.py      # Returns success despite failure
│   │   ├── exception_suppression.py  # Silent exception swallowing
│   │   ├── audit_gaps.py             # Missing audit/evidence trails
│   │   ├── fallback_degradation.py   # Silent fallback behavior
│   │   ├── bypass_overrides.py       # Escape hatches + overrides
│   │   ├── return_contracts.py       # Ambiguous return semantics
│   │   ├── parallel_drift.py         # Logic inconsistency across calls
│   │   ├── background_tasks.py       # Unsupervised background work
│   │   ├── startup_integrity.py      # Startup validation gaps
│   │   ├── environment_drift.py      # Env-dependent behavior
│   │   ├── determinism_drift.py      # Non-deterministic reasoning
│   │   ├── lineage_gaps.py           # Missing source→output tracing
│   │   ├── confidence_misrepresent.py # Overstated confidence
│   │   ├── test_asymmetry.py         # Untested failure paths
│   │   └── retry_idempotency.py      # Retry/idempotency assumptions
│   ├── scanner.py                    # Main scanning engine
│   ├── ast_utils.py                  # Python AST traversal helpers
│   ├── reporter.py                   # Result formatting + output
│   ├── config.py                     # Configuration management
│   └── __main__.py                   # CLI entry point
├── tests/                            # Test suite
│   ├── fixtures/                     # Code samples for testing rules
│   ├── test_scanner.py               # Integration tests
│   └── test_rules.py                 # Individual rule tests
├── docs/                             # Documentation
│   ├── PATTERNS.md                   # Detailed pattern definitions
│   ├── USAGE.md                      # Command-line usage guide
│   ├── RULE_DEVELOPMENT.md           # How to write new rules
│   └── RESEARCH.md                   # Research methodology + findings
├── examples/                         # Example codebases + findings
├── ROADMAP.md                        # Feature roadmap
├── CONTRIBUTING.md                   # Contribution guidelines
├── AIRTABLE_SCHEMA.md                # Airtable findings database
├── CHANGELOG.md                      # Version history
└── README.md                         # Quick start
```

## Fail-Soft Pattern Categories

### 1. Success Integrity Violations
System returns HTTP 200 / success code despite operation failure.

**Example** (from TrueTraining audit):
```python
# Register endpoint returns 201 even when duplicate email + wrong password
if existing_user and password_wrong:
    token = _create_token(uuid.uuid4(), ...)  # Fake user_id!
    return TokenResponse(access_token=token)  # ✗ Success despite auth failure
```

**AIRA Detection**: Looks for success returns in exception handlers or post-failure branches.

### 2. Audit & Evidence Integrity Gaps
System fails to record evidence of decision or operation outcome.

**Example**:
```python
# Governance audit consumer never persists events due to indentation bug
async for msg_id, data in bus.subscribe(...):
    # Extract data
    pass  # Loop ends here
# DB insert OUTSIDE loop = never executes = zero audit events
```

**AIRA Detection**: Looks for audit/logging calls that may not execute, missing transaction boundaries, unacked messages.

### 3. Broad Exception Suppression
Catch-all `except:` or `except Exception:` with no propagation or logging.

**Example**:
```python
try:
    important_operation()
except:
    pass  # ✗ Silent failure
```

**AIRA Detection**: Flags bare `except:` clauses and exception handlers without logging.

### 4. Fallback & Degradation
System silently falls back to unsafe defaults instead of failing.

**Example**:
```python
# Event publishing fails but caller thinks it succeeded
try:
    await bus.publish(event)
except:
    logger.error("publish failed")
    # But route still returns HTTP 201 (Created)
```

**AIRA Detection**: Looks for `fail_open` patterns, silent retry logic, unchecked fallback branches.

### 5. Bypass & Override Paths
Escape hatches for "testing" or "debugging" that weaken guarantees.

**Example**:
```python
if os.getenv("SKIP_GOVERNANCE"):  # ✗ Env-var bypass
    return decision  # Skip all integrity checks
```

**AIRA Detection**: Flags environment-variable gates on safety-critical code.

### 6. Ambiguous Return Contracts
Function return types don't distinguish success/failure cases.

**Example**:
```python
def process():
    try:
        return compute()
    except:
        return None  # ✗ Ambiguous: None = computed None, or error?
```

**AIRA Detection**: Looks for Optional returns from functions that may fail.

### 7. Parallel Logic Drift
Same operation implemented differently in different code paths.

**Example**:
```python
# Tenant isolation enforced via RLS in DB, but also in middleware
# If one fails silently, the other may not catch it
```

**AIRA Detection**: Looks for redundant safety checks that may have diverged.

### 8. Unsupervised Background Tasks
Async/background work with no monitoring or result collection.

**Example**:
```python
# Fire-and-forget celery task
process_document_task.delay(...)  # ✗ No error handling
```

**AIRA Detection**: Looks for `task.delay()` or `create_task()` without error handlers.

### 9. Startup Integrity Weaknesses
Configuration validation missing at startup (fails at runtime instead).

**Example**:
```python
# API_KEY not validated at __init__, fails at first API call
self._api_key = os.getenv("OPENAI_API_KEY", "")  # ✗ Empty string allowed
```

**AIRA Detection**: Looks for missing validation on critical config/dependencies.

### 10. Environment-Dependent Safety Drift
Safety behavior changes based on ENVIRONMENT variable.

**Example**:
```python
if ENVIRONMENT != "production":
    skip_governance_checks()  # ✗ Dev-only bypass that might escape
```

**AIRA Detection**: Flags conditional security/safety logic.

### 11. Determinism Drift
Non-deterministic reasoning (RNG, timing) without seeding.

**Example**:
```python
choice = random.choice(options)  # ✗ Can't reproduce failures
```

**AIRA Detection**: Looks for `random`, `time.now()` without seeding.

### 12. Source-to-Output Lineage Gaps
Missing tracing of where output came from / what data influenced decision.

**Example**:
```python
# Response includes synthesized data but original sources not linked
return {"summary": generated_text}  # ✗ No source attribution
```

**AIRA Detection**: Looks for data transformations without provenance tracking.

### 13. Confidence Misrepresentation
System claims high confidence but based on weak evidence.

**Example**:
```python
# Scores averaged without weighting importance
avg_score = sum(scores) / len(scores)  # ✗ Treats all scores equally
```

**AIRA Detection**: Looks for confidence aggregation without evidence strength weighting.

### 14. Failure-Path Test Asymmetry
Happy-path tested extensively, error paths untested.

**Example**:
```python
# Route has 10 happy-path tests, 0 error case tests
@router.post("/items")
async def create_item(...):  # ✓ Tested
    # But error handling never tested
```

**AIRA Detection**: Looks for exception handlers and error branches in untested code.

### 15. Retry & Idempotency Assumption Drift
Code assumes operations are idempotent but doesn't verify.

**Example**:
```python
# Message may be retried, but deduplication not checked
async for msg_id, data in bus.subscribe(...):
    await db.execute(insert(...))  # ✗ No idempotency check
    await bus.ack(...)
```

**AIRA Detection**: Looks for message consumers without deduplication checks.

## Development Workflow

### Setup
```bash
cd ~/Documents/GitHub/aira-scanner

# Install in development mode
pip install -e ".[dev]"

# Or with uv
uv sync --extra dev
```

### Running the Scanner
```bash
# Scan a single file
aira scan my_file.py

# Scan a directory
aira scan my_project/

# Scan with specific rule set
aira scan --rules exception_suppression,audit_gaps my_project/

# Output JSON for processing
aira scan --format json my_project/ > findings.json

# Verbose mode (show reasoning)
aira scan -v my_project/
```

### Running Tests
```bash
# All tests
pytest tests/ -v

# Specific rule
pytest tests/test_rules.py::TestExceptionSuppression -v

# Coverage
pytest --cov=aira tests/
```

### Adding a New Rule

1. **Create rule file** in `aira/rules/my_pattern.py`:
```python
from aira.rule_base import Rule, Finding

class MyPatternRule(Rule):
    """Detect my specific fail-soft pattern."""

    category = "my_category"
    severity = "high"  # high, medium, low
    description = "Description of what this detects"

    def check(self, node, context):
        """AST visitor method — return list of Finding objects."""
        findings = []
        # Traverse AST, detect pattern
        if self.matches_pattern(node):
            findings.append(Finding(
                node=node,
                message="What went wrong",
                remediation="How to fix it",
                confidence=0.95,  # 0-1 scale
            ))
        return findings
```

2. **Add tests** in `tests/test_rules.py`:
```python
def test_my_pattern_detected():
    code = """
    try:
        operation()
    except:
        pass  # ✗ Should be detected
    """
    findings = scan_code(code, rules=[MyPatternRule])
    assert len(findings) == 1
```

3. **Document** in `docs/PATTERNS.md` with examples

4. **Register** in `aira/rules/__init__.py`

## Key Files to Know

| File | Purpose | Notes |
|------|---------|-------|
| `aira/rules/` | Pattern detection implementations | Each rule = one fail-soft category |
| `aira/scanner.py` | Main orchestration + AST traversal | Coordinates rule execution |
| `aira/ast_utils.py` | AST helper functions | `find_in_handler()`, `find_return_in_branch()`, etc |
| `aira/reporter.py` | Formatting findings for output | Text, JSON, HTML formats |
| `tests/fixtures/` | Code samples for testing | Good for rule development |
| `docs/PATTERNS.md` | Detailed pattern definitions | Reference for developers |
| `AIRTABLE_SCHEMA.md` | Findings database structure | Tracks scan results across projects |

## Configuration

### Rule Configuration
```yaml
# .aira/config.yaml
rules:
  - name: exception_suppression
    severity: high
    enabled: true
  - name: audit_gaps
    severity: critical
    enabled: true
  - name: environment_drift
    severity: medium
    enabled: false  # Optional rule
```

### Exclusions
```yaml
exclude:
  - "*/vendor/*"
  - "*/.venv/*"
  - "*/tests/*"  # Don't scan test code
```

## Common Tasks

### Scanning a Codebase
```bash
# Scan with all rules
aira scan my_repo/

# High/critical severity only
aira scan --min-severity high my_repo/

# Specific categories
aira scan --rules success_integrity,audit_gaps my_repo/

# Output to file
aira scan my_repo/ > findings.txt
```

### Generating Reports
```bash
# JSON output
aira scan --format json my_repo/ | jq '.findings[] | select(.severity=="critical")'

# HTML report
aira scan --format html --output report.html my_repo/

# CSV for spreadsheet analysis
aira scan --format csv my_repo/ > findings.csv
```

### Interpreting Results

Each finding includes:
- **Pattern**: Category of fail-soft behavior
- **Severity**: Critical / High / Medium / Low
- **Confidence**: 0-1 scale (1.0 = certain, 0.7 = probable)
- **Location**: File + line number
- **Message**: What the pattern is
- **Remediation**: How to fix it

**Example**:
```
File: services/auth-service/app/routes/auth.py:243
Pattern: Success Integrity Violation
Severity: High
Confidence: 0.95

Message: Function returns TokenResponse on duplicate email, even when password is wrong.
Remediation: Either reject the request with 409 Conflict, or don't return a valid JWT.
```

## Research & Publication

- **arXiv**: https://arxiv.org/abs/2604.17587 (published research paper)
- **Methodology**: `docs/RESEARCH.md` — how patterns were identified
- **Findings Database**: `AIRTABLE_SCHEMA.md` — structure for tracking scan results

## Integration with Other Tools

### Use in CI/CD
```yaml
# .github/workflows/aira-scan.yml
name: AIRA Scanner
on: [pull_request]
jobs:
  aira:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install aira-scanner
      - run: aira scan . --format json --output findings.json
      - run: |
          CRITICAL=$(jq '.findings[] | select(.severity=="critical") | length' findings.json)
          if [ $CRITICAL -gt 0 ]; then exit 1; fi
```

### Use in Code Review
```bash
# Scan changes in PR
aira scan --files-only <(git diff --name-only origin/main) .
```

### Use as Library
```python
from aira.scanner import AIRAScanner
from aira.rules import AllRules

scanner = AIRAScanner(rules=AllRules)
findings = scanner.scan_directory("my_project/")

for finding in findings:
    if finding.severity == "critical":
        print(f"CRITICAL: {finding.message}")
```

## Patterns Found in Recent Audits

### TrueTraining (2026-06-09)
- ✗ Success Integrity: Register returns valid JWT on failed auth
- ✗ Audit Gaps: Governance audit events never persisted (loop/insert indentation)
- ✗ Exception Suppression: Governance service import silently binds None
- ✗ Success Integrity: Event publishing fails silently, route returns 201
- ✗ Startup Integrity: AI providers don't validate API keys at init
- ✗ File Upload: Reads entire file into memory (potential OOM)

### V8 (Constitutional AI Governance)
- ✓ Well-tested exception handling
- ✓ Audit trail properly persisted
- ✓ Critic independence maintained
- ✗ (See ELEANOR V8 code review for findings)

## Conventions

- **Rule naming**: `snake_case` for module names, `PascalCase` for classes
- **AST patterns**: Use `ast.NodeVisitor` for traversal
- **Severity levels**: Critical (blocks production), High (fix before merge), Medium (tech debt), Low (nice to have)
- **Confidence**: 0.9+ for pattern matching with clear AST signatures, 0.7+ for heuristics

## Contributing

1. **Identify a pattern** (see `docs/PATTERNS.md`)
2. **Implement rule** in `aira/rules/`
3. **Add tests** with code fixtures
4. **Document remediation** (how to fix)
5. **Update ROADMAP.md**
6. **Submit PR** with research findings if applicable

See `CONTRIBUTING.md` for detailed guidelines.

## Getting Help

- Pattern definitions → `docs/PATTERNS.md`
- Rule development → `docs/RULE_DEVELOPMENT.md`
- Scanner usage → `docs/USAGE.md`
- Research methodology → `docs/RESEARCH.md`

---

**Last Updated**: 2026-06-09
**Website**: https://aira.bageltech.net
**Paper**: https://arxiv.org/abs/2604.17587
**Active Researchers**: Bill P + team
