from pathlib import Path

import yaml

from claimcert.cli import main

FIX = Path(__file__).parent / "fixtures"


def bad_claim(tmp_path) -> Path:
    p = tmp_path / "c_bad.yaml"
    p.write_text(yaml.safe_dump({"name": "c_bad", "type": "bound", "intent": "x",
                                 "variables": {"z": "m"}, "goals": ["z <= 1"]}), encoding="utf-8")
    return p


def test_schema_error_is_clean_exit_1(tmp_path, capsys):
    rc = main(["new", str(bad_claim(tmp_path)), "--registry", str(FIX / "registry.yaml")])
    err = capsys.readouterr().err
    assert rc == 1
    assert err.startswith("error: ") and "Traceback" not in err


def test_registry_error_is_clean_exit_1(tmp_path, capsys):
    reg = tmp_path / "reg.yaml"
    reg.write_text("- just\n- a list\n", encoding="utf-8")
    rc = main(["gen-assumptions", "--registry", str(reg), "--out", str(tmp_path / "o.lean")])
    assert rc == 1 and capsys.readouterr().err.startswith("error: ")


def test_existing_file_is_clean_exit_1(tmp_path, capsys):
    dst = tmp_path / "fx_pass.yaml"
    dst.write_text((FIX / "claims" / "fx_pass.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    reg = str(FIX / "registry.yaml")
    assert main(["new", str(dst), "--registry", reg]) == 0
    assert main(["new", str(dst), "--registry", reg]) == 1
    assert "error: " in capsys.readouterr().err


def test_audit_schema_error_is_clean_exit_1(tmp_path, capsys):
    rc = main(["audit-pack", str(bad_claim(tmp_path)), "--registry", str(FIX / "registry.yaml")])
    assert rc == 1 and capsys.readouterr().err.startswith("error: ")


def test_malformed_yaml_is_clean_exit_1(tmp_path, capsys):
    p = tmp_path / "c_bad.yaml"
    p.write_text("name: [c_bad\n", encoding="utf-8")
    rc = main(["new", str(p), "--registry", str(FIX / "registry.yaml")])
    err = capsys.readouterr().err
    assert rc == 1 and err.startswith("error: ") and "Traceback" not in err


def test_infinite_quantity_is_clean_exit_1(tmp_path, capsys):
    p = tmp_path / "c_inf.yaml"
    p.write_text("name: c_inf\ntype: point\nintent: x\nconstants: {C: 'inf m'}\ngoals: ['C <= C']\n", encoding="utf-8")
    rc = main(["new", str(p), "--registry", str(FIX / "registry.yaml")])
    assert rc == 1 and capsys.readouterr().err.startswith("error: ")
