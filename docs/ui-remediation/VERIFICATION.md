# Verification — `aira.html` UI remediation

Baseline: `762ed246d018000ea7994784ca7b46993b879908`
Branch: `fix/ui-remediation/aira-scanner-p0`
Final head SHA: resolve with `git rev-parse HEAD`; the implementation commit SHA is recorded in the follow-up evidence commit, because a commit cannot contain its own SHA.

Classification legend: `passed`, `failed`, `blocked`, `not-run`.

## 1. Baseline evidence (before editing)

Command:

```sh
git -C /Users/temporary/ui-ux-review/worktrees/wave2/BDBLabs__aira-scanner rev-parse HEAD
git -C /Users/temporary/ui-ux-review/worktrees/wave2/BDBLabs__aira-scanner status --short --branch
git show HEAD:aira.html | grep -nE "api\.anthropic\.com|claude-sonnet-4-20250514|code\.slice\(0, 8000\)|AIRTABLE_TOKEN|api\.airtable\.com"
```

Result:

```text
762ed246d018000ea7994784ca7b46993b879908
## fix/ui-remediation/aira-scanner-p0
1031:const AIRTABLE_TOKEN   = 'YOUR_AIRTABLE_PAT'; // set this server-side ideally
1228:  const response = await fetch('https://api.anthropic.com/v1/messages', {
1232:      model: 'claude-sonnet-4-20250514',
1235:      messages: [{ role: 'user', content: `Analyze this ${lang} code:\n\n${code.slice(0, 8000)}` }]
1368:    const res = await fetch(`https://api.airtable.com/v0/${AIRTABLE_BASE_ID}/${encodeURIComponent(AIRTABLE_TABLE)}`, {
1371:        'Authorization': `Bearer ${AIRTABLE_TOKEN}`,
```

Status: `passed` — baseline matched the assigned SHA and the confirmed findings were reproduced from `HEAD`.

## 2. Environment limits

Commands:

```sh
node --version
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --version
printenv | cut -d= -f1 | grep -E '^(ANTHROPIC|GROQ|OPENROUTER|GEMINI|GOOGLE|NVIDIA|SUPABASE|AIRTABLE|AIRA_)'
```

Result:

```text
v22.23.4
Google Chrome 158.0.8127.88
NO MATCHING ENV VAR NAMES
```

Status: `passed` for environment inventory. No live API credential was present, pasted, invented, or required.

## 3. Static assertions after the fix

Command:

```sh
if grep -nE "api\.anthropic\.com|claude-sonnet-4-20250514|AIRTABLE_TOKEN|YOUR_AIRTABLE_PAT|api\.airtable\.com|Authorization:.*Bearer|code\.slice\(0, 8000\)|baseUrl" aira.html; then printf 'MATCHES FOUND\n'; else printf 'NO MATCHES (grep exit 1)\n'; fi
```

Result:

```text
NO MATCHES (grep exit 1)
```

The committed Node contract test also asserts:

- no `api.anthropic.com`, `claude-sonnet`, `api.airtable.com`, `AIRTABLE_TOKEN`, `YOUR_AIRTABLE_PAT`, `YOUR_BASE_ID`, `Authorization: Bearer`, `baseUrl`, or `code.slice(0, 8000)` remains in `aira.html`;
- `MAX_SCAN_CHARS = 8000`, `/api/health`, `/api/scan`, `/api/research`, `Partial scan:`, and the no-key-in-browser note are present.

Status: `passed`.

## 4. Automated contract tests

Command:

```sh
npm test
```

Final result:

```text
# tests 7
# pass 7
# fail 0
# cancelled 0
# skipped 0
# todo 0
```

Coverage:

1. Static `aira.html` credential/direct-call assertions.
2. `/api/scan` with no configured providers and `fetch` stubbed to throw: HTTP 500 and `No providers are configured`, no dummy key echoed.
3. `/api/scan` with `GROQ_API_KEY=dummy-server-key` and `fetch` stubbed: exactly one request to `api.groq.com`, `Authorization: Bearer dummy-server-key` present on the outbound server-side request, HTTP 200 body contains the model text and does not contain the dummy key.
4. Four pre-existing provider routing tests.

Status: `passed`.

### First run failure and lesson

The first `npm test` run returned `6 pass / 1 fail`. The failing assertion expected `body.prompt` on the captured Groq request; `lib/llm.js` correctly wraps it as `buildMessages(system, prompt)`, so the prompt is at `body.messages.at(-1).content`. The test assertion was corrected; no production code was changed to force a pass. The second run is the 7/7 result above.

Status of failure follow-up: `passed`.

## 5. Inline script syntax

Commands:

```sh
python3 - <<'PY'
from pathlib import Path
html = Path('aira.html').read_text()
start = html.index('<script>') + len('<script>')
end = html.index('</script>', start)
Path('/tmp/aira-inline.js').write_text(html[start:end])
PY
node --check /tmp/aira-inline.js
```

Result: no output, exit 0.

Status: `passed`. The temporary file was outside the worktree and is not part of the commit.

## 6. Headless Chrome artifacts

Commands (exact required form, absolute paths):

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --no-first-run --hide-scrollbars --window-size=1440,900 --virtual-time-budget=6000 --screenshot=/Users/temporary/ui-ux-review/worktrees/wave2/BDBLabs__aira-scanner/docs/ui-remediation/evidence/aira-desktop-1440x900.png file:///Users/temporary/ui-ux-review/worktrees/wave2/BDBLabs__aira-scanner/aira.html

"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --no-first-run --hide-scrollbars --window-size=375,812 --virtual-time-budget=6000 --screenshot=/Users/temporary/ui-ux-review/worktrees/wave2/BDBLabs__aira-scanner/docs/ui-remediation/evidence/aira-mobile-375x812.png file:///Users/temporary/ui-ux-review/worktrees/wave2/BDBLabs__aira-scanner/aira.html
```

Result:

```text
478183 bytes written to file .../docs/ui-remediation/evidence/aira-desktop-1440x900.png
187673 bytes written to file .../docs/ui-remediation/evidence/aira-mobile-375x812.png
```

Both processes exited with code 2 after the files were written, with `Teardown watchdog expired; recording dump and terminating.` and macOS `CVDisplayLinkCreateWithCGDisplay failed` warnings. This is a headless Chrome teardown quirk in this environment, not a page assertion failure; the artifacts were written before teardown.

Dimension check command:

```sh
file docs/ui-remediation/evidence/aira-desktop-1440x900.png docs/ui-remediation/evidence/aira-mobile-375x812.png
sips -g pixelWidth -g pixelHeight docs/ui-remediation/evidence/aira-desktop-1440x900.png docs/ui-remediation/evidence/aira-mobile-375x812.png
```

Result: `PNG image data, 1440 x 900` and `PNG image data, 375 x 812`; `sips` reported the same widths and heights.

Status: `passed` for artifact creation and dimensions. The drafting agent did **not** visually inspect either screenshot; no claim about visual appearance is made.

## 7. Rendered unconfigured state under `file://`

Command:

```sh
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --disable-gpu --no-first-run --virtual-time-budget=6000 --dump-dom file:///Users/temporary/ui-ux-review/worktrees/wave2/BDBLabs__aira-scanner/aira.html > /tmp/aira-dom.txt 2>/tmp/aira-dom-stderr.txt
grep -o 'Cloud scan is unavailable[^<]*' /tmp/aira-dom.txt | head -2
grep -o 'id="scan-btn"[^>]*' /tmp/aira-dom.txt | head -1
```

Result (rendered text, first grep hit):

```text
Cloud scan is unavailable: /api/health could not be reached (Failed to fetch). This page must be served with /api/health and /api/scan plus server-side provider environment variables. Opening this file directly, or deploying without a configured provider, disables cloud scanning. Use the CLI for local scans.
```

Result (button state):

```text
id="scan-btn" onclick="runScan()" disabled=""
```

The second grep hit for `Cloud scan is unavailable` was the literal template string inside the inline script, not rendered UI text.

Status: `passed` — the fixed page's honest unconfigured state was rendered in the same `file://` context used for the screenshots.

## 8. Checks not run

- Live provider scan: `not-run` — no live credentials in this environment; mocked server tests cover the key-handling boundary instead.
- Visual review of screenshots: `not-run` by explicit instruction; screenshots are committed artifacts only.
- Duplicate/vault repository verification or modification: `not-run` — out of scope by assignment (AIR-02); owner approval required.
- PR cross-model review: `not-run` — no PR was created. `docs/ui-remediation/README.md` records the requirement if one is opened.
- Push, merge, deploy, production-data access: `not-run` — prohibited by assignment.

## 9. Residual risks

- `/api/health` is unauthenticated and lists configured provider names. This was pre-existing and is not a secret, but it is a configuration signal.
- `api/scan.js` still accepts a client-supplied `baseUrl` (pre-existing). The remediated page does not send it. Removing or validating that field is a separate owner decision.
- Input truncation at 8,000 characters remains; it is now disclosed rather than silent. Long-input results are partial by design.
- The duplicate/vault UI remains unfixed pending owner approval.
- Screenshots cover only the `file://` unconfigured state. A configured hosted scan was not screenshotted because no credentials exist here.
- Health status can change between probe and scan; `/api/scan` failures still surface in the page's error panel.

## 10. Diff hygiene

Command:

```sh
git diff --check && git diff --name-only
```

Result: no whitespace errors; tracked change is `aira.html`. Untracked files added by this work item are `tests/aira_html_contract.test.mjs` and `docs/ui-remediation/**`.

Status: `passed`.

---

AI-Model: Big Pickle (big-pickle; exact version not exposed)
AI-Provider: opencode
AI-Tool: OpenCode coding agent
AI-Role: Drafted
