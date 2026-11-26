# UI remediation evidence — BDBLabs/aira-scanner

Work item: `AIR-01` (P0, direct browser-side Anthropic call and silent 8k truncation) and the evidence-only record for `AIR-02` (duplicate/vault UI).

## Scope and roles

- Worktree: `/Users/temporary/ui-ux-review/worktrees/wave2/BDBLabs__aira-scanner`
- Branch: `fix/ui-remediation/aira-scanner-p0`
- Baseline HEAD (verified before editing): `762ed246d018000ea7994784ca7b46993b879908`
- Implementation commit: recorded in the follow-up evidence commit after creation; no SHA is guessed here.
- Final head SHA: resolve with `git rev-parse HEAD`; a commit cannot contain its own SHA.
- Drafting agent: Big Pickle (`big-pickle`), provider `opencode`, surface OpenCode coding agent. Exact model version was not exposed to the agent.
- Reviewing model: none assigned. No PR, merge, push, or deploy was created. If an AI-drafted PR is opened, the repository's `AI_ATTRIBUTION.md` cross-model review requirement applies to the final head SHA.

### In scope

- `aira.html`: legacy public scanner page.
- `tests/aira_html_contract.test.mjs`: new static and mocked-server contract tests.
- `docs/ui-remediation/`: this evidence set and headless-Chrome artifacts.

### Out of scope

- `index.html` and `api/*`: already use server-side routes; unchanged.
- Any duplicate/vault repository: unchanged. See canonical mapping below.
- Live API calls: no credentials exist in this environment, and none were invented or used.

## Approach

1. `aira.html` no longer calls `api.anthropic.com`. The prompt is posted to the repository's existing `POST /api/scan`, whose `lib/llm.js` reads provider keys from server environment variables. The browser sends only `provider`, `system`, and `prompt`; it sends no key and no `baseUrl`.
2. On load, `aira.html` probes `GET /api/health`. The scan button remains disabled unless the health snapshot reports at least one server-configured provider. When the page is opened via `file://` or deployed without provider env vars, the UI shows an explicit unconfigured/unavailable state that explains the cause and points to the CLI. This is deliberately an honest disabled state, not a simulated successful scan.
3. The 8,000-character input boundary is now explicit. Before a scan, and again inside the results view, the UI states how many characters were analyzed and how many were omitted, and recommends the CLI for a full local scan. No silent `code.slice(0, 8000)` remains.
4. The legacy browser-side Airtable token placeholder and direct `api.airtable.com` call were removed. Research submission now goes to the existing `POST /api/research`; failure is reported honestly instead of pretending a token-protected browser call succeeded.
5. Verification uses static assertions plus mocked endpoint calls with a dummy server-side key. No live provider or storage credential was required.

## AIR-02 canonical mapping (proposal only)

- Proposed canonical source: this repository, `BDBLabs/aira-scanner`.
- Canonical current web scanner: `index.html` with `/api/scan`, `/api/static-scan`, `/api/health`, and `/api/research`.
- Legacy web page remediated here: `aira.html`, now redirected conceptually to the same server-side routes.
- Duplicate/vault UI: out of scope and not modified. Proposed action is to retire or redirect the duplicate to the canonical repository/page, or port this patch only after owner approval. No duplicate path, branch, or commit was inspected or changed by this work item.

## Evidence index

- [DECISIONS.md](./DECISIONS.md) — ADR-style choices, rejected alternatives, risks.
- [VERIFICATION.md](./VERIFICATION.md) — exact commands, results, environment limits, failures, lessons, residual risks.
- [evidence/aira-desktop-1440x900.png](./evidence/aira-desktop-1440x900.png) — headless Chrome artifact at 1440x900.
- [evidence/aira-mobile-375x812.png](./evidence/aira-mobile-375x812.png) — headless Chrome artifact at 375x812.

The screenshots are artifacts only. They were not visually inspected by the drafting agent.

---

AI-Model: Big Pickle (big-pickle; exact version not exposed)
AI-Provider: opencode
AI-Tool: OpenCode coding agent
AI-Role: Drafted
