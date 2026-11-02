namespace ClaimCert

/-- Dimension exponents: length, mass, time, current, temperature, amount, luminosity,
information. -/
structure Dim where
  L : Int
  M : Int
  T : Int
  I : Int
  Th : Int
  N : Int
  J : Int
  Bit : Int
deriving DecidableEq, Repr

namespace Dim

def one : Dim := ⟨0, 0, 0, 0, 0, 0, 0, 0⟩

def mul (a b : Dim) : Dim :=
  ⟨a.L + b.L, a.M + b.M, a.T + b.T, a.I + b.I, a.Th + b.Th, a.N + b.N, a.J + b.J, a.Bit + b.Bit⟩

def div (a b : Dim) : Dim :=
  ⟨a.L - b.L, a.M - b.M, a.T - b.T, a.I - b.I, a.Th - b.Th, a.N - b.N, a.J - b.J, a.Bit - b.Bit⟩

def pow (a : Dim) (k : Int) : Dim :=
  ⟨a.L * k, a.M * k, a.T * k, a.I * k, a.Th * k, a.N * k, a.J * k, a.Bit * k⟩

end Dim

end ClaimCert
