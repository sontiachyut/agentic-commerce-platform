# ADR 002 — Human-first deterministic purchasing authority

**Status:** proposed. User intent is not permission, agent identity is not consent, processor authorization is not a grant. Start exact trusted human approval bound to immutable quote/user/agent/merchant/item/amount/expiry; delegated grants come only after complete human slice.

Prompts-only restrictions or signed-but-unconsumed tokens cannot enforce concurrent budget/replay/revocation. Choose server-owned policy/usage/nonce with atomic execution acceptance and explicit in-flight revocation semantics. Established signatures can protect service boundary binding later; private signer never exposed to agent. Tradeoff: stricter reapproval and honest uncertainty rather than convenient silent scope expansion. AC-01/02/03/06/10 required.
