# Ontology Writeback Ledger

Independent GlacierEQ reference implementation for controlled typed-object mutation.

> **Not affiliated.** This project is not affiliated with, endorsed by, or deployed at Palantir.

## Purpose

A writeback boundary should not accept “the agent said it was authorized” as provenance. It must independently establish:

- the object and exact base state being changed;
- the schema version in force;
- the exact typed diff;
- who proposed it and under what declared authority;
- required sign-off;
- replay identity and ledger parent;
- whether the mutation can be reversed; and
- whether the side-effect authorization actually descends from a complete causal action lineage.

This repository owns that transactional boundary.

## Core ledger

`OntologyWritebackLedger` provides:

- deterministic object snapshots and diff fingerprints;
- schema-drift and stale-base refusal;
- typed `set` / `delete` operations with bounded path syntax and operation count;
- HUMAN_AGENT or TWO_AGENT sign-off modes;
- required proposer and authority metadata;
- one-shot diff IDs after a structurally valid attempt;
- parent-ledger consistency;
- atomic batch rollback;
- reverse-diff generation;
- deterministic audit hashes.

The existing `apply(diff)` path remains available for systems whose authority/provenance boundary is external to this repository.

## Action-lineage integration

`apply_authorized(diff, lineage_proof)` is the stronger composed path.

The consumer verifies the serialized `glaciereq.action-lineage-proof.v1` bundle **without importing or trusting the producer process**. It recomputes:

- the outer proof digest;
- every node fingerprint;
- parent closure;
- root/non-root shape;
- cycle freedom;
- side-effect attestation presence;
- reachability of every supplied node;
- the complete lineage fingerprint.

The SIDE_EFFECT tip must then bind the exact ledger writeback:

- object type and ID;
- `WritebackDiff.fingerprint()`;
- proposer;
- authority;
- schema fingerprint;
- current parent ledger hash;
- `authorized: true`.

Any mismatch is refused **before** normal writeback execution. A rejected external proof is audit-recorded but does not mutate the object, reserve the diff ID, or advance the ledger tip. A corrected proof can retry the same otherwise-valid immutable diff.

Producer contract: `GlacierEQ/palantir-action-lineage-graph`.

## Real cross-repository proof

The CI integration job clones the Action Lineage Graph at exact accepted commit:

```text
1f19f1de737d2c499027918a256978efdcc91aad
```

It then:

1. creates an ontology `WritebackDiff` against the current ledger tip;
2. commits observation → transform → SIDE_EFFECT in the sibling lineage implementation;
3. exports the complete proof from the sibling repository;
4. self-verifies it with the producer;
5. passes only the serialized proof into this repository;
6. independently verifies the bundle and its writeback bindings;
7. transactionally applies the diff;
8. asserts the object actually changed.

Run the same integration locally:

```bash
git clone https://github.com/GlacierEQ/palantir-action-lineage-graph.git /tmp/action-lineage
git -C /tmp/action-lineage checkout 1f19f1de737d2c499027918a256978efdcc91aad
python scripts/operate.py --lineage-repo /tmp/action-lineage
```

Unit tests:

```bash
python -m unittest discover -s tests -v
```

## Truth boundary

This repository verifies causal proof integrity and exact writeback binding. The lineage producer’s `attestation` value is metadata, not a cryptographic identity assertion. External actor identity/signature authentication remains outside these two repositories unless a real authority provider is connected later.

The library also does not call proprietary ontology APIs or persist to a remote service. Its natural current form is a deterministic writeback engine and cross-repository protocol implementation. Those boundaries are explicit rather than being disguised as deployment success.
