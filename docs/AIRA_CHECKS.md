# AIRA Checks Reference

This document defines the 15 AIRA checks at a practical level.

The goal is not to create a formal semantics document. The goal is to make each check inspectable, discussable, and usable in research.

## Summary Table

| ID | Name | Automation Status | Typical Concern |
| --- | --- | --- | --- |
| C01 | Success Integrity | Automated | Success returned after critical failure |
| C02 | Audit / Evidence Integrity | Automated | Audit or evidence loss can occur silently |
| C03 | Broad Exception Suppression | Automated | Exceptions are swallowed or neutralized |
| C04 | Distributed Fallback / Degraded Execution | Automated (heuristic-heavy) | Fallback behavior is scattered and weakens guarantees |
| C05 | Bypass / Override Paths | Automated | Flags or overrides disable intended safeguards |
| C06 | Ambiguous Return Contracts | Automated | `None`/`null`/`false` blurs absence and failure |
| C07 | Parallel Logic Drift | Human review | Divergent logic paths produce inconsistent semantics |
| C08 | Unsupervised Background Tasks | Automated | Async or background work lacks supervision |
| C09 | Environment-Dependent Safety | Automated | Safety is relaxed in local/dev/test/staging paths |
| C10 | Startup Integrity | Automated | Startup/init catches failure and continues |
| C11 | Deterministic Reasoning Drift | Automated | Decision paths use non-deterministic model settings |. 
| C12 | Source-to-Output Lineage | Human review | Outputs lack traceable link to their input or reasoning basis |
| C13 | Confidence Misrepresentation | Automated | Output is inferred or degraded without explicit confidence posture |
| C14 | Test Coverage Asymmetry | Automated | Failure-path tests lag happy-path tests |
| C15 | Retry / Idempotency Assumption Drift | Automated | Retries happen on writes without idempotency controls |

## C01: Success Integrity

**Question:** Does the code return or signal success after a critical operation has already failed?

Typical signals:

- success-like returns in exception handlers
- success responses after validation, persistence, or critical side effects fail
- “ok” or ready-state signaling after integrity loss

Why it matters:

- it preserves the appearance of correct execution after a broken guarantee

## C02: Audit / Evidence Integrity

**Question:** Can audit, evidence, or trace writes fail without halting or materially changing the reported outcome?

Typical signals:

- audit writes inside swallowed try/catch or try/except blocks
- evidence recording paths treated as best-effort without explicit degraded posture
- logging of audit failure without escalation where assurance depends on it

Why it matters:

- systems that claim governance or evidence integrity become untrustworthy if the evidence path can fail silently

## C03: Broad Exception Suppression

**Question:** Are exceptions caught too broadly or absorbed without preserving failure semantics?

Typical signals:

- `except Exception`
- broad `catch` blocks that only log
- handlers that do not re-raise, reject, or halt

Why it matters:

- broad suppression is one of the clearest pathways to fail-soft behavior

## C04: Distributed Fallback / Degraded Execution

**Question:** Is fallback or degraded behavior scattered across the system in a way that weakens guarantees?

Typical signals:

- repeated `fallback`, `best effort`, `degraded`, or “continue anyway” logic
- many dispersed soft-fail branches
- operationally important features quietly converting into optional behavior

Why it matters:

- the more fallback logic is distributed, the harder it becomes to reason about actual assurance

## C05: Bypass / Override Paths

**Question:** Are there switches, flags, or overrides that can disable important protections?

Typical signals:

- `testing_bypass`
- `skip_validation`
- `force_model_output`
- `allow_degraded`
- mock or override paths that alter guarantees outside clearly bounded environments

Why it matters:

- bypasses are sometimes necessary, but they are high-impact because they can silently redefine the system contract

## C06: Ambiguous Return Contracts

**Question:** Do return values blur the difference between absence, failure, disabled state, and success?

Typical signals:

- `None`, `null`, `undefined`, or `false` reused across different semantic meanings
- no explicit error object or status distinction
- callers that cannot tell what kind of non-success occurred

Why it matters:

- ambiguity at the return-contract level makes higher-level fail-soft behavior hard to detect

## C07: Parallel Logic Drift

**Question:** Do multiple implementations of the same conceptual flow drift apart semantically?

Examples:

- sync and async paths diverge
- normal and streaming paths enforce governance differently
- duplicate code paths evolve different failure semantics

Automation status:

- human review only

Why it matters:

- this usually requires repo-scale semantic comparison, not just local pattern matching

## C08: Unsupervised Background Tasks

**Question:** Is important async or background work launched without proper supervision, observation, or failure handling?

Typical signals:

- detached async tasks
- background workers without health tracking
- fire-and-forget work carrying evidence or policy responsibilities

Why it matters:

- important guarantees can silently die in background execution

## C09: Environment-Dependent Safety

**Question:** Does the code relax safety or integrity depending on environment in ways that may escape their intended scope?

Typical signals:

- safety disabled for `local`, `dev`, `test`, or `staging`
- fallback to weaker providers or weaker controls outside production
- startup or secret handling that becomes permissive in non-production environments

Why it matters:

- environment drift is one of the easiest ways for soft-fail behavior to become normalized

## C10: Startup Integrity

**Question:** Can initialization or startup failures occur without preventing the system from appearing ready?

Typical signals:

- startup integrity checks wrapped in broad catches
- init failures logged but not treated as blocking
- “ready” behavior despite incomplete critical initialization

Why it matters:

- startup is where assurance boundaries are established; soft-fail behavior there is especially dangerous

## C11: Deterministic Reasoning Drift

**Question:** Are decision-making paths using non-deterministic model settings or randomness where reproducibility matters?

Typical signals:

- non-zero temperature in decision-critical workflows
- random model selection for governed decisions
- low reproducibility in assurance-sensitive paths

Why it matters:

- non-determinism can undermine auditability and repeatability

## C12: Source-to-Output Lineage

**Question:** Can outputs be traced back to the inputs, transformations, or reasoning basis that produced them?

Automation status:

- human review only

Why it matters:

- lineage failures degrade explainability, reproducibility, and evidence quality

## C13: Confidence Misrepresentation

**Question:** Does the system present inferred, degraded, or weakly grounded output without an explicit confidence posture?

Typical signals:

- synthesized output with no uncertainty marker
- degraded paths that still look authoritative
- weak or fallback reasoning presented as normal output

Why it matters:

- the system can become epistemically dishonest even when it is not technically crashing

## C14: Test Coverage Asymmetry

**Question:** Are failure paths under-tested relative to happy paths?

Typical signals:

- many happy-path tests and few failure-path tests
- failure conditions not exercised even where code has complex exception or fallback logic
- assurance-sensitive branches lacking explicit tests

Why it matters:

- systems can look well-tested while leaving the most important failure semantics unexamined

## C15: Retry / Idempotency Assumption Drift

**Question:** Does the code retry operations that are not clearly idempotent?

Typical signals:

- retries around persistence or side-effectful writes
- no idempotency keys, guards, or duplicate-write controls
- optimistic assumption that retried writes are safe

Why it matters:

- retry behavior can quietly duplicate or corrupt state while preserving an appearance of resilience

## Interpreting The Checks

AIRA is strongest when these checks are read together.

For example:

- `C03` plus `C01` often indicates explicit failure concealment
- `C04` plus `C09` often indicates environment-shaped degraded assurance
- `C02` plus `C10` often indicates a system that can start and report readiness despite losing evidence guarantees
- `C13` is often the epistemic surface that makes the rest look normal

The checks are not just independent warnings. They often describe a failure profile.
