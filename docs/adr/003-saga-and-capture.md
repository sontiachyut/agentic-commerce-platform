# ADR 003 — Reserve locally, authorize, dispense, capture

**Status:** proposed. Reserve stock/budget and create one order/job in a local transaction before external authorization. Default manual-capture sequence authorizes, confirms dispense, then captures. Unknown effects hold resources and trigger inquiry.

Capturing first simplifies payment-before-goods but requires refunds for failed dispense; dispensing before capture avoids known-failure charges but can leave dispensed goods with failed/unknown capture. No distributed transaction solves both. Choose default plus explicit early-capture fixture, deterministic linked compensation and visible recovery-required states. Never redispense/auto-refund unknown fulfillment or give model raw financial tools. AC-04/05/07/08 and all linked payment scenarios prove assumptions.
