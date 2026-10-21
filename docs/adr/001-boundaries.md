# ADR 001 — Six logical components, one initial business application

**Status:** proposed. Separate agent, commerce, policy, payment integration, durable work and UI/observability responsibilities without immediately deploying six services. One FastAPI commerce DB/transaction boundary plus serialized graph runner is sufficient initially; Java owns its independent DB/API.

Microservices add release autonomy but increase distributed identity/failure/operations cost; monolithic unstructured agent tools let policy leak. Choose explicit module/port ownership, independent source simulators and no shared DB. Extract only after measured isolation/scaling/ownership need. Validate independent demos and AC/PS contract corpus; Medusa module richness is a reference, not a required port.
