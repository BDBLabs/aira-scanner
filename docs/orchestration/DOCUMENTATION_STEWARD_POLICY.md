# Portfolio Documentation Steward Protocol v1.0

**Status:** Proposed; not active until independent final-head review and owner-authorized merge.

For any material orchestrated engineering effort, the orchestrator SHALL delegate a Documentation Steward function to a capable smaller/less expensive model when available. If unavailable, the orchestrator retains responsibility and records the reason. No live model is started by this document.

The steward SHALL propose and maintain ADRs for material architecture, security, governance, authorization, public API, data/persistence, migrations, service boundaries, and technology decisions. Preserve existing ADR locations and numbering, or use `docs/adr/` if none exists. ADRs include ID/title/date, Proposed/Accepted/Rejected/Superseded status, approving authority, context, decision, alternatives, tradeoffs, risks, rollback, PR/commit links, test evidence, reviewer and reviewed SHA. Never mark a proposal accepted without authorization; supersede old decisions rather than rewriting history.

The steward SHALL update `docs/orchestration/ENGAGEMENTS.md` for each substantial engagement: plan, actual tasks, assigned model identities (only exact exposed names), implementation/commit evidence, validations and skipped checks, independent review, successes, failures, lessons, residual uncertainty and next decisions. Explicitly distinguish planned, implemented, validated, reviewed, accepted, unknown. Do not infer execution from prompts or green CI from an unverified report.

The orchestrator SHALL check the documentation against real implementation and review the steward's output. Existing `AGENTS.md`, AI attribution, human approval, cross-model final-head reviews, branch protections, product boundaries and security rules take precedence; this policy cannot weaken them. The steward cannot authorize merges, deployments or policy changes and cannot independently approve its own ADR. Avoid storing private session transcripts, credentials or sensitive data.

For material PRs, ask: ADR required and appropriately authorized? Engagement evidence current? Architectural docs and diagrams aligned? Correct AI attribution? Independent final-head review and CI evidence present? Critical missing records block acceptance; routine changes need no unnecessary ADR. Actual GitHub automated enforcement must be verified separately.

After authorized merge, each active orchestrator must reload the instruction entrypoint, designate a real steward model (or document fallback), and record attributable acknowledgment. Merging text alone is not proof an agent loaded it.
