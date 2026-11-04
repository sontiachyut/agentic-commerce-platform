# Platform, operations and accessibility

## Fit the resources we actually have

The research machine has 16 GiB host memory and ten CPU cores; Docker currently has four CPUs and about 3.84 GiB. This is enough for a bounded local identity/commerce/monitoring demonstration, but not a reason to run every optional infrastructure component continuously. Use Compose profiles and resource limits. Keep the existing host-operated Codex adapter separate from containers; do not bake or mount its native authentication into distributable images.

Package deterministic services with pinned base images, a non-root user, health checks, graceful termination, bounded resources and configuration validation. Separate migration and runtime database credentials. Keep application data and independent source effects persistent. Document the difference between a local Compose profile and a client production deployment. [Keycloak container guidance](https://www.keycloak.org/server/containers).

A local Keycloak profile should use persistent storage and explicit realm/client configuration. `start-dev` belongs only to the loopback demonstration; production needs an optimized server/TLS/hostname configuration. Identity mode and simulated financial source mode should be separate settings: real local OIDC does not imply real payments or permission to expose the runtime publicly.

## Inference boundary

The signed-in Codex adapter remains appropriate for this owner-operated local application. OpenAI's documentation distinguishes local/open-source app-server authentication from commercial/hosted use, and identifies a supported Sign in with ChatGPT path for eligible integrations. API access, partner access and credits cannot be assumed from the subscription alone. Keep a replaceable decision-provider interface and never proxy one personal login as a customer-facing model service. [Official integration documentation](https://learn.chatgpt.com/docs/app-server).

Do not copy auth caches into images, inspect tokens, activate paid resources or depend on unverified account entitlements. Research spikes used no real inference calls. When evaluation begins, enforce the existing call ledger and capture actual metadata without inferring a dollar cost from subscription token counters.

## Operational signals

Measure meaningful outcomes: accepted purchases, policy denials, unresolved source actions, recovery-required age, queue wait, retries, model availability/decision latency, payment/delivery outcomes and HTTP error/latency. Keep outcome counts separate from model task quality. Use bounded labels; execution/user/quote IDs belong in protected logs/traces, not metric labels. [Prometheus instrumentation](https://prometheus.io/docs/practices/instrumentation/).

Use Prometheus/Grafana locally with a least-privilege scrape credential, provisioned dashboards and tested alert rules. Do not use an eight-hour human operator cookie as the monitoring identity. Add redaction before export, not only in the viewer. Prompts, credentials, payment instruments and raw signed artifacts do not belong in ordinary telemetry. Store necessary audit evidence under explicit retention/access rules. [OpenTelemetry configuration](https://opentelemetry.io/docs/zero-code/python/configuration/).

Define SLIs from the user-visible workflow and separate model/queue/human/source wait. Proposed SLOs require a workload and observation period; a local load test does not demonstrate production availability. Alert on failures that require action, including aging unknown transactions and stuck jobs, and account for low traffic. [Google SRE alerting](https://sre.google/workbook/alerting-on-slos/).

## Performance methodology

Use an isolated benchmark database/source, seeded snapshots and a no-model lane. Declare hardware, Docker limits, service versions, concurrency, request mix, duration, success/error counts and warmup. Record latency histograms, queue delay, throughput and resource usage. Benchmark reads and accepted purchases separately; stock depletion and permission budgets must be controlled rather than mistaken for performance errors.

Profile SQL/query plans and worker contention before adding a broker or distributed agents. A single serialized graph intentionally limits model throughput. A separate checkout worker preserves progress for accepted purchases while inference waits. Changes to worker count require lease/stale-observation and contention regression tests.

## Accessibility findings

Axe-core 4.14.0 was run against sign-in, shopping, permissions and history through a real headless browser. All four screens reported serious color-contrast violations. The research audit bypassed CSP solely to inject the audit library into that test browser; application CSP was not changed. No purchase or model call was performed.

Fix text/background contrast tokens and disabled/action affordances, then rerun all supported screens and responsive states. Also test visible keyboard focus, tab order, status announcements, errors, expiry, zoom and screen-reader naming. Automated success is not a complete WCAG conformance claim. [WCAG 2.2 understanding documents](https://www.w3.org/WAI/WCAG22/understanding/).

## Commercial readiness boundary

Local cryptography, OIDC, protocol fixtures and dashboards can be completed with existing resources. Real provider onboarding, trusted-agent/network enrollment, external merchant interoperability, a supported hosted inference arrangement, production infrastructure and independent reviews remain separate prerequisites. Open-source dependency licenses and Visa's distinct product terms need accurate attribution/handling; a public repository is not itself a blanket reuse license. The owner has not selected a distribution license for the application.
