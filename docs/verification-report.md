# Verification report — Asterfield Pharmacy candidate

Recorded 2026-11-04 on the owner's Apple Silicon Mac. All pharmacy people, records, locations, pricing, stock, payments and fulfillment are synthetic. Current evidence supersedes historical milestone statements below; it does not establish clinical certification, public-service readiness or external protocol compatibility.

| Check | Observed result |
| --- | --- |
| Full backend regression | **99 passed in 29.86 seconds** (87 preserved-engine cases and 12 pharmacy cases) |
| Targeted pharmacy rerun after speech process cleanup | **12 passed in 7.16 seconds** |
| Pharmacy Chromium/browser acceptance | **4 passed in 40.3 seconds** including actual local recognition, actual Qwen3-TTS WAV generation and browser playback-state confirmation |
| Preserved retail browser regression | **6 passed in 12.7 seconds** including local OIDC login/revocation and source response-loss recovery |
| Accessibility/mobile | Automated WCAG checks on pharmacy landing, pickup, permission dialog, household and history; permission keyboard behavior and a 390-pixel viewport without horizontal overflow. Bounded Chromium checks, not a complete audit |
| TypeScript/Vite build and Ruff | Passed |
| Natural voice sample | Qwen3-TTS supplied Ryan preset: 7.2 seconds of audio generated in 9.047 seconds after model loading. A separate whisper.cpp run read back the expected Cedar Square and $40.98 confirmation. One sample, not a percentile or human-rated quality benchmark |
| Optional neural-runtime dependency audit | pip-audit 2.10.1 reported no known vulnerabilities in the pinned local voice environment at check time |
| Pharmacy image | Non-root/read-only-root startup, product discovery and recorder asset over HTTP passed. This packaged profile uses a rule baseline and excludes host Codex/speech environments |
| Migration/restore rehearsal | Fresh upgrade, metadata check, downgrade to base and re-upgrade passed. Commerce: **29 tables / 826 rows**; source: **2 tables / 48 rows** restored with matching per-table fingerprints at the recorded snapshot |

## Pharmacy behavior exercised

Backend tests cover full customer/staff/verified pickup; unresolved coverage, too-soon/exhausted refills; exact approval; twenty concurrent acceptances of one quote returning one order; two separate quotes competing for the same refill with one accepted; request-limit tightening; caregiver and permission revocation; authorization/capture response loss and inquiry; staff rejection/release; owner/role/CSRF/cancellation boundaries; body limits; pharmacy read-only MCP; and rejection of client-provided or stale spoken-success prose.

The optional voice browser case injects a disclosed synthesized Aiden-preset command at Chromium's microphone input. It exercises getUserMedia, AudioWorklet, PCM WAV encoding, the local whisper.cpp recognizer, the workflow, then a real Qwen3-TTS Ryan-preset response. It verifies the returned engine, voice, WAV header, duration, correct location in the canonical sentence and the browser's speaking state. It is not a physical microphone, accent matrix, road/CarPlay test or independent human listening score.

## Client recording

A complete real-Codex customer/staff recording has demonstrated BUDGET_EXCEEDED without an order, ORDERED with AUTHORIZED payment, READY_FOR_PICKUP with CAPTURED payment, and PICKED_UP with confirmed handover. Both model interpretations reserved the normal durable allowance. Actual app speech and separately generated neural narration are retained with the raw WebM and scene/receipt manifest. Final video: **236.569 seconds, 6,616,715 bytes, H.264 1440×1000 with AAC audio**. It contains two actual app spoken updates plus separately generated neural narration and the synthetic customer command. The final isolated journal contains one authorize, one capture and one dispense command, with two actual Codex interpretations taking 4.502 and 4.453 seconds. These are two authored demonstrations, not a representative accuracy result. [Sanitized run evidence](../results/pharmacy/2026-11-04-local.json); [capture recipe](pharmacy/demo-guide.md).

Recorder development corrected display branding versus canonical facility name, a request-state assertion and an evidence-export table name. The running workflow was not changed to satisfy those assertions. The final capture/evidence helper completed successfully. Private outtakes remain available; they are not labeled production benchmarks or silently converted into accuracy claims.

## Current limits

The pharmacy batch workflow uses internal quotes/permissions; preserved AP2/TAP-style/UCP/ACP adapters are not its execution path. Real pharmacy/payer/payment contracts, external enrollment/conformance, native CarPlay approval, supported hosted inference, production identity/operations, abuse controls, broader evaluation/load/security/accessibility work and a distribution license remain release gates. Audio generation can lag the visible order status; written status remains authoritative and available if speech is busy/unavailable. No general low-latency conversational SLO is claimed.

---

## Preserved historical v0.1 and retail hardening

The original v0.1 record below is preserved. Current candidate evidence: 87 backend tests passed in 17.36 seconds; six browser tests passed (including real local OIDC and four-screen automated accessibility checks); the non-root packaged HTTP smoke completed in 2.597 seconds with synthetic response-loss recovery and duplicate execution resolving to one ID. The updated migration chain also passed fresh upgrade, downgrade-to-base, upgrade and metadata checks, and both commerce/source restores matched their table fingerprints. Identity-provider/configuration recovery remains a separate exercise. These timings are individual local observations, not latency percentiles or capacity claims. The older Docker ARM guest required the documented portable OpenSSL CPU profile. See [current status](STATUS.md) and [identity/packaging](local-identity-and-packaging.md).

Decision results are retained under results/evaluations: rule baseline 100/100; original Codex batch 1/3; corrected three-case regression 3/3. The original failures were not removed. No 100-case real-model accuracy, external merchant certification, deployed monitoring or production throughput is established.


Recorded 2026-11-04 on macOS. This report covers the standalone local implementation, not a deployed customer service. All purchases, products and provider effects are synthetic.

## Environment and commands

Python 3.12.7; uv 0.5.24; Node 23.9.0; PostgreSQL 17 from the digest pinned in Compose; Codex CLI 0.163.0. Python and npm dependency locks are committed with the implementation. The documented Node baseline and configured Linux CI use Node 22+. Linux CI has not been executed remotely in this work.

| Check | Observed result |
| --- | --- |
| `uv run ruff check src tests tools migrations` | Passed |
| `uv run ruff format --check src tests tools migrations` | Passed |
| `uv run pytest -q --cov=commerce` | **54 passed**, 10.73 seconds in the recorded final backend run |
| Statement coverage | **1,153 / 1,331**, 86.63% (displayed as 87%); not a branch-coverage claim |
| `uv run alembic check` | No new upgrade operations detected |
| `npm run build --prefix web` | TypeScript compilation and optimized Vite build passed |
| `npm run test:e2e --prefix web` | **4 passed**, 11.9 seconds in the recorded browser run |
| Python dependency audit | pip-audit 2.10.1: no known vulnerabilities in the installed locked application/dev environment after an unused vulnerable dependency was removed |
| npm dependency audit | Zero known vulnerabilities reported at verification time |
| Restore/migration rehearsal | Fresh upgrade, metadata check, downgrade to base, upgrade and check passed in a disposable database |
| Two-database restoration | Commerce: 14 tables/379 rows; source: 2 tables/28 rows at backup time. Restored per-table row counts and SHA-256 fingerprints matched |

Times describe these local runs, not performance budgets. Dependency audits are point-in-time advisory checks, not proof that dependencies contain no vulnerabilities. CI is configured in `.github/workflows/verify.yml` and must run after a separately authorized push before being described as green.

## Core acceptance evidence

| Scenario | Executed coverage | Limit |
| --- | --- | --- |
| AC-01 human approval | No approval/forged approval denied; graph resume cannot confer authority; full captured-and-delivered purchase | Synthetic identity and provider |
| AC-02 delegation | Concurrent requests compete against one held-plus-spent budget; revoked/out-of-scope grants denied | Small bounded local workload |
| AC-03 stale terms | Changed product price/version rejected before reservation or payment | Not an external merchant webhook integration |
| AC-04 last item | Two separate PostgreSQL connections race; one accepted, one out-of-stock | One-SKU race, not a capacity benchmark |
| AC-05 duplicate checkout | 50 concurrent submissions through eight threads yield one execution/order and three distinct normal saga commands | Does not prove universal exactly-once delivery |
| AC-06 expired/revoked authority | Inactive approval and grant checks fail closed | Production issuer/key trust not implemented |
| AC-07 failed fulfillment | Cancellation/refund paths and lost compensation response; delivered-but-capture-declined remains review | No real acquirer or physical dispenser |
| AC-08 recovery | Independent source commits before lost authorize/dispense/capture response; worker recreation/expired lease; real PostgreSQL graph checkpoint reconnection | Not arbitrary database-partition fencing or regional failover |
| AC-09 malicious content | Compromised planner/injected product cannot authorize an ineligible purchase | Not a repeated real-model adversarial evaluation |
| AC-10 forbidden scope | Wrong user/product/merchant rejected; forbidden kiosk stops before quote/execution | Not an enterprise IAM audit |

Additional tests cover CSRF/origin checks, request idempotency, malformed MCP inputs, model invocation/schema failures, durable quota reservations, completed-session admission, unknown source statuses, source-observation binding and telemetry redaction. Test fixtures refuse to recreate tables outside the named dedicated test databases.

The browser suite covers exact approval and persistent history, lost payment response recovery, ambiguity without purchase, and a 390-pixel viewport without horizontal overflow. Screenshots were visually inspected. This is not a complete accessibility audit or every browser/device matrix.

## Real Codex integration smoke

At 2026-11-04 19:45:27 UTC, `tools/smoke.py --provider codex` completed one purchase against the real local CLI adapter and independent HTTP source. The user-facing result was COMPLETED with CAPTURED payment and DISPENSED fulfillment. A duplicate checkout returned the identical execution ID. The source deliberately lost its authorization response after commit and the worker recovered by inquiry.

The two recorded model decisions took 4.920 and 4.270 seconds. End-to-end smoke elapsed time was 12.105 seconds. The CLI reported 12,874 input tokens and 99 output tokens in total. These are observed runtime fields, not a separately billed API cost calculation. Earlier adapter integration attempts exposed strict-output schema requirements; those failures were corrected and are covered by tests.

This establishes that the real signed-in adapter works for that scenario. It does **not** establish 97/100 accuracy, 20/20 ambiguity handling, model safety across arbitrary prompts, a latency percentile or a production throughput figure. Those historical narrative targets have not been relabeled as measurements.

## Operational evidence and unresolved work

The application/source were stopped and restarted without removing their volume; completed business state remained available. Restore rehearsals ran only in uniquely named scratch databases, then removed those databases. Private dumps, raw smoke output, coverage and audit evidence remain ignored under `.local/`; they are not published artifacts. The public report deliberately contains only synthetic aggregate evidence.

External AP2/TAP/UCP/ACP conformance, full MCP transport compatibility, real-model held-out evaluation, hosted inference, production identity, real payments, deployment/load/SLO/alerting, broader accessibility/security review and commercial licensing remain open gates. Read [status](STATUS.md), [protocol support](protocol-support.md) and [threat model](threat-model.md).
