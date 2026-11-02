# Security

Report a vulnerability through GitHub's private advisory form on this repository (Security tab, "Report a vulnerability"). I aim to reply within 7 days.

What counts: a way to get a PASS verdict for a claim whose proof the Lean kernel did not accept, a way to get a PASS while using an axiom or hypothesis the verdict does not list, or a way for a proof to run code the proof screen should have refused.

What to expect from the proof screen: it is a denylist, not a sandbox. Lean runs code during elaboration, so treat a proof from a stranger the way you would treat any program from a stranger and run it in a container. `docs/trust.md` lists the rules.
