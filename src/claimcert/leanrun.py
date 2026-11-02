"""Hygiene scan of untrusted proofs, and running Lake with a time budget."""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import sys
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
    r"|\bsimproc\w*|\bdsimproc\w*|\bregister_\w+|\bdeclare_\w+|\bmodifyEnv\b")


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


def run_lean(lake_root, lean_file, module: str, timeout_s: float, lake: str = "lake",
             nonce: str = "") -> LeanRun:
    exe = shutil.which(lake)
    if exe is None:
        return LeanRun("missing", f"{lake!r} not found on PATH", 0.0)
    t0 = time.perf_counter()
    env = {**os.environ, "CC_NONCE": nonce}

    def left() -> float:
        # one deadline for build plus run
        return max(timeout_s - (time.perf_counter() - t0), 0.001)

    try:
        rc, out = _run([exe, "build", module], Path(lake_root), env, left())
        if rc != 0:
            return LeanRun("build", out, time.perf_counter() - t0)
        rc, out = _run([exe, "env", "lean", str(Path(lean_file).resolve())], Path(lake_root), env, left())
    except subprocess.TimeoutExpired:
        return LeanRun("timeout", f"timed out after {timeout_s} s", time.perf_counter() - t0)
    except OSError as e:
        return LeanRun("missing", f"could not run {lake!r} in {lake_root}: {e}", time.perf_counter() - t0)
    return LeanRun("ok" if rc == 0 else "error", out, time.perf_counter() - t0)
