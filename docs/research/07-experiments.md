# Executed research experiments

Date: 2026-11-04. All experiments used synthetic/local data or public source material. These are isolated feasibility/contract investigations; the v0.1 application has not acquired new protocol integrations as a result.

## AP2 v0.2.0 SDK

Source: `google-agentic-commerce/AP2` tag v0.2.0, commit `b4587ac1d055888a73b4b21750973cffba961793`. Ran the Python SDK tests, without sample agents or provider connections, under two isolated environments:

| Environment | Relevant versions | Observed result |
| --- | --- | --- |
| Modernized candidate | Python 3.12.7, cryptography 50.0.2, jwcrypto 1.6.1, sd-jwt 0.10.4, Pydantic 2.14.2, pytest 9.2.0 | **186 passed, 2 failed** |
| Original declared pins | cryptography 46.0.5, jwcrypto 1.5.6, sd-jwt 0.10.4, Pydantic 2.12.5, pytest 9.0.2 | **186 passed, 2 failed** |

The failing tests are `kb_sd_jwt_intermediate_tests.py::test_verify_rejects_aud_mismatch` and `::test_verify_rejects_nonce_mismatch`. The primitive's implementation applies expected audience/nonce checks only to terminal hops while these tests expect them on intermediate hops too. Full-chain final-hop checks are a separate path. This is a reproducible source/test contract inconsistency; it is not presented as a confirmed exploitable vulnerability.

The old pin audit flagged cryptography, jwcrypto and pytest. Advisory entries include aliases/duplicates, so the report does not call every returned entry a distinct vulnerability. The modern candidate spike environment reported no known vulnerabilities under pip-audit 2.10.1 at test time. No old dependency was installed into the application's environment.

To reproduce: obtain the pinned source, create an isolated Python 3.12 environment with the selected versions, set PYTHONPATH to `code/sdk/python`, and run pytest against `code/sdk/python/ap2/tests` with `python_files=*_tests.py`. Do not run the sample applications or assume a clean upstream suite.

## MCP Python SDK 2.3.0

Created an isolated authenticated Streamable HTTP server on loopback port 8862, using SDK TokenVerifier/AuthSettings, resource binding, per-request identity and a typed read-only status tool. Connected independent HTTP clients concurrently.

- Modern automatic discovery negotiated **2026-07-28** for Alex and Sam.
- Legacy mode negotiated **2025-11-25**.
- Each client read its own synthetic resource and was denied the other user's resource.
- Missing, invalid and wrong-audience bearer tokens returned 401.
- Protected-resource metadata was served with the expected MCP resource URL.
- A typed output model produced structured content. An earlier unparameterized `dict` annotation did not, which informed the implementation rule.

The server was stopped after the spike. Static test tokens are not an OIDC implementation; real local identity integration is a subsequent acceptance gate. In-memory SDK tests alone would not have exercised these HTTP auth checks.

## UCP v2026-08-25 schemas

Source: `87dd4b1fcff9105d68173120897237fa784c74ef`. Built official `ucp-schema` **1.4.1** using its locked crates.io package; crate checksum is recorded in the private receipt. Used the local pinned schema tree, not moving remote definitions.

- Schema lint: **129 files checked, all passed**, with warnings on service documents lacking JSON Schema `$id`.
- Validator contract tests: **52 passed, 0 failed** once the schema binary was available.
- Documentation examples: **343 passed, 0 failed, 0 errors, 53 explicitly skipped**.

Before installing the schema tool, two tool-gated checks were reported as skipped/failures by the script; they were not ignored in the final run. The first corpus command also used an incorrect relative base path; the rerun used an absolute local schema base. These are setup diagnostics, not suppressed schema failures.

Schema/documentation tests do not establish runtime checkout, payment or network conformance. The tool's operation projection and local bundling are the relevant integration mechanisms.

## HTTP signatures

Used `http-message-signatures` **3.0.0** and cryptography 50.0.2 with fresh local Ed25519 keys. A valid POST signed method/authority/path/query/content type/body digest/signature-agent/idempotency identity and a payment-purpose tag.

Six independent negative cases were rejected: changed method, path, authority, query, body and purpose tag. Re-verifying the original signed request succeeds cryptographically, confirming that durable replay prevention remains application policy. No Visa endpoint, enrolled key, consumer-recognition object or payment container was tested. This establishes selected RFC 9421/digest library behavior, not TAP certification.

## Accessibility and dependency feasibility

Axe-core **4.14.0**, Playwright **1.64.1**, Chromium and the running local v0.1 application were used for read-only screen checks. Sign-in, shopping, permissions and history each reported serious color-contrast violations. That is actionable release work, not a claim that the application passed accessibility review. The audit browser bypassed CSP to inject the audit library; application CSP was unchanged.

The complete candidate Python dependency set, including the existing application stack and proposed MCP/Authlib/signature/SD-JWT/schema libraries, resolved successfully for Python 3.12. The isolated installed spike set audited without known findings. Resolution does not prove all application integrations pass; each remains a targeted implementation test.

A second resolution included the actual tagged AP2 source package with explicit overrides for cryptography, jwcrypto, Pydantic and pytest. It resolved 90 packages. This shows a declared modernized dependency route is feasible; it does not remove the SDK contract/logging concerns or count as an application integration test.

## Evaluation-source inspection

Inspected the pinned Tau2 evaluator/environment comparison and AgentDojo task-suite utility/security checks. Their environment/communication/action and utility/security separation informs this project's evaluator. No Tau2/AgentDojo benchmark, LLM user simulator, attack generation or paid model evaluation was executed. Their reported scores are not attributed to this project.

## Evidence retention

Raw source manifests, dependency receipts, test logs and spike output remain private under the ignored research directory. Public source locks and this aggregate report contain no credentials, private payment research or real customer data. Application verification remains separately recorded in [v0.1 verification](../verification-report.md).
