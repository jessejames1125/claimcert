"""Hygiene scan of untrusted proofs, and running Lake with a time budget."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

_CHARS = ("#", '"', "\\", "@[")
_WORDS = re.compile(
    r"\b(attribute|initialize|builtin_initialize|run_tac|run_cmd|run_elab|by_elab|unsafe|implemented_by|extern"
    r"|native_decide|sorry|admit|axiom|dbg_trace|trust|IO|CCREPORT)\b"
    r"|\b(macro|elab|syntax|notation|infix|infixl|infixr|prefix|postfix)\w*"
    r"|\brun_\w+|\bunsafe\w*|\bset_option\b|\baddDecl\w*|\bdebug\b|\bskipKernel\w*|\bLean\b|\bElab\b|\bMeta\b"
    r"|\bopen\b|\bEnvironment\b|\bTactic\b|\bCommand\b|\w*[Cc]ompile\w*|\bdecl\b"
    r"|\bsimproc\w*|\bdsimproc\w*|\bregister_\w+|\bdeclare_\w+|\bmodifyEnv\b|\bbuiltin_\w+")


def hygiene(proof: str) -> str | None:
    """None if the proof is clean, else the reason. Runs before Lean ever sees the file.

    Structural: a tactic proof needs no command syntax, strings, attributes or escapes."""
    for line in proof.splitlines():
        if line.strip() and not line[0].isspace() and not line.startswith("--"):
            # A format rule only: an indented command passes it. The defense is the bans below.
            return f"unindented line {line.strip()[:40]!r} in the proof (proof lines must be indented)"
    for ch in _CHARS:
        if ch in proof:
            return f"forbidden character {ch!r} in the proof (kernel-only rule)"
    m = _WORDS.search(proof)
    if m:
        return f"forbidden token {m.group(0)!r} in the proof (kernel-only rule)"
    return None


@dataclass
class LeanRun:
    status: str  # ok | missing | timeout | build | error
    output: str
    seconds: float


def _kill_tree(p: subprocess.Popen) -> None:
    """Kill p and everything it started. lake starts lean as a child, and killing lake alone leaves
    lean running and holding the output pipes."""
    try:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(p.pid)], capture_output=True, timeout=60)
        else:
            os.killpg(p.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass  # p.kill below still stops lake itself
    try:
        p.kill()
    except OSError:
        pass


def _run(cmd: list[str], cwd: Path, env: dict, timeout: float) -> tuple[int, str]:
    """(exit code, stdout + stderr); raises subprocess.TimeoutExpired after killing the process tree."""
    if sys.platform == "win32":
        group = dict(creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)
    else:
        group = dict(start_new_session=True)
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, encoding="utf-8", errors="replace", **group)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(p)
        try:
            p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            pass  # a survivor still holds a pipe; do not wait for it
        raise
    return p.returncode, out + err


# Lean gets these and nothing else from the caller's environment: no keys, no tokens, no nonce.
_ENV_KEEP = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
             "HOME", "USERPROFILE", "LOCALAPPDATA", "APPDATA", "XDG_CACHE_HOME", "ELAN_HOME", "ELAN_TOOLCHAIN",
             "LANG", "LC_ALL", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")
VERIFY = "claimcert-verify"


def lean_env() -> dict:
    return {k: os.environ[k] for k in _ENV_KEEP if k in os.environ}


def verify_exe(lake_root) -> Path:
    return Path(lake_root) / ".lake" / "build" / "bin" / (VERIFY + (".exe" if sys.platform == "win32" else ""))


def _sources(lake_root: Path, module: str) -> list[Path]:
    """Every file in this repo that decides what a check imports or runs."""
    files = [lake_root / "ClaimCert.lean", *sorted((lake_root / "ClaimCert").glob("*.lean")),
             lake_root.joinpath(*module.split(".")).with_suffix(".lean"), lake_root / "Verify.lean",
             lake_root / "lakefile.toml", lake_root / "lake-manifest.json", lake_root / "lean-toolchain"]
    return files


def source_stamp(lake_root, module: str) -> str:
    lake_root = Path(lake_root)
    h = hashlib.sha256()
    for f in _sources(lake_root, module):
        h.update(f.relative_to(lake_root).as_posix().encode() + b"\0")
        h.update(f.read_bytes().replace(b"\r\n", b"\n") if f.is_file() else b"<missing>")
        h.update(b"\0")
    return h.hexdigest()


def _stamp_file(lake_root: Path, module: str) -> Path:
    return lake_root / ".lake" / "claimcert-stamps" / f"{module}.sha256"


def is_built(lake_root, module: str) -> bool:
    """True when the last successful build for this module saw exactly the sources on disk now. A
    `lake build` with nothing to do still walks every Mathlib module (168 s measured on Windows), so it
    runs only when something changed. File times are not trusted: the stamp is a hash of the sources."""
    lake_root = Path(lake_root)
    stamp = _stamp_file(lake_root, module)
    return verify_exe(lake_root).is_file() and stamp.is_file() and \
        stamp.read_text(encoding="utf-8").strip() == source_stamp(lake_root, module)


def run_lean(lake_root, lean_file, module: str, timeout_s: float, lake: str = "lake", nonce: str = "",
             theorem: str | None = None, source: str | None = None) -> LeanRun:
    """Two processes. The first compiles a private copy of the claim file to an olean; its output is
    read only for error messages. The second, claimcert-verify, replays the olean through the kernel
    and prints the report line with the nonce. Only that process ever sees the nonce."""
    exe = shutil.which(lake)
    if exe is None:
        return LeanRun("missing", f"{lake!r} not found on PATH", 0.0)
    lake_root, lean_file = Path(lake_root), Path(lean_file)
    theorem = theorem or lean_file.stem
    t0 = time.perf_counter()
    env = lean_env()

    def left() -> float:
        # one deadline for build, compile and verify
        return max(timeout_s - (time.perf_counter() - t0), 0.001)

    try:
        if not is_built(lake_root, module):
            stamp = source_stamp(lake_root, module)
            rc, out = _run([exe, "build", "ClaimCert", module, VERIFY], lake_root, env, left())
            if rc != 0:
                return LeanRun("build", out, time.perf_counter() - t0)
            _stamp_file(lake_root, module).parent.mkdir(parents=True, exist_ok=True)
            _stamp_file(lake_root, module).write_text(stamp + "\n", encoding="utf-8")
        source = source if source is not None else lean_file.read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory(prefix="claimcert-") as tmp:
            copy = Path(tmp) / lean_file.name
            copy.write_text(source, encoding="utf-8", newline="\n")
            olean = copy.with_suffix(".olean")
            rc, out = _run([exe, "env", "lean", "-R", tmp, "-o", str(olean), str(copy)], lake_root, env, left())
            out = out.replace(str(copy), str(lean_file.resolve()))
            if rc != 0 or not olean.is_file():
                return LeanRun("error", out, time.perf_counter() - t0)
            rc, out = _run([exe, "env", str(verify_exe(lake_root).resolve()), str(olean), theorem, nonce],
                           lake_root, env, left())
    except subprocess.TimeoutExpired:
        return LeanRun("timeout", f"timed out after {timeout_s} s", time.perf_counter() - t0)
    except OSError as e:
        return LeanRun("missing", f"could not run {lake!r} in {lake_root}: {e}", time.perf_counter() - t0)
    if rc != 0:
        # the kernel refusing a replayed constant, or the verifier itself failing to run
        return LeanRun("kernel" if "(kernel)" in out else "verify", out, time.perf_counter() - t0)
    return LeanRun("ok", out, time.perf_counter() - t0)


