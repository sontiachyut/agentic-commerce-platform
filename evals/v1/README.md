# Shopping decisions v1

Original synthetic requests and manually specified expectations, generated from 20 explicit scenario families with five surface variations each. This is a small engineering regression corpus, not a human-reviewed representative commerce benchmark. All variants of one family stay in one split; holdout labels are never passed to the model. The catalog is frozen independently of the running demonstration's inventory.

The runner scores intent extraction, clarification/refusal, valid-set selection and request constraints. Workflow order is fixed by the graph and is **not** reported as model tool-selection accuracy. Source recovery and authorization are separate integration tests. No evaluation sends a purchase or claims delivery. Rule-baseline results and actual model results remain separate.

Run `uv run python tools/evaluate.py --provider baseline`. A bounded signed-in run uses `--provider codex --split holdout --limit 3`; it reserves calls in the normal application's durable daily allowance before inference. Results append to a unique directory. A partial run is resumable by its directory; unsuccessful decisions remain failures, not silently retried. The model never receives expected fields or valid product IDs from the oracle.
