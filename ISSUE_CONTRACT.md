# ISSUE CONTRACT

## Pain
Consequential object writebacks can silently apply against stale state, drifted schemas, weak sign-off, or ambiguous transaction history. A mutation path that cannot prove what state it changed and how rollback works is not trustworthy.

## Success
- Object snapshots bind object identity, properties, and schema fingerprint.
- Diff IDs are explicit one-shot attempt identities.
- Parent-ledger mismatch refuses apply.
- Schema mismatch refuses apply.
- Stale base state refuses apply.
- HUMAN+AGENT or TWO_AGENT sign-off is enforced according to configured mode.
- Empty or malformed diff metadata/operations refuse closed.
- Multi-object batches are all-or-nothing and preserve a refusal receipt on rollback.
- Reverse diffs support explicit undo.
- Applied and refused decisions emit deterministic ledger receipts.

## Explicit boundary
- The `authority` field must be present, but this repository does not authenticate external authorization policy; that belongs to the authority plane.
- External action provenance is not validated here; that belongs to the lineage plane.
- Current state storage is in-memory; no external durable database or production provider writeback is claimed.
