# Evaluation and reliability research

## Evaluate decisions and effects separately

The existing graph fixes the tool sequence. The model interprets intent and chooses a candidate; it does not choose an arbitrary next tool. A correct fixed sequence is not model tool-selection accuracy. Evaluate supported intent fields, valid-set selection, appropriate clarification and task outcome separately from backend policy enforcement.

Tau-bench evaluates the final database state against the intended result and studies repeated-run reliability. Tau2's environment evaluator compares replayed predicted and reference environment states; its evaluator separates environment, action and communication criteria. AgentDojo separately evaluates user-task utility and attack success from outputs, state and traces. Adopt those distinctions, not their full runtime or datasets. [Tau-bench paper](https://arxiv.org/abs/2406.12045), [Tau2 evaluator](https://github.com/sierra-research/tau2-bench/blob/033bf082f48e4a3c6a1256208e93cf2ce9c3bb6f/src/tau2/evaluator/evaluator.py), [AgentDojo task suite](https://github.com/ethz-spylab/agentdojo/blob/089ed468cf3ed0322acc66b0211f26d9d90dbf60/src/agentdojo/task_suite/task_suite.py).

The useful four-way result is: task succeeded/safe; task failed/safe; task succeeded/unsafe; task failed/unsafe. A backend-blocked invalid purchase belongs in task-failed/safe. A model that does nothing is not useful simply because no unsafe action occurred.

## Corpus and oracle

Create a versioned synthetic corpus with named scenario families, fixed catalog snapshots, independently specified eligible product sets, expected constraints and allowed stop/outcome states. Include strict/inclusive limits, exact-price boundaries, missing budget/item, unsupported currency/quantity, no match, flavor preference, merchant/product scope, stale quote, revoked authority, prompt injection and source uncertainty.

Keep development, holdout and adversarial families separate. Similar paraphrases stay in the same family/split. Expected IDs, hidden fault state and labels must not leak into model prompts, paths or merchant descriptions. Selection may have multiple valid answers. Missing evidence for a requested attribute requires clarification or no match, not an invented product property.

Use deterministic oracles for money, identity, policy, tool arguments and database effects. Reserve manual review for preference/clarification quality; do not let an uncalibrated model judge become ground truth. Corpus generation is not independent human validation. Record label provenance/review status and do not call a machine-authored set human-reviewed.

## Evaluation lanes

| Lane | What runs | What it proves |
| --- | --- | --- |
| Deterministic | Backend/source/agent fixtures, schema and crypto cases | Tested invariants and failure behavior |
| Rule baseline | Same shopping corpus without an LLM | Mechanics and a comparison baseline |
| Real model | Bounded actual Codex interpretation/selection, same visible data | Measured model behavior for recorded cases/settings |
| Capacity | No-model HTTP/source traffic against isolated disposable databases | API/database/worker capacity under the declared workload |
| Browser/accessibility | User journeys, keyboard/viewport and automated scans | Tested experience, not full standards certification |

Use existing durable model-call reservations, deadlines and explicit retry. Do not hide failures by rerunning until successful. Resume a partially completed evaluation from an append-only run ledger; no skipped failed cases or denominator changes. Record configured/reported model, CLI version, prompt/schema/graph/catalog/corpus/source/policy revisions, commit, times and token metadata. If actual model snapshot is unavailable, disclose that reproducibility limit.

The local daily cap is an application safeguard, not an asserted subscription entitlement. Real-model coverage must fit the actual available allowance and may span days. Creating a 100-case dataset does not mean 100 real-model runs have completed. No paid judge or user-simulator API is required for the first harness.

## Reliability and execution

A checkpoint persists graph progress, not external payment/fulfillment atomicity. Keep stock/budget/order/job acceptance in one commerce transaction and all remote calls outside held row locks. Source commands need stable business identities and inquiry. Stage/version and lease-token checks reject stale workers; global graph serialization is not distributed fencing under arbitrary partitions. [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence), [PostgreSQL 17 locks](https://www.postgresql.org/docs/17/explicit-locking.html).

Add failure injection at boundaries: after acceptance commit, after remote effect before response, after observation before checkpoint, before/after job completion, during approval, after grant revocation and while old workers resume. Restore tests must preserve independent source knowledge. Unknown source state retains holds; human approval expiry does not retroactively undo accepted financial effects.

Transport nonce replay rejection and business retries must coexist. A client can use a fresh signed envelope around the same idempotent request. A cached accepted result must never become a new order, and a changed body/key binding must conflict. Exercise this through each protocol adapter, not only the internal service.

## Reporting

Publish raw counts, case IDs/families, all scheduled outcomes, model versus backend failures, cold/warm timings and repeated-run variability. Use p50/p95/p99 only with the sample size and workload stated. Do not convert a small smoke run into an accuracy or availability claim. The earlier 54 backend tests and one live purchase remain the application evidence until the new suite actually runs.
