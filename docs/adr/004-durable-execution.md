# ADR 004 — Business state survives independently of graph checkpoints

**Status:** proposed. Persist execution/order/authority usage/payment links/dispense identity and job intent before effects. Graph has per-run thread/checkpoint and replay-safe logical tools, not financial authority. Start serialized; human/source wait ends worker and resumes later.

Checkpoint-only state loses business identity at external gaps; broker-only jobs can disappear; leases/advisory lock on one connection do not fence saver writes on another. Parallel takeover requires tested owner/fence check in same transaction as all saver mutations, or remains disabled. DB runner first; Celery/Redis only when useful, with DB intent/reconciliation. Temporal is an alternative after demonstrated requirement. Some provider/model calls may repeat; account for cost honestly. AC-08 is a kill/pause/connection-loss corpus, not one happy restart.
