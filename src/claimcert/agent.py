"""Run any command-line agent: the prompt goes in on stdin, the reply comes back on stdout.

No API key lives in this tool. The agent runs in an empty temp folder, so by default it sees only
the prompt. What it sends over the network is up to the command you give it."""
from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile


class AgentError(RuntimeError):
    pass


def run_agent(command: str, prompt: str, timeout_s: float = 300.0) -> str:
    argv = shlex.split(command)
    if not argv:
        raise AgentError("the agent command is empty")
    exe = shutil.which(argv[0])
    if exe is None:
        raise AgentError(f"agent command {argv[0]!r} not found on PATH")
    with tempfile.TemporaryDirectory(prefix="claimcert-agent-") as cwd:
        try:
            p = subprocess.run([exe, *argv[1:]], input=prompt, capture_output=True, text=True, encoding="utf-8",
                               errors="replace", cwd=cwd, timeout=timeout_s)
        except subprocess.TimeoutExpired as e:
            raise AgentError(f"agent timed out after {timeout_s} s") from e
    if p.returncode != 0:
        raise AgentError(f"agent exited {p.returncode}: {(p.stderr or p.stdout)[-500:]}")
    return p.stdout
