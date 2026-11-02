"""What a verdict was computed from, so a recorded verdict can be matched to the files later."""
from __future__ import annotations

import datetime
import hashlib
from pathlib import Path

from . import __version__
from .claims import lean_path

# Dates and versions describe the run; only these identify what was checked.
MATCHED = ("claim_sha256", "lean_sha256", "assumptions_sha256", "toolchain", "manifest_sha256", "core_sha256")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _file_sha(path: Path) -> str | None:
    return _sha(path.read_bytes()) if path.is_file() else None


def _core_sha(lake_root: Path) -> str | None:
    """The Lean library every claim imports, the verifier and the build file."""
    files = [lake_root / "ClaimCert.lean", *sorted((lake_root / "ClaimCert").glob("*.lean")),
             lake_root / "Verify.lean", lake_root / "lakefile.toml"]
    files = [f for f in files if f.is_file()]
    if not files:
        return None
    blob = b"".join(f.relative_to(lake_root).as_posix().encode() + b"\0" + f.read_bytes().replace(b"\r\n", b"\n")
                    for f in files)
    return _sha(blob)


def _module_sha(lake_root: Path, reg) -> str | None:
    """The assumption module Lean reads, hashed from disk rather than from what the registry generates."""
    if reg is None:
        return None
    return _file_sha(lake_root.joinpath(*reg.lean_module.split(".")).with_suffix(".lean"))


def fingerprint(claim_path, reg, lake_root) -> dict:
    claim_path, lake_root = Path(claim_path), Path(lake_root)
    toolchain = lake_root / "lean-toolchain"
    return {
        "claim_sha256": _file_sha(claim_path),
        "lean_sha256": _file_sha(lean_path(claim_path)),
        "assumptions_sha256": _module_sha(lake_root, reg),
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
