"""Run any command-line agent: the prompt goes in on stdin, the reply comes back on stdout.

No API key lives in this tool. The agent starts in an empty temp folder and gets the caller's
environment, because the command you name may need its own login or key. Nothing stops it reading
other files or using the network: what it can reach is up to the command you give it. Its reply is
only text, and nothing in it is trusted: a proof still goes through the screen and the kernel, and an
audit reply counts only if it starts with MATCH."""
from __future__ import annotations

import shlex
import shutil
import subprocess
import sys
import tempfile


class AgentError(RuntimeError):
    pass


def split_command(command: str) -> list[str]:
    """POSIX quoting, except that on Windows a backslash is a path separator, not an escape."""
    try:
        if sys.platform == "win32":
            return [a[1:-1] if len(a) > 1 and a[0] == a[-1] and a[0] in "\"'" else a
                    for a in shlex.split(command, posix=False)]
        return shlex.split(command)
    except ValueError as e:
        raise AgentError(f"could not read the agent command: {e}") from e


def run_agent(command: str, prompt: str, timeout_s: float = 300.0) -> str:
    argv = split_command(command)
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
