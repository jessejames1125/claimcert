# Changelog

## Unreleased

- Claims in YAML generate a frozen Lean statement; a proof goes through a screen, then the kernel, and the verdict lists every assumption used by kind.
- The report line comes from `claimcert-verify`, a separate program that replays the compiled claim through the kernel; the process that runs the proof never sees the nonce.
- `claimcert demo` and `claimcert replay` match recorded verdicts to the files without Lean.
- `claimcert doctor` and `claimcert setup` report and fetch what the kernel run needs.
- `claimcert prove` and `claimcert audit-agent` work with any command-line agent that reads stdin.
- Information is a dimension, with exact bit, byte, GB and GiB units.
- Examples for software, numerics and neutron shielding.
- Evaluations in `evals/`: the 40-claim planted-error set, a no-Lean baseline, and a 12-claim set that measures the gap between English and the formal statement.
