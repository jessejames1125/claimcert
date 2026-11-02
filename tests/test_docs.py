"""The rules a stranger's first read depends on, kept from drifting."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ONE_LINER = "Check AI-written numeric claims with Lean's kernel; every pass lists the assumptions its proof used."
# Assembled from parts so this file does not itself contain the words it forbids.
BANNED = ["power" + "ful", "seam" + "less", "compre" + "hensive", "rob" + "ust", "blaz" + "ing", "revolu" + "tionary",
          "production" + "-ready"]
DASHES = [chr(0x2013), chr(0x2014)]


def public_text() -> list[Path]:
    out = [ROOT / "README.md", ROOT / "CHANGELOG.md", ROOT / "HISTORY.md", ROOT / "pyproject.toml"]
    for folder in ("docs", ".github", "evals"):
        out += [p for p in (ROOT / folder).rglob("*") if p.suffix in (".md", ".yml", ".py")]
    return out


def test_one_liner_is_the_same_everywhere_and_short():
    assert len(ONE_LINER.split()) <= 20
    assert ONE_LINER in (ROOT / "README.md").read_text(encoding="utf-8")
    assert ONE_LINER in (ROOT / "pyproject.toml").read_text(encoding="utf-8")


def test_readme_stays_under_budget():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    assert len(text.split()) <= 1500
    before_code = text.split("```")[0]
    assert len(before_code.split()) <= 150
    assert "![" in " ".join(text.split()[:80])


def test_no_banned_words_or_long_dashes():
    for path in public_text():
        text = path.read_text(encoding="utf-8")
        low = text.lower()
        assert not [w for w in BANNED if w in low], path
        assert not [d for d in DASHES if d in text], path


def test_no_emoji_headings():
    for path in public_text():
        if path.suffix == ".md":
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.startswith("#"):
                    assert line.isascii(), (path, line)


def test_root_stays_small():
    tracked = {p.name for p in ROOT.iterdir()} - {".git", ".venv", ".pytest_cache", "build"}
    assert len(tracked) <= 15, sorted(tracked)
    assert not tracked & {"PLAN.md", "NOTES.md", "TODO.md", "CLAUDE.md", "AGENTS.md", "HANDOFF.md", ".claude"}


def test_history_note_is_dated():
    assert re.search(r"\d{4}-\d{2}-\d{2}: Developed privately", (ROOT / "HISTORY.md").read_text(encoding="utf-8"))


def test_one_license_and_it_is_apache():
    assert "Apache License" in (ROOT / "LICENSE").read_text(encoding="utf-8")
