# ISSUE CONTRACT

## Pain
Agent/FDE writebacks silently reshape ontology objects; schema drift and missing lineage make undo and audit impossible.

## Success
- Diffs are typed and hash-chained
- Schema fingerprint mismatch refuses apply
- Dual sign-off modes: HUMAN+AGENT or TWO_AGENT (configurable)
- Ledger is append-only and replayable
