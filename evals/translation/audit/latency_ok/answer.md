**Variable:** `l` is a real number.

**Definition used:** `A_latency_measured l` is the proposition that `l ≤ 3/20`. That is, `l` is at most 0.15.

**Hypothesis:** `h_latency_measured` says `A_latency_measured l` holds. So `l ≤ 0.15`.

**Conclusion:** `l ≤ 1/5`. That is, `l` is at most 0.2.

**Statement:** For every real number `l`, if `l ≤ 0.15`, then `l ≤ 0.2`.

The names suggest `l` is a latency in seconds. The Lean statement itself only talks about a real number `l` and two upper bounds on it.
