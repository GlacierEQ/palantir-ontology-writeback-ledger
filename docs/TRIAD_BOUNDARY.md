# Palantir-Lens Triad Boundary

The three repositories are intentionally orthogonal control planes.

## 1. Action Lineage Graph
Question: **Why is this proposed action allowed to exist in the causal chain?**

Owns action ancestry, parent existence, side-effect attestation, cycle/depth/parent limits, reachability, and lineage fingerprints.

Does not own actor/object authorization or durable object mutation.

## 2. Object Authority Matrix
Question: **Who may attempt what verb on what object type?**

Owns default-deny `(actor_role, object_type, verb)` authorization and deterministic authorization decisions.

Does not own action ancestry or writeback transaction semantics. Property/effect/time-limited authority is future scope unless separately proven.

## 3. Ontology Writeback Ledger
Question: **How does an authorized intended change become state safely?**

Owns exact-state transactional mutation: typed diffs, schema/base checks, local sign-off, one-shot diff identity, parent-tip consistency, atomic rollback, reverse diffs, and deterministic ledger receipts.

Does not authenticate external authorization and does not validate external action lineage today.

## Intended future composition

`proposal → lineage receipt → authority receipt → transactional writeback → post-write readback/receipt → new lineage node`

Every inter-repository edge remains `REFERENCE_COMPLEMENT_NOT_INTEGRATED` until an executable integration test proves the composed path.
