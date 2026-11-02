# Claim format

A claim is one YAML file. Its `name` must equal the file name.

```yaml
name: inflight_requests_true
type: bound              # bound | floor | point | fits_in_sphere | not_fits_in_sphere
intent: At a peak of 200 requests per second and 150 ms mean latency, at most 30 requests are in flight.
variables:
  L: {unit: "1", domain: real}        # real | positive | [lo, hi]
  lam: {unit: "s^-1", domain: positive}
  W: {unit: s, domain: positive}
conditions: []           # extra comparisons taken as hypotheses
assumptions:             # names from the registry, with the variables they apply to
  littles_law: [L, lam, W]
  peak_rate: [lam]
  mean_latency: [W]
constants: {B: "30"}     # any quantity; replaced by an exact number in the statement
goals: ["L <= B"]
```

A `point` claim has only constants and goals. The `fits_in_sphere` types take `cylinder: {r, h, R}` and check the corner of the cylinder, which a radial check would miss.

## Expressions

Numbers, names, `+ - * /`, integer powers with `**`, unary minus, `log`, `exp`, `sqrt`, `sin`, `cos`, and one comparison at the top level. Functions other than `sqrt` need a dimensionless argument.

## Units

Numbers are read exactly as fractions. Variables must use a coherent unit (`m`, `s`, `bit`); constants may use any listed unit.

| Kind | Units |
|---|---|
| length | `m cm mm km ft`, area `b` |
| time | `s ms us ns min h day` |
| mass, current, temperature, amount, luminosity | `kg g`, `A MA`, `K`, `mol`, `cd` |
| derived | `N lbf`, `J eV keV MeV`, `W kW MW`, `Pa MPa`, `T` |
| information | `bit kbit Mbit Gbit`, `B kB MB GB TB`, `KiB MiB GiB TiB` |

Information is a dimension of its own, so a bit rate cannot be compared with a size.

## Registry

Every hypothesis beyond the claim's own premises comes from `registry.yaml`, typed by kind.

| Kind | Meaning | Required fields |
|---|---|---|
| LAW | a law or a theorem from elsewhere | `source` |
| FIT | a fitted formula or survey value | `source`, `range`, `date` |
| TECH | a technology limit | `source`, `date` |
| NUMBER | a value computed outside Lean | `source`, `produced_by` |

`source` is required. Write `UNSOURCED` when there is none: it prints on every verdict that uses the assumption. A FIT with `valid_when` carries its range as a Lean precondition, so using it outside the range cannot be proved.

## Workflow

```bash
claimcert gen-assumptions --registry registry.yaml --out lean/MyProject/Assumptions.lean
claimcert new my_claim.yaml                 # writes my_claim.lean with a sorry
claimcert prove my_claim.yaml --agent "your-agent-command"   # or write the proof under CC-END yourself
claimcert check my_claim.yaml
claimcert audit-agent my_claim.yaml --agent "your-agent-command"
```

Add a `[[lean_lib]]` entry to `lean/lakefile.toml` for your assumption module. An agent command reads the prompt on stdin and writes the reply to stdout. For Claude Code with its tools off: `claude -p --model sonnet --setting-sources project --strict-mcp-config --permission-mode dontAsk`.
