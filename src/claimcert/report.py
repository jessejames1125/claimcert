"""Read the single CCREPORT line printed by `#cc_report`."""
from __future__ import annotations

import json
import re

_ANY = re.compile(r"CCREPORT")
_LINE = re.compile(r"CCREPORT (\S+) (\{.*\})")


def parse_report(output: str, nonce: str) -> dict | None:
    """The report dict, or None unless the output holds exactly one CCREPORT line and it carries the nonce."""
    if len(_ANY.findall(output)) != 1:
        return None
    found = _LINE.findall(output)
    if len(found) != 1 or found[0][0] != nonce:
        return None
    try:
        return json.loads(found[0][1])
    except json.JSONDecodeError:
        return None
