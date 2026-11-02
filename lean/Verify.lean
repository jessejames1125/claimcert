import Lean

open Lean Meta

/-!
The second stage of `claimcert check`, built as its own executable.

The first stage compiled the claim file to an olean and could run code while it did. Nothing it
printed is read. This program never elaborates the claim. It reads the olean's constants, loads the
claim's imports with extensions off, so nothing the claim registered runs here, and replays the
claim's constants through the kernel. Axioms and binders are then read from what the kernel accepted,
and the one line claimcert reads is printed. The nonce reaches this process alone.
-/

/-- Every axiom `root` depends on, walking the kernel's own environment. A constant that is missing
from it is an error, never a silent skip. -/
partial def axiomsOf (env : Kernel.Environment) (root : Name) : Except String (Array Name) := do
  let rec go (todo : List Name) (seen : NameSet) (out : Array Name) : Except String (Array Name) :=
    match todo with
    | [] => pure out
    | n :: rest =>
      if seen.contains n then go rest seen out else
      match env.find? n with
      | none => throw s!"{n} is not in the kernel environment"
      | some ci =>
        let out := if ci matches .axiomInfo _ then out.push n else out
        let used := ci.type.getUsedConstants ++ ((ci.value? (allowOpaque := true)).map
          (·.getUsedConstants) |>.getD #[])
        let more := match ci with
          | .inductInfo v => v.ctors ++ v.all
          | .ctorInfo v => [v.induct]
          | .recInfo v => v.all
          | _ => []
        go (used.toList ++ more ++ rest) (seen.insert n) out
  go [root] {} #[]

/-- Each binder of the theorem: its name, whether it is a proposition, the head constant of its type,
whether the proof uses it. Binder types mention only imported constants, which the environment holds. -/
def binders (info : ConstantInfo) (value : Expr) : MetaM (Array Json) :=
  forallTelescope info.type fun xs _ =>
    lambdaBoundedTelescope value xs.size fun ys body => do
      let mut out : Array Json := #[]
      for i in [0:xs.size] do
        let decl ← xs[i]!.fvarId!.getDecl
        let ty ← instantiateMVars decl.type
        let head := (ty.getAppFn.constName?.map Name.toString).getD ""
        let used := if h : i < ys.size then body.containsFVar ys[i].fvarId! else true
        out := out.push <| Json.mkObj [
          ("name", Json.str decl.userName.toString),
          ("prop", Json.bool (← isProp ty)),
          ("head", Json.str head),
          ("used", Json.bool used)]
      return out

/-- `claimcert-verify <olean file> <theorem> <nonce>` -/
unsafe def main (args : List String) : IO UInt32 := do
  let [olean, thmArg, nonce] := args
    | throw <| IO.userError "usage: claimcert-verify <olean file> <theorem> <nonce>"
  initSearchPath (← findSysroot)
  let thm := thmArg.toName
  let (data, _) ← readModuleData olean
  let base ← importModules data.imports {} (trustLevel := 0) (loadExts := false)
  let mut fresh : Std.HashMap Name ConstantInfo := {}
  for name in data.constNames, ci in data.constants do
    fresh := fresh.insert name ci
  -- throws if the kernel rejects any constant the claim file added
  let kenv ← base.toKernelEnv.replay fresh
  let some info := kenv.find? thm
    | throw <| IO.userError s!"{thm} is not in the claim file"
  unless info matches .thmInfo _ do
    throw <| IO.userError s!"{thm} is not a theorem"
  let some value := info.value? (allowOpaque := true)
    | throw <| IO.userError s!"{thm} has no proof term"
  let axioms ← IO.ofExcept (axiomsOf kenv thm)
  let ctx : Core.Context := { fileName := "<verify>", fileMap := default }
  let (bs, _) ← ((binders info value).run' : CoreM _).toIO ctx { env := base }
  let json := Json.mkObj [
    ("theorem", Json.str thm.toString),
    ("binders", Json.arr bs),
    ("axioms", Json.arr (axioms.map fun a => Json.str a.toString))]
  IO.println s!"CCREPORT {nonce} {json.compress}"
  return 0
