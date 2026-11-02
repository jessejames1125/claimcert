import Lean

open Lean Elab Command Meta

namespace ClaimCert

/-- `#cc_report thm` prints one line `CCREPORT <nonce> {json}`: each binder of `thm` (name,
whether it is a proposition, the head constant of its type, whether the proof uses it) and the
axioms `thm` depends on. The nonce is read from the environment variable `CC_NONCE` (`-` when
unset). claimcert reads this line; it never reads the proof text. -/
syntax (name := ccReport) "#cc_report " ident : command

@[command_elab ccReport] def elabCcReport : CommandElab := fun stx => do
  let nonce := (← IO.getEnv "CC_NONCE").getD "-"
  let name ← liftCoreM <| realizeGlobalConstNoOverloadWithInfo stx[1]
  let info ← getConstInfo name
  let some value := info.value? (allowOpaque := true) | throwError "#cc_report: {name} has no proof term"
  let axioms ← liftCoreM <| collectAxioms name
  let binders ← liftTermElabM do
    forallTelescope info.type fun xs _ => do
      lambdaBoundedTelescope value xs.size fun ys body => do
        let mut out : Array Json := #[]
        for i in [0:xs.size] do
          let decl ← xs[i]!.fvarId!.getDecl
          let ty ← instantiateMVars decl.type
          let prop ← isProp ty
          let head := match ty.getAppFn.constName? with
            | some n => n.toString
            | none => ""
          let used := if h : i < ys.size then body.containsFVar ys[i].fvarId! else true
          out := out.push <| Json.mkObj [
            ("name", Json.str decl.userName.toString),
            ("prop", Json.bool prop),
            ("head", Json.str head),
            ("used", Json.bool used)]
        return out
  let json := Json.mkObj [
    ("theorem", Json.str name.toString),
    ("binders", Json.arr binders),
    ("axioms", Json.arr (axioms.map fun a => Json.str a.toString))]
  logInfo m!"CCREPORT {nonce} {json.compress}"

end ClaimCert
