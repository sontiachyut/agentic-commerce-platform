# Contributing

Read [current status](docs/STATUS.md), [runtime architecture](docs/runtime-architecture.md), [threat model](docs/threat-model.md) and the relevant [acceptance scenario](docs/production-scenarios.md) before changing behavior.

Work on a branch. Keep one business problem per change and add tests that assert the relevant invariant rather than private implementation details. Use the locked Python and Node dependencies. Run the checks listed in the README. Review schema migrations as production changes; application startup must not migrate the commerce schema automatically.

Keep `.env`, `.local`, authorization material, real payment data and customer information out of commits, screenshots and issue reports. Use synthetic fixtures. Do not add real payment or model API credentials to CI. The normal test suite must not require an account or consume a model allowance.

Model changes require a versioned prompt, corpus and measured results. A backend rejection is a successful safety control but can still be an unsuccessful agent run. Protocol claims require pinned schemas and positive/negative conformance evidence. Current interoperability limitations are recorded in [protocol support](docs/protocol-support.md).

No production deployment, paid resource, real transaction or licensing change is part of a routine contribution. A local test passing is not evidence of production scale or regulatory certification.
