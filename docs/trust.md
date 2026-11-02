# What a verdict means

## What the checker enforces

- Everything from the top of the Lean file to `-- CC-END` is generated from the YAML. Any edit fails the check at stage `statement`.
- The assumption module a claim imports must equal what `gen-assumptions` writes from the registry. Otherwise the check fails at stage `assumptions` before Lean runs.
- A pass needs only the axioms `propext`, `Classical.choice` and `Quot.sound`. Anything else, `sorryAx` included, fails at stage `axioms`.
- Every hypothesis in the statement must be a variable domain, a condition from the claim, or a registered assumption. The verdict lists which assumptions the proof term really uses, read from the term by Lean, and which it dropped.
- The report comes from a second process. The first compiles a private copy of the screened file to an olean, with a minimal environment: no keys, no tokens, no nonce. Nothing it prints is read except as an error message. The second, `claimcert-verify` (`lean/Verify.lean`), never elaborates the claim. It loads the claim's imports with environment extensions off, replays every constant the claim file added through the kernel, reads axioms and binders from what the kernel accepted, and prints the one report line with a fresh random nonce. claimcert accepts only that line. Code a proof runs while compiling cannot print a report the checker will take, and a theorem added with the kernel switched off fails the replay at stage `kernel`.
- The build is skipped only when a hash of the Lean sources, the build file, the manifest and the toolchain pin matches the last successful build. File times are not trusted.
- The time budget covers the whole process tree: on timeout Lake and its Lean child are both killed.

## Stages

A failed claim names the stage that refused it.

| Stage | Meaning | Lean ran? |
|---|---|---|
| `schema`, `registry` | the YAML is malformed | no |
| `dimension` | units do not agree | no |
| `file`, `statement`, `trailer` | the Lean file is missing or was edited | no |
| `hygiene` | the proof text tripped the screen | no |
| `assumptions` | the assumption module differs from the registry | no |
| `build` | the Lean library did not build | yes |
| `elaboration` | Lean found no proof: a tactic failed or a goal stayed open | yes |
| `kernel` | the kernel rejected a term, while compiling or in the replay | yes |
| `axioms` | the proof depends on a non-standard axiom | yes |
| `report` | the report line is missing or malformed | yes |
| `audit` | a recorded audit says the statement does not match the intent | no |

A false claim normally stops at `elaboration`, because no tactic can finish the goal, so no term ever reaches the kernel. A PASS is reported at stage `kernel`: the term was accepted when the theorem was added to the environment. FAIL means no proof was produced from the listed assumptions. It does not mean the claim was disproved. In `id_collision_planted` the union bound stops at 2.7%, so a 0.1% goal cannot follow from it; the check does not compute the true collision chance.

## The proof screen

The proof is untrusted text. Before Lean runs, it goes through a fixed denylist of words and characters. This is a screen, not a sandbox: anything not on the list reaches Lean, and Lean runs code during elaboration. Code that runs there can do what your user account can do, such as read files or edit the repo before the second process starts. The guarantee about the verdict is the kernel replay plus the axiom check, and it holds only if the first process could not tamper with the verifier or the libraries. Run a stranger's proof in a container or a throwaway VM.

The screen rejects a proof that contains:

- `#`, a string literal, a backslash, or an attribute (`@[`);
- a line that is not indented, other than a `--` comment. This is a format rule, not a defense;
- commands such as `macro`, `elab`, `syntax`, `run_cmd`, `set_option`, `open`, `initialize`, `register_*`, `simproc`, or anything that adds or compiles declarations;
- `sorry`, `admit`, `native_decide`, `axiom`, `unsafe`, or any change to LeanCert's trust mode.

It looks everywhere, comments included, and fails closed: a legitimate proof that trips it is rejected too. Whole-word rules such as `Lean`, `Meta`, `Tactic`, `IO` and `sorry` match only a token equal to the word, so `Lean.Meta.foo` is rejected and `Leanish` is not. Prefix rules such as `macro*`, `run_*` and anything containing `compile` also match inside longer names.

## What a PASS does not establish

- It proves the generated Lean statement. It does not prove that statement says what the claim's intent says. That is the audit (`audit-pack` then `audit-record`, or `audit-agent`). A verdict that has not been through it says UNAUDITED. A recorded MISMATCH fails the claim. The record hashes the statement and the whole assumption module, so any later change to either shows STALE, which counts as unaudited.
- The premises a claim adds, its domains and conditions, are hypotheses like any other. Contradictory premises make any goal provable. The verdict lists them; only the audit reads them against the intent.
- A NUMBER assumption is an input computed outside Lean. A PASS that uses one holds only if that number is right.
- Assumptions are not checked against the real world. The verdict names each one so the gap is visible.
- A FIT's range is enforced in Lean only when its registry entry has `valid_when`. Without it the range is printed on the verdict and Lean does not check it.
- The arithmetic is exact real arithmetic. A claim says nothing about floating-point rounding in code that uses the same formula.
- Lean's real division, logarithm and square root are total functions with junk values: `x / 0 = 0`, `Real.log 0 = 0`, `Real.log (-x) = Real.log x`, and `Real.sqrt` of a negative number is 0. A claim that divides by a variable, or takes a log or root of one, should add a condition that keeps it in range (`domain: positive`, or a line under `conditions`). claimcert does not add one for you, so a goal can be proved through a junk value. The audit is where that shows up.

## What replay does not establish

`claimcert demo` and `claimcert replay` do not run Lean. They re-run the stages marked "no" above, check that the assumption module on disk is what the registry generates, check that a recorded PASS still agrees with the audit record, and confirm that the claim, proof, assumption module, core library, verifier, manifest and toolchain pin match the record. They cannot confirm the verdict's own contents. Anyone can edit a verdict file. To re-check a proof, run `claimcert check`, or read the green Lean job in CI.
