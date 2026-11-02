# Contributing

1. `pip install -e ".[test]"`, then `pytest -m "not lean"` runs in seconds and needs no Lean.
2. `claimcert setup`, then `pytest -m lean` runs the tests that need the toolchain. Allow several minutes.
3. A change to the checker needs a test that fails without it.
4. A new example needs a true claim and a planted partner, and its verdict files must come from a real `claimcert check` run.
5. Changing a claim or the Lean core makes its recorded verdict stale. `claimcert replay` will say which ones to re-run.
6. Numbers in the README need a command that reproduces them, the date and the run count.
