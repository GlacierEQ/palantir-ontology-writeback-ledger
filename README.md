# Ontology Writeback Diff Ledger

**Problem space:** ontology-centric operational platforms (Palantir-class public design lens)  
**Innovation:** typed object diffs are admitted only against the expected schema and base state, under configured sign-off, then applied through a hash-linked transactional ledger with rollback and reverse-diff support.

## Current mechanism

This repository owns the **transactional writeback boundary**:

- exact object snapshot + schema fingerprint binding;
- parent-ledger consistency checks;
- stale-base refusal;
- top-level typed diff validation;
- configurable HUMAN+AGENT or TWO_AGENT sign-off;
- one-shot diff identities;
- deterministic applied/refused receipts;
- all-or-nothing batch rollback with a retained refusal receipt;
- reverse-diff generation for explicit undo.

The current implementation is an **in-memory reference mechanism**. Its `authority` field is declared metadata and its sign-off policy is local; this repository does not authenticate a separate external authorization decision. It also does not currently consume an external action-lineage proof.

## Mesh boundary

The three Palantir-lens controls remain deliberately separate:

`action proposal → Action Lineage Graph (provenance) → Object Authority Matrix (authorization) → Ontology Writeback Ledger (transactional mutation) → receipt/readback`

`palantir-action-lineage-graph` and `palantir-object-authority-matrix` are complementary references only. No exercised integration is claimed.

## Verification

```bash
python3 -m unittest discover -s tests -v
```

## Claim ceiling

Independent GlacierEQ reference implementation exploring a public problem shape. No Palantir affiliation, employment, deployment, contract, endorsement, clearance, proprietary access, internal architecture knowledge, or production use is claimed.

## Quality honesty

The repository previously suffered a source regression in which automation truncated the ledger implementation while tests and higher-level descriptions survived. `machine/canonical-position.json` records that lineage. Canonical promotion requires restored exact-source proof, not prose continuity.
