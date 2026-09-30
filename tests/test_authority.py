"""Auto-generated tests for Enterprise Data Platform & Authority Governance."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from palantir_ontology_writeback_ledger.core import Permission, DataObject, AuthorityMatrix, IntentCompiler

def test_data_lineage():
    obj = DataObject("d1", "table", "owner1")
    obj.add_lineage("source_a")
    obj.add_lineage("source_b")
    assert obj.lineage_depth == 2

def test_no_duplicate_lineage():
    obj = DataObject("d1", "table", "owner1")
    obj.add_lineage("source_a")
    obj.add_lineage("source_a")
    assert obj.lineage_depth == 1

def test_authority_grant_check():
    am = AuthorityMatrix()
    am.grant("user1", "table_a", Permission.READ)
    assert am.check("user1", "table_a", Permission.READ)
    assert not am.check("user1", "table_a", Permission.WRITE)

def test_authority_revoke():
    am = AuthorityMatrix()
    am.grant("user1", "obj1", Permission.ADMIN)
    am.revoke("user1", "obj1", Permission.ADMIN)
    assert not am.check("user1", "obj1", Permission.ADMIN)

def test_audit_log():
    am = AuthorityMatrix()
    am.grant("user1", "t1", Permission.READ)
    am.grant("user1", "t2", Permission.WRITE)
    log = am.audit_log("user1")
    assert "t1" in log
    assert "t2" in log

def test_intent_compiler():
    ic = IntentCompiler()
    ic.register_rule("search", lambda i: {{"action": "SEARCH", "query": i}})
    result = ic.compile("search for anomalies")
    assert result is not None
    assert result["action"] == "SEARCH"

def test_intent_compiler_no_match():
    ic = IntentCompiler()
    assert ic.compile("unknown intent") is None

