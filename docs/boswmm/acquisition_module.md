# AcquisitionFunction — Strategy for Single/Multi-objective BO

**Source:** `src/boswmm/acquisition.py`

---

## Purpose

Encapsulates everything that differs between **single-objective** and **multi-objective** Bayesian optimization so the core `BOSWMM` loop stays mode-agnostic. Concrete strategies own:

- the surrogate GP (single `SingleTaskGP` vs `ModelListGP` with one GP per objective),
- the BoTorch acquisition function (`qLogExpectedImprovement` vs `qLogExpectedHypervolumeImprovement`),
- the scalar progress metric used by the convergence check (best-so-far vs hypervolume),
- `n_objectives` — 1 for EI, `M` (typically 4) for EHVI.

`BOSWMM.run` calls `propose_candidate(train_X, train_Y)` and `progress_metric(train_Y)`; the strategy does the rest.

---

## API

### Base class

```python
class AcquisitionFunction(ABC):
    mode: str   # "single" or "multi"

    def __init__(
        self,
        bounds: torch.Tensor,          # (2, N) lower/upper bounds
        ineq_constraints: list,        # BoTorch inequality_constraints, may be []
        *,
        batch_size: int = 1,
        num_restarts: int = 10,
        raw_samples: int = 64,
        mc_samples: int = 32,
        ref_point_offset: float = -0.1,
    ): ...

    @abstractmethod
    def n_objectives(self) -> int: ...

    @abstractmethod
    def fit_surrogate(self, train_X, train_Y): ...

    @abstractmethod
    def build_acqf(self, model, train_Y): ...

    @abstractmethod
    def progress_metric(self, train_Y) -> float: ...

    def propose_candidate(self, train_X, train_Y) -> torch.Tensor:
        """Shared: fit → build acqf → optimize_acqf → (q, N) candidate."""
```

`propose_candidate` is the only non-abstract public method; it runs the full single-iteration BO step using whichever strategy was passed in.

### Factory

```python
from src.boswmm.acquisition import make_acquisition

acq = make_acquisition(
    mode="single",                 # or "multi"
    bounds=bounds_2xN,
    ineq_constraints=ineq,
    batch_size=3,
    num_restarts=10,
    raw_samples=64,
    mc_samples=32,
    ref_point_offset=-0.1,
    n_objectives=4,                # only used in multi mode
)
```

Returns an `EIAcquisition` (single) or `EHVIAcquisition` (multi).

---

## `EIAcquisition` — Single-objective EI

| Element | Choice |
|---|---|
| Surrogate | `SingleTaskGP(train_X, -train_Y, input_transform=Normalize, outcome_transform=Standardize)` |
| Fit MLL | `ExactMarginalLogLikelihood` |
| Acquisition | `qLogExpectedImprovement(model=gp, best_f=max(-train_Y), sampler=SobolQMC)` |
| Progress | `-min(train_Y)` — best FROI so far (higher = better) |
| n_objectives | `1` |

BOSWMM minimizes the kpi; BoTorch maximizes internally. We negate `train_Y` before fitting the GP, and `best_f` is the current max of the negated observations (i.e., the most-negative original value).

---

## `EHVIAcquisition` — Multi-objective EHVI

| Element | Choice |
|---|---|
| Surrogate | `ModelListGP(*[SingleTaskGP per objective])` with `Normalize` + `Standardize` on each |
| Fit MLL | `SumMarginalLogLikelihood` |
| Reference point | `min(-train_Y, dim=0) + ref_point_offset`  (computed per iteration from current data) |
| Partitioning | `NondominatedPartitioning(ref_point, Y=-train_Y)` |
| Acquisition | `qLogExpectedHypervolumeImprovement(model, ref_point, partitioning, sampler=SobolQMC)` |
| Progress | Pareto-front hypervolume in the negated (maximization) space |
| n_objectives | `len(train_Y[0])` — 4 for `[FHI, FEI, FVI, 1-FRI]` |

---

## Why a strategy class?

Before this refactor, the entire BO loop was hardcoded to EHVI. Adding single-objective EI required either duplicating the loop body or threading `if mode == 'single'` checks through every step. The strategy pattern:

- keeps the loop body one concrete algorithm,
- lets new acquisition functions (e.g., noisy EI, NEHVI) drop in by subclassing `AcquisitionFunction`,
- makes the code under test: each strategy can be instantiated and exercised without running a full BO loop.

---

## Dependencies

- `torch`
- `botorch` — `SingleTaskGP`, `ModelListGP`, `qLogExpectedImprovement`, `qLogExpectedHypervolumeImprovement`, `optimize_acqf`, `NondominatedPartitioning`, `Hypervolume`, `is_non_dominated`
- `gpytorch` — `ExactMarginalLogLikelihood`, `SumMarginalLogLikelihood`
