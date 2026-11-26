# ADRs — `aira.html` UI remediation

Baseline: `762ed246d018000ea7994784ca7b46993b879908`
Branch: `fix/ui-remediation/aira-scanner-p0`

## ADR-001 — Route the legacy scan through the existing server-side endpoint

- Status: accepted.
- Context: baseline `aira.html` called `https://api.anthropic.com/v1/messages` directly from the browser. A browser cannot keep a provider key secret, and the page implied protection that did not exist. The repository already has `POST /api/scan` backed by `lib/llm.js`, which reads provider keys from server environment variables.
- Decision: keep the AIRA prompt logic in the page, but post only `provider: 'auto'`, `system`, and `prompt` to `/api/scan`. Do not send a key or a client-selected `baseUrl`.
- Rejected alternatives:
  1. Keep the direct call and add a comment claiming the key is server-side. Rejected: false assurance; browser source is public.
  2. Add a new bespoke Anthropic-only server route. Rejected: duplicates existing routing and would reintroduce single-vendor coupling contrary to `docs/EVOLUTION.md`.
  3. Convert the legacy page permanently to a static brochure with no scan capability. Rejected for this repo because a working server-side route already exists; the honest disabled state is retained as the fallback when that route is unavailable.
- Consequences / risks: the page is functional only when served by the same origin as `/api/scan` with providers configured. A direct `file://` open is explicitly disabled. `/api/health` already exposes configured-provider names; no additional secret is disclosed.

## ADR-002 — Fail visibly to an unconfigured state when server routing is unavailable

- Status: accepted.
- Context: the fix must be verifiable without live credentials. The page must not pretend a scan is available when it is opened from disk or deployed without provider env vars.
- Decision: disable the scan button by default, call `GET /api/health` on load, and enable the button only when the response reports `ok: true` and at least one configured provider. Otherwise render a visible message naming the missing server-side route/configuration and pointing users to the CLI.
- Rejected alternatives:
  1. Leave the button enabled and fail only after the user submits code. Rejected: preserves the misleading affordance.
  2. Hide the scanner silently. Rejected: this is itself a fail-soft UI pattern, contrary to the project's purpose.
- Consequences / risks: health endpoint failures are surfaced as text in the page; the exact error message is diagnostic, not a secret. A provider could disappear between the health probe and the scan; `/api/scan` errors are still shown through the existing error panel.

## ADR-003 — Disclose the 8,000-character boundary instead of silent truncation

- Status: accepted.
- Context: the baseline request silently sent only `code.slice(0, 8000)` while the UI implied a complete scan.
- Decision: keep a single explicit `MAX_SCAN_CHARS = 8000` boundary, compute source/scanned/omitted character counts, show a notice before the scan, and retain a second disclosure inside the results header. Attach the same counts to `result.meta`.
- Rejected alternatives:
  1. Remove the cap entirely. Rejected for this change because model context and request-size limits still exist; silent success would remain possible at a different boundary.
  2. Keep the cap but mention it only in documentation. Rejected: the user viewing results would not know the result is partial.
- Consequences / risks: results from long inputs are explicitly partial. The CLI is presented as the full local-scan path. This does not change deterministic static-scan behavior.

## ADR-004 — Remove browser-side storage credentials from the legacy page

- Status: accepted.
- Context: baseline `aira.html` also contained `AIRTABLE_BASE_ID`, `AIRTABLE_TABLE`, and `AIRTABLE_TOKEN` constants and posted an `Authorization: Bearer ...` header from the browser. They were placeholders, but they preserved the same false-protection pattern as AIR-01.
- Decision: remove those constants and the direct Airtable request. Submit the anonymized aggregate to the existing `POST /api/research`, which reads storage configuration from server environment. Report a failed submission explicitly.
- Rejected alternatives:
  1. Keep placeholders with a comment telling operators to set them server-side. Rejected: the browser still constructs the credential header.
  2. Keep the mailto path as the primary mechanism. Rejected: it bypasses the canonical research backend and produces a worse user experience.
- Consequences / risks: `api/research.js` disables public submissions unless explicitly enabled by server env; the UI now reports that honestly instead of appearing to succeed.

## ADR-005 — Record AIR-02 without touching any duplicate

- Status: accepted, owner approval pending for any duplicate-side action.
- Context: an identical UI exists in a duplicate/vault repository. The assignment explicitly forbids modifying it.
- Decision: treat `BDBLabs/aira-scanner` as the proposed canonical source, with `index.html` as the current web scanner and `aira.html` as the remediated legacy page. Record the mapping only in evidence docs. Do not edit, copy, or inspect any duplicate as part of this work item.
- Rejected alternatives: apply the same patch directly to the duplicate. Rejected: out of scope and requires owner approval.
- Consequences / risks: the duplicate remains vulnerable until the owner approves retirement, redirection, or a port of this patch.

---

AI-Model: Big Pickle (big-pickle; exact version not exposed)
AI-Provider: opencode
AI-Tool: OpenCode coding agent
AI-Role: Drafted
