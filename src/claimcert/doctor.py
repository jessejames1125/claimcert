"""doctor says what is missing; setup fetches it. Neither changes anything outside lean/.lake."""
from __future__ import annotations

import ctypes
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

CHECK_PEAK_GB = 4.6  # measured: one check, Lean with Mathlib imported
LEAN_DISK_GB = 15.0  # measured: lean/.lake after setup on a clean copy, plus room for the download


@dataclass
class Row:
    name: str
    ok: bool
    detail: str
    needed_for: str  # replay | kernel


def memory_gb() -> tuple[float, float] | None:
    """(total, available) in GB, or None where this platform gives no cheap answer."""
    if sys.platform == "win32":
        class Status(ctypes.Structure):
            _fields_ = [("length", ctypes.c_ulong), ("load", ctypes.c_ulong), ("total", ctypes.c_ulonglong),
                        ("avail", ctypes.c_ulonglong), ("pt", ctypes.c_ulonglong), ("pa", ctypes.c_ulonglong),
                        ("vt", ctypes.c_ulonglong), ("va", ctypes.c_ulonglong), ("ve", ctypes.c_ulonglong)]
        status = Status()
        status.length = ctypes.sizeof(Status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.total / 2**30, status.avail / 2**30
        return None
    try:
        fields = dict(line.split(":") for line in Path("/proc/meminfo").read_text().splitlines() if ":" in line)
        return (int(fields["MemTotal"].split()[0]) / 2**20, int(fields["MemAvailable"].split()[0]) / 2**20)
    except (OSError, KeyError, ValueError):
        return None


def _exists(path: Path, label: str, missing: str) -> Row:
    return Row(label, path.is_file(), "built" if path.is_file() else missing, "kernel")


def diagnose(root: Path, which=shutil.which) -> list[Row]:
    lean = root / "lean"
    version = ".".join(map(str, sys.version_info[:3]))
    rows = [Row("python", sys.version_info >= (3, 11), f"{version} (needs 3.11 or newer)", "replay")]
    try:
        import yaml
        rows.append(Row("pyyaml", True, yaml.__version__, "replay"))
    except ImportError:
        rows.append(Row("pyyaml", False, "not installed; run pip install .", "replay"))
    rows.append(Row("examples", (root / "examples").is_dir(), "found" if (root / "examples").is_dir()
                    else "run this inside a claimcert checkout", "replay"))
    elan = which("elan")
    rows.append(Row("elan", elan is not None, "found" if elan else
                    "install from https://lean-lang.org/install/ (Lean's toolchain manager)", "kernel"))
    pin = (lean / "lean-toolchain").read_text(encoding="utf-8").strip() if (lean / "lean-toolchain").is_file() else "?"
    if elan:
        listed = subprocess.run([elan, "toolchain", "list"], capture_output=True, text=True, cwd=root.anchor)
        have = pin.replace("/", "--").replace(":", "---") in listed.stdout
        rows.append(Row("toolchain", True, f"{pin} {'installed' if have else 'will download on first use, about 500 MB'}",
                        "kernel"))
    build = lean / ".lake" / "packages"
    missing = "not built; run claimcert setup"
    rows.append(_exists(build / "mathlib" / ".lake" / "build" / "lib" / "lean" / "Mathlib.olean", "mathlib", missing))
    rows.append(_exists(build / "leancert" / ".lake" / "build" / "lib" / "lean" / "LeanCert" / "Tactic.olean",
                        "leancert", missing))
    rows.append(_exists(lean / ".lake" / "build" / "lib" / "lean" / "ClaimCert.olean", "claimcert lean", missing))
    mem = memory_gb()
    if mem:
        total, avail = mem
        rows.append(Row("memory", avail >= CHECK_PEAK_GB, f"{avail:.1f} GB free of {total:.1f}; "
                        f"one check peaks near {CHECK_PEAK_GB} GB", "kernel"))
    free = shutil.disk_usage(root).free / 2**30
    built = (build / "mathlib" / ".lake" / "build" / "lib" / "lean" / "Mathlib.olean").is_file()
    rows.append(Row("disk", built or free >= LEAN_DISK_GB, f"{free:.0f} GB free; setup needs about {LEAN_DISK_GB:.0f} GB",
                    "kernel"))
    return rows


def report(rows: list[Row]) -> tuple[str, int]:
    lines = [f"{'ok' if r.ok else 'MISSING':<8}{r.name:<16}{r.detail}" for r in rows]
    replay = all(r.ok for r in rows if r.needed_for == "replay")
    kernel = replay and all(r.ok for r in rows)
    lines.append("")
    if kernel:
        lines.append("Ready: claimcert demo replays recorded runs; claimcert check <claim.yaml> runs the kernel.")
        return "\n".join(lines) + "\n", 0
    lines.append("claimcert demo: " + ("ready" if replay else "not ready"))
    lines.append("claimcert check: not ready; fix the MISSING lines, then run claimcert setup")
    return "\n".join(lines) + "\n", 2


def setup(root: Path, lake: str = "lake") -> int:
    """Download the Mathlib build cache, then build LeanCert and the claimcert Lean library."""
    exe = shutil.which(lake)
    if exe is None:
        print(f"{lake} not found; install elan from https://lean-lang.org/install/", file=sys.stderr)
        return 2
    for step in (["exe", "cache", "get"], ["build", "ClaimCert"]):
        started = time.perf_counter()
        print(f"$ lake {' '.join(step)}", flush=True)
        code = subprocess.run([exe, *step], cwd=root / "lean").returncode
        print(f"lake {' '.join(step)}: exit {code} after {time.perf_counter() - started:.0f} s", flush=True)
        if code != 0:
            return code
    return 0
