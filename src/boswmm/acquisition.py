"""Acquisition-function strategies for BOSWMM.

Encapsulates everything that differs between single-objective (EI) and
multi-objective (EHVI) Bayesian optimization so the core BOSWMM loop can
remain acquisition-agnostic.

Responsibilities of each concrete strategy:
  * Fit the surrogate GP for the current (train_X, train_Y).
  * Build the BoTorch acquisition function for the current posterior.
  * Compute a scalar "progress" metric used by the convergence check
    (best-so-far for EI; hypervolume for EHVI).
  * Expose ``n_objectives``: 1 for EI, len(kpi) for EHVI.

The BOSWMM loop just calls ``propose_candidate(train_X, train_Y)`` and
``progress_metric(train_Y)``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import torch
from botorch.acquisition.logei import qLogExpectedImprovement
from botorch.acquisition.multi_objective.logei import (
    qLogExpectedHypervolumeImprovement,
)
from botorch.fit import fit_gpytorch_mll
from botorch.models import ModelListGP, SingleTaskGP
from botorch.models.transforms.input import Normalize
from botorch.models.transforms.outcome import Standardize
from botorch.optim import optimize_acqf
from botorch.sampling.normal import SobolQMCNormalSampler
from botorch.utils.multi_objective.box_decompositions import (
    NondominatedPartitioning,
)
from botorch.utils.multi_objective.hypervolume import Hypervolume
from gpytorch.mlls import ExactMarginalLogLikelihood, SumMarginalLogLikelihood


class AcquisitionFunction(ABC):
    """Strategy interface used by :class:`BOSWMM`."""

    #: ``"single"`` or ``"multi"``. Set by concrete subclasses.
    mode: str = ""

    def __init__(
        self,
        bounds: torch.Tensor,
        ineq_constraints: list,
        *,
        batch_size: int = 1,
        num_restarts: int = 10,
        raw_samples: int = 64,
        mc_samples: int = 32,
        ref_point_offset: float = -0.1,
    ):
        """
        Args:
            bounds: ``(2, N)`` tensor — lower and upper bounds per dim.
            ineq_constraints: BoTorch inequality constraints list (may be empty).
            batch_size: q — number of candidates proposed per iteration.
            num_restarts / raw_samples: ``optimize_acqf`` restart budget.
            mc_samples: Sobol sample count for the qMC acquisition estimator.
            ref_point_offset: Offset added to worst objective for the reference
                point (EHVI only; ignored by EI).
        """
        self._bounds = bounds
        self._ineq_constraints = ineq_constraints
        self._batch_size = batch_size
        self._num_restarts = num_restarts
        self._raw_samples = raw_samples
        self._mc_samples = mc_samples
        self._ref_point_offset = ref_point_offset

    # --- Hooks subclasses must implement ---

    @abstractmethod
    def n_objectives(self) -> int:
        """Number of objectives (1 for EI, >=2 for EHVI)."""

    @abstractmethod
    def fit_surrogate(self, train_X: torch.Tensor, train_Y: torch.Tensor):
        """Return the fitted surrogate model (``SingleTaskGP`` or ``ModelListGP``)."""

    @abstractmethod
    def build_acqf(self, model, train_Y: torch.Tensor):
        """Build the BoTorch acquisition function instance."""

    @abstractmethod
    def progress_metric(self, train_Y: torch.Tensor) -> float:
        """Scalar metric for convergence tracking (higher = better)."""

    # --- Shared helper used by both strategies ---

    def propose_candidate(
        self, train_X: torch.Tensor, train_Y: torch.Tensor
    ) -> torch.Tensor:
        """Run one BO step: fit surrogate, build acqf, optimize, return candidate.

        Returns a tensor of shape ``(batch_size, N)`` with candidate points.
        """
        model = self.fit_surrogate(train_X, train_Y)
        acqf = self.build_acqf(model, train_Y)
        candidate, _ = optimize_acqf(
            acq_function=acqf,
            bounds=self._bounds,
            q=self._batch_size,
            num_restarts=self._num_restarts,
            raw_samples=self._raw_samples,
            inequality_constraints=self._ineq_constraints,
        )
        return candidate.detach()


# ----------------------------------------------------------------------
# Single-objective: Expected Improvement
# ----------------------------------------------------------------------

class EIAcquisition(AcquisitionFunction):
    """Single-objective BO via qLogExpectedImprovement.

    BOSWMM minimizes the kpi, but BoTorch maximizes internally. We negate
    ``train_Y`` before fitting the GP, and ``best_f`` is the current max of
    the negated observations (i.e., the most-negative original value).
    """

    mode = "single"

    def n_objectives(self) -> int:
        return 1

    def fit_surrogate(
        self, train_X: torch.Tensor, train_Y: torch.Tensor
    ) -> SingleTaskGP:
        # train_Y shape: (n, 1) — negate for maximization
        neg_Y = -train_Y
        N = train_X.shape[-1]
        gp = SingleTaskGP(
            train_X,
            neg_Y,
            input_transform=Normalize(d=N, bounds=self._bounds),
            outcome_transform=Standardize(m=1),
        )
        mll = ExactMarginalLogLikelihood(gp.likelihood, gp)
        fit_gpytorch_mll(mll)
        return gp

    def build_acqf(self, model: SingleTaskGP, train_Y: torch.Tensor):
        neg_Y = -train_Y
        best_f = neg_Y.max().item()
        sampler = SobolQMCNormalSampler(
            sample_shape=torch.Size([self._mc_samples])
        )
        return qLogExpectedImprovement(
            model=model,
            best_f=best_f,
            sampler=sampler,
        )

    def progress_metric(self, train_Y: torch.Tensor) -> float:
        """Best-so-far in the original (minimization) space."""
        return -float(train_Y.min().item())


# ----------------------------------------------------------------------
# Multi-objective: Expected Hypervolume Improvement
# ----------------------------------------------------------------------

class EHVIAcquisition(AcquisitionFunction):
    """Multi-objective BO via qLogExpectedHypervolumeImprovement."""

    mode = "multi"

    def n_objectives(self) -> int:
        # Known only after first fit; BOSWMM reads it from the KPIEvaluation
        # result shape and passes it in via `set_n_objectives`. Subclasses
        # don't know N_objectives until data exists.
        return self._n_obj

    def __init__(self, *args, n_objectives: int = 4, **kwargs):
        super().__init__(*args, **kwargs)
        self._n_obj = int(n_objectives)

    def fit_surrogate(
        self, train_X: torch.Tensor, train_Y: torch.Tensor
    ) -> ModelListGP:
        neg_Y = -train_Y
        N = train_X.shape[-1]
        models = []
        for i in range(neg_Y.shape[-1]):
            gp = SingleTaskGP(
                train_X,
                neg_Y[:, i : i + 1],
                input_transform=Normalize(d=N, bounds=self._bounds),
                outcome_transform=Standardize(m=1),
            )
            models.append(gp)

        model = ModelListGP(*models)
        mll = SumMarginalLogLikelihood(model.likelihood, model)
        fit_gpytorch_mll(mll)
        return model

    def build_acqf(self, model: ModelListGP, train_Y: torch.Tensor):
        neg_Y = -train_Y
        ref_point = neg_Y.min(dim=0).values + self._ref_point_offset
        partitioning = NondominatedPartitioning(ref_point=ref_point, Y=neg_Y)
        sampler = SobolQMCNormalSampler(
            sample_shape=torch.Size([self._mc_samples])
        )
        return qLogExpectedHypervolumeImprovement(
            model=model,
            ref_point=ref_point.tolist(),
            partitioning=partitioning,
            sampler=sampler,
        )

    def progress_metric(self, train_Y: torch.Tensor) -> float:
        """Pareto-front hypervolume in the negated (maximization) space."""
        from botorch.utils.multi_objective.pareto import is_non_dominated

        neg_Y = -train_Y
        ref_pt = neg_Y.min(dim=0).values + self._ref_point_offset
        mask = is_non_dominated(neg_Y)
        pareto_neg_Y = neg_Y[mask]
        if pareto_neg_Y.shape[0] == 0:
            return 0.0
        hv = Hypervolume(ref_point=ref_pt)
        return float(hv.compute(pareto_neg_Y))


# ----------------------------------------------------------------------
# Factory
# ----------------------------------------------------------------------

def make_acquisition(
    mode: str,
    bounds: torch.Tensor,
    ineq_constraints: list,
    *,
    batch_size: int,
    num_restarts: int,
    raw_samples: int,
    mc_samples: int,
    ref_point_offset: float,
    n_objectives: int = 4,
) -> AcquisitionFunction:
    """Construct the strategy for ``mode`` ('single' or 'multi')."""
    kwargs = dict(
        bounds=bounds,
        ineq_constraints=ineq_constraints,
        batch_size=batch_size,
        num_restarts=num_restarts,
        raw_samples=raw_samples,
        mc_samples=mc_samples,
        ref_point_offset=ref_point_offset,
    )
    if mode == "single":
        return EIAcquisition(**kwargs)
    if mode == "multi":
        return EHVIAcquisition(**kwargs, n_objectives=n_objectives)
    raise ValueError(f"Unknown optimization mode: {mode!r} (expected 'single' or 'multi')")
