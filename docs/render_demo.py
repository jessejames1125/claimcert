"""Draw docs/demo.svg from what `claimcert demo` prints. Run from the repo root after any verdict change."""
from html import escape
from pathlib import Path

from claimcert.replay import demo

LINE, WIDTH = 19, 880
HEAD = "$ claimcert demo"


def main() -> None:
    text, ok = demo(Path("."))
    assert ok, "a demo claim is stale; re-run claimcert check first"
    # The image holds the catch: the planted claim and its true partner. The README has the rest as text.
    blocks = text.split("\n\n")
    lines = [HEAD, ""] + "\n\n".join(blocks[:3]).splitlines()
    height = LINE * (len(lines) + 1) + 16
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" '
           'role="img" aria-label="Terminal output of claimcert demo">',
           f'<rect width="{WIDTH}" height="{height}" rx="6" fill="#16181c"/>',
           '<g font-family="ui-monospace,Consolas,Menlo,monospace" font-size="13" fill="#d7dae0">']
    for i, line in enumerate(lines):
        color = ""
        if line == HEAD:
            color = ' fill="#8fb4ff"'
        elif ": FAIL" in line and "at stage" in line:
            color = ' fill="#ff8f85"'
        elif ": PASS" in line and "at stage" in line:
            color = ' fill="#8fdc9a"'
        elif line.startswith("["):
            color = ' fill="#8b919c"'
        indent = 16 + 7.2 * (len(line) - len(line.lstrip()))  # SVG collapses leading spaces
        out.append(f'<text x="{indent:g}" y="{LINE * (i + 1) + 8}"{color}>{escape(line.strip())}</text>')
    out += ["</g>", "</svg>", ""]
    Path("docs/demo.svg").write_text("\n".join(out), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
