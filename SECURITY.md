# Security

This release accepts loopback clients and synthetic data only. It deliberately refuses non-demo configuration. Do not expose the API, source simulator or PostgreSQL to a public network, and do not place real customer, payment or identity data in this demonstration.

Report a suspected issue privately to the repository owner through the repository's private vulnerability-reporting channel if available. Do not publish credentials or exploit payloads containing customer information. If no private reporting channel is configured, request a private contact route without posting sensitive details.

The [threat model](docs/threat-model.md) describes implemented boundaries and known gaps. Real payment processing, AP2/UCP/ACP/TAP certification, enterprise identity, hosted subscription-backed inference and production operational assurances are not provided by v0.1.
