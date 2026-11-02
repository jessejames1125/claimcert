import shutil
from pathlib import Path

from claimcert.audit import audit_pack, audit_record, audit_status
from claimcert.claims import load_claim
from claimcert.registry import load_registry

FIX = Path(__file__).parent / "fixtures"
REG = load_registry(FIX / "registry.yaml")


def staged(tmp_path):
    dst = tmp_path / "fx_pass.yaml"
    shutil.copy(FIX / "claims" / "fx_pass.yaml", dst)
    return dst


def test_pack_hides_intent_and_shows_defs(tmp_path):
    claim = load_claim(staged(tmp_path), REG)
    text = audit_pack(claim, REG).read_text(encoding="utf-8")
    assert "def A_fx_cap" in text and "theorem claim " in text
    assert "fx_pass" not in text  # a name such as ..._wrong would give the answer away
    assert claim.intent not in text
    assert "example :" not in text


def test_status_cycle(tmp_path):
    p = staged(tmp_path)
    claim = load_claim(p, REG)
    assert audit_status(claim, REG) == "UNAUDITED"
    audit_record(claim, REG, True, "agent", "back-translation matches")
    assert audit_status(claim, REG) == "MATCH"
    audit_record(claim, REG, False, "operator", "says 5 m, intent says 4 m")
    assert audit_status(claim, REG) == "MISMATCH"
    p.write_text(p.read_text(encoding="utf-8").replace('"400 cm"', '"500 cm"'), encoding="utf-8")
    assert audit_status(load_claim(p, REG), REG) == "STALE"


def test_assumption_change_makes_match_stale(tmp_path):
    p = staged(tmp_path)
    claim = load_claim(p, REG)
    audit_record(claim, REG, True, "agent", "matches")
    reg_path = tmp_path / "reg.yaml"
    reg_path.write_text((FIX / "registry.yaml").read_text(encoding="utf-8").replace('"300 cm"', '"350 cm"'),
                        encoding="utf-8")
    reg2 = load_registry(reg_path)
    assert audit_status(load_claim(p, reg2), reg2) == "STALE"


def test_record_without_new_hash_is_stale(tmp_path):
    p = staged(tmp_path)
    claim = load_claim(p, REG)
    rec = audit_record(claim, REG, True, "agent", "matches")
    rec.write_text('{"statement_sha256": "abc", "match": true}', encoding="utf-8")
    assert audit_status(claim, REG) == "STALE"


def test_corrupt_record_is_stale(tmp_path):
    p = staged(tmp_path)
    claim = load_claim(p, REG)
    rec = audit_record(claim, REG, True, "agent", "matches")
    rec.write_text('{"audit_sha256": ', encoding="utf-8")
    assert audit_status(claim, REG) == "STALE"


def test_cylinder_definition_is_the_core_one():
    from claimcert.audit import CYLINDER_DEF
    geometry = (Path(__file__).resolve().parents[1] / "lean" / "ClaimCert" / "Geometry.lean").read_text(encoding="utf-8")
    assert CYLINDER_DEF in geometry


def test_intent_change_makes_match_stale(tmp_path):
    p = staged(tmp_path)
    claim = load_claim(p, REG)
    audit_record(claim, REG, True, "agent", "matches")
    p.write_text(p.read_text(encoding="utf-8").replace(claim.intent, "a different claim"),
                 encoding="utf-8")
    edited = load_claim(p, REG)
    assert edited.intent == "a different claim"
    assert audit_status(edited, REG) == "STALE"
