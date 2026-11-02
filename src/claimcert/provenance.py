"""What a verdict was computed from, so a recorded verdict can be matched to the files later."""
from __future__ import annotations

import datetime
import hashlib
from pathlib import Path

from . import __version__
from .claims import lean_path
from .registry import lean_assumptions

# Dates and versions describe the run; only these identify what was checked.
MATCHED = ("claim_sha256", "lean_sha256", "assumptions_sha256", "toolchain", "manifest_sha256", "core_sha256")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _file_sha(path: Path) -> str | None:
    return _sha(path.read_bytes()) if path.is_file() else None


def _core_sha(lake_root: Path) -> str | None:
    """The Lean library every claim imports. The report command and the definitions live here."""
    files = sorted((lake_root / "ClaimCert").glob("*.lean"))
    if not files:
        return None
    blob = b"".join(f.name.encode() + b"\0" + f.read_bytes().replace(b"\r\n", b"\n") for f in files)
    return _sha(blob)


def fingerprint(claim_path, reg, lake_root) -> dict:
    claim_path, lake_root = Path(claim_path), Path(lake_root)
    toolchain = lake_root / "lean-toolchain"
    return {
        "claim_sha256": _file_sha(claim_path),
        "lean_sha256": _file_sha(lean_path(claim_path)),
        "assumptions_sha256": _sha(lean_assumptions(reg).encode("utf-8")) if reg is not None else None,
        "toolchain": toolchain.read_text(encoding="utf-8").strip() if toolchain.is_file() else None,
        "manifest_sha256": _file_sha(lake_root / "lake-manifest.json"),
        "core_sha256": _core_sha(lake_root),
        "claimcert": __version__,
        "date": datetime.datetime.now(datetime.timezone.utc).date().isoformat(),
    }


def differences(recorded: dict | None, current: dict) -> list[str]:
    """Names of the inputs that changed since the verdict was recorded."""
    recorded = recorded or {}
    return [k for k in MATCHED if recorded.get(k) != current.get(k)]
