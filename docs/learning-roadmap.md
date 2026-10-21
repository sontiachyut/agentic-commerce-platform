# Just-in-time learning roadmap

Read/teach only what the next approved task requires, inspect pinned source/tests, predict failure and verify it. Future approval permits Codex implementation within that milestone, followed by explanation and understanding review.

| Before milestone | Learn now | Concrete exercise / authoritative source |
| --- | --- | --- |
| M0 | Purchase authority versus processor hold; seven independent states | Walk AC-07 without treating payment/fulfillment as one status; [source analysis](reference-analysis.md) |
| M1 | Python typing/exceptions/async, FastAPI/Pydantic, SQL transactions/session/Alembic, pytest | Persist session then restart; [Python](https://docs.python.org/3/tutorial/), [FastAPI async](https://fastapi.tiangolo.com/async/), [SQLAlchemy transactions](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html) |
| M2 | Catalog IDs/attributes, integer money, immutable quote, stock/reservation/order | Explain why “1 available” is not a reserved item; Medusa complete-cart/reserve/inventory sources |
| M3 | LangGraph state/reducers/nodes, model schema/refusal, tokens/context, bounded execution | Fake looping provider; stop safely without a purchase; [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview) |
| M4 | Tool contracts and authorized dispatch, semantic validation, prompt injection | Schema-valid request for wrong kiosk must fail; [OpenAI function calling](https://developers.openai.com/api/docs/guides/function-calling) |
| M5 | Trusted approval, identity, exact hash/version/nonce binding, signing versus consent | Price changes after approval; explain why a chat “yes” alone is insufficient; AP2 chain/constraint/key-binding tests |
| M6 | Local atomic stock/budget/order acceptance, saga, external uncertainty/idempotency | Last-item race and effect-then-response-loss; Medusa fulfillment failure test, [PostgreSQL locks](https://www.postgresql.org/docs/current/explicit-locking.html) |
| M7 | Delegated scope, usage reservations, revocation linearization, replay | Two 400-unit purchases under 700-unit budget; revoke after acceptance; [authority design](authorization-and-mandates.md) |
| M8 | Checkpoint versus business effect, interrupt replay, jobs/leases/fences and saver ownership | Resume with missing graph state but existing payment; [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) |
| M9 | Versioned event/API contracts, inbox/outbox, separate compensation facts | Capture unknown after confirmed dispense; [shared sequences](payment-integration-contracts.md) |
| M10 | Oracle leakage, multi-valid labels, policy versus agent metrics, latency/cost/queue denominators, safe tracing | Compare rule/fixed/agent results and include blocked invalid proposals; [evaluation plan](evaluation-plan.md), [OTel concepts](https://opentelemetry.io/docs/concepts/) |
| Optional M11 | Pinned protocol semantics/conformance, trust enrollment, isolation and explicit standards scope | Show which requirements and negative tests prove a narrow compatibility claim; UCP/ACP/TAP/AP2 selective comparison |

## Token/provider fundamentals before a real model

Tokens are model-specific encoded units, not fixed words/characters. Context includes instructions, tool schemas/results, retained observations and output subject to model/provider limits. Budget all of them and keep decisive facts/contradictions instead of blindly concatenating descriptions. Schema conformance does not establish truth, source trust or spending permission. Record actual model ID, limits, token usage and price snapshot after approval; no permanent “best model” or fixed dollar estimate is invented now.

First implementation recommendation: approve M1 and build one durable purchase-session/read boundary, then explain transaction/restart behavior. Do not begin full autonomous purchasing. Complete M6's human-approved vertical slice before M7 delegation.

Defer GPU/model training, multi-agent delegation, vector databases, MCP, Kubernetes, OpenFGA and Temporal until a concrete requirement/evaluation justifies them. Neither sophisticated orchestration nor protocol badges replace correct stock/authority/effect identity.
