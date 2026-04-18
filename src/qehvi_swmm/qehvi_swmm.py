"""Step 3 — qEHVISWMM: multi-objective Bayesian optimization loop using qEHVI."""

import os

import torch
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
from gpytorch.mlls import SumMarginalLogLikelihood

from ._config import resolve_config
from .input import InputqEHVISWMM
from .kpi_evaluation import KPIEvaluation
from .output import OutputqEHVISWMM


class qEHVISWMM:
    """Multi-objective Bayesian optimization using qEHVI for sediment
    maintenance volume selection.

    Wraps the BoTorch qLogExpectedHypervolumeImprovement acquisition function
    with SWMM hydraulic simulation as the black-box objective.

    Decision variable: x in R^N with x[i] in [0, v_max[i]] and sum(x) <= A.

    Loop:
        1. Generate initial continuous samples via Sobol + rejection (budget).
        2. Evaluate via SWMM (InputqEHVISWMM + KPIEvaluation).
        3. Fit GP surrogate (ModelListGP with Normalize input transform).
        4. Optimize qLogEHVI acquisition with inequality_constraints.
        5. Evaluate candidates via SWMM (no discretization).
        6. Update Pareto front, check convergence.
        7. Repeat 3-6 until converged or max iterations.
        8. Extract Pareto set, generate JSON report.
    """

    def __init__(
        self,
        input_module: InputqEHVISWMM,
        kpi_evaluator: KPIEvaluation,
        config: dict | None = None,
    ):
        """
        Args:
            input_module: Initialized InputqEHVISWMM instance.
            kpi_evaluator: Initialized KPIEvaluation instance.
            config: Optional config dict overriding the default ``config.yaml``.
        """
        self._input = input_module
        self._kpi_eval = kpi_evaluator

        cfg = resolve_config(config)
        bo_cfg = cfg["bo"]
        constraints_cfg = cfg["constraints"]

        self._n_init = bo_cfg["n_init"]
        self._max_iter = bo_cfg["max_iter"]
        self._batch_size = bo_cfg["batch_size"]
        self._num_restarts = bo_cfg["num_restarts"]
        self._raw_samples = bo_cfg["raw_samples"]
        self._mc_samples = bo_cfg["mc_samples"]
        self._patience = bo_cfg["patience"]
        self._seed = bo_cfg["seed"]
        self._ref_point_offset = bo_cfg["ref_point_offset"]
        self._budget_A = float(constraints_cfg["maintenance_budget"])

        self._N = input_module.N
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._tkwargs = {"dtype": torch.double, "device": device}

        v_max = input_module.v_max.to(**self._tkwargs)
        self._bounds = torch.stack(
            [torch.zeros(self._N, **self._tkwargs), v_max]
        )

        # Budget diagnostics
        v_max_sum = float(v_max.sum().item())
        v_max_max = float(v_max.max().item()) if self._N > 0 else 0.0
        print(
            f"Budget: A={self._budget_A:.4f} m^3, "
            f"Σ v_max={v_max_sum:.4f} m^3, max(v_max)={v_max_max:.4f} m^3"
        )
        if self._budget_A >= v_max_sum:
            print("  Warning: A >= Σ v_max — budget constraint is inactive.")
        if self._budget_A < v_max_max and self._N > 0:
            print(
                "  Warning: A < max(v_max_i) — rejection sampling may be inefficient."
            )

        # Encode Σ x_i ≤ A as Σ (-1)·x_i ≥ -A for BoTorch optimize_acqf
        self._ineq_constraints = [
            (
                torch.arange(self._N, dtype=torch.long, device=device),
                torch.full((self._N,), -1.0, **self._tkwargs),
                -self._budget_A,
            )
        ]

        # Counter for unique scenario IDs across all evaluations
        self._scenario_counter = 0

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self, output_path: str = "output/report.json") -> dict:
        """Run the full qEHVI optimization loop."""
        print("qEHVI-SWMM Optimization")
        print(
            f"  N={self._N}, n_init={self._n_init}, max_iter={self._max_iter}, "
            f"batch_size={self._batch_size}, patience={self._patience}"
        )
        print()

        # --- Step 1: Initial sampling (Sobol + rejection on budget constraint) ---
        print(
            f"Generating {self._n_init} initial samples (Sobol + rejection, "
            f"Σ x ≤ {self._budget_A:.4f})..."
        )
        train_X = self._initial_samples()

        print("Evaluating initial samples via SWMM...")
        train_Y, all_results = self._evaluate(train_X)
        print(f"  Initial Y mean: {train_Y.mean(dim=0).tolist()}")
        print()

        # --- Step 2: BO loop ---
        hv_history: list[float] = []
        best_hv = -float("inf")
        stagnation_count = 0
        iteration = -1

        for iteration in range(self._max_iter):
            print(f"=== Iteration {iteration + 1}/{self._max_iter} ===")

            # Fit GP surrogate (negate Y for maximization)
            neg_Y = -train_Y
            model = self._fit_gp(train_X, neg_Y)

            # Reference point
            ref_point = neg_Y.min(dim=0).values + self._ref_point_offset

            # Partitioning
            partitioning = NondominatedPartitioning(ref_point=ref_point, Y=neg_Y)

            # qLogEHVI acquisition
            sampler = SobolQMCNormalSampler(
                sample_shape=torch.Size([self._mc_samples])
            )
            acqf = qLogExpectedHypervolumeImprovement(
                model=model,
                ref_point=ref_point.tolist(),
                partitioning=partitioning,
                sampler=sampler,
            )

            # Optimize acquisition function (with budget inequality constraint)
            candidate, _acqf_value = optimize_acqf(
                acq_function=acqf,
                bounds=self._bounds,
                q=self._batch_size,
                num_restarts=self._num_restarts,
                raw_samples=self._raw_samples,
                inequality_constraints=self._ineq_constraints,
            )

            # Evaluate candidates directly (continuous — no discretization)
            new_X = candidate.detach().to(**self._tkwargs)
            new_X = torch.clamp(new_X, min=self._bounds[0], max=self._bounds[1])
            print(f"  Evaluating {new_X.shape[0]} new candidates via SWMM...")
            new_Y, new_results = self._evaluate(new_X)

            # Update dataset
            train_X = torch.cat([train_X, new_X])
            train_Y = torch.cat([train_Y, new_Y])
            all_results.extend(new_results)

            # Compute hypervolume for convergence check
            neg_train_Y = -train_Y
            ref_pt = neg_train_Y.min(dim=0).values + self._ref_point_offset
            hv_calc = Hypervolume(ref_point=ref_pt)
            pareto_indices = OutputqEHVISWMM.extract_pareto(train_X, train_Y)[2]
            pareto_Y_neg = neg_train_Y[pareto_indices]
            current_hv = (
                hv_calc.compute(pareto_Y_neg) if pareto_Y_neg.shape[0] > 0 else 0.0
            )
            hv_history.append(current_hv)

            new_Y_str = ", ".join(f"{v:.4f}" for v in new_Y.mean(dim=0).tolist())
            n_samples = train_X.shape[0]

            # Free cache in each iteration
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            print(f"  New Y mean: [{new_Y_str}]")
            print(f"  Total samples: {n_samples}, HV: {current_hv:.4f}")

            # Convergence check (disabled when patience == -1)
            if self._patience >= 0:
                if current_hv > best_hv:
                    best_hv = current_hv
                    stagnation_count = 0
                else:
                    stagnation_count += 1

                if stagnation_count >= self._patience:
                    print(
                        f"\n  Converged: HV stagnated for {self._patience} iterations."
                    )
                    break

            print()

        n_iterations = min(iteration + 1, self._max_iter)
        print(
            f"\nOptimization complete. {n_iterations} iterations, "
            f"{train_X.shape[0]} total evaluations."
        )

        # Move training data to CPU and free GPU memory
        train_X = train_X.cpu()
        train_Y = train_Y.cpu()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # --- Step 3: Extract Pareto set and generate report ---
        pareto_X, pareto_Y, pareto_indices = OutputqEHVISWMM.extract_pareto(
            train_X, train_Y
        )
        pareto_results = [all_results[i] for i in pareto_indices]

        print(f"Pareto front: {pareto_X.shape[0]} solutions")

        report_path = OutputqEHVISWMM.generate_report(
            pareto_X=pareto_X,
            pareto_results=pareto_results,
            conduit_names=self._input.conduit_names,
            output_path=output_path,
        )
        print(f"Report saved to: {report_path}")

        return {
            "train_X": train_X,
            "train_Y": train_Y,
            "all_results": all_results,
            "pareto_X": pareto_X,
            "pareto_Y": pareto_Y,
            "pareto_indices": pareto_indices,
            "report_path": report_path,
            "n_iterations": n_iterations,
            "hv_history": hv_history,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _evaluate(
        self, X: torch.Tensor
    ) -> tuple[torch.Tensor, list[dict]]:
        """Evaluate maintenance-volume decision vectors via SWMM.

        Args:
            X: Tensor of shape (n, N) — each row a continuous volume vector.

        Returns:
            (Y, results) where Y is shape (n, 3) and results is list of dicts.
        """
        paths: list[str] = []
        for i in range(X.shape[0]):
            path = self._input.build_scenario(X[i], scenario_id=self._scenario_counter)
            paths.append(path)
            self._scenario_counter += 1

        results = self._kpi_eval.evaluate_batch(paths)

        # Clean up temporary scenario files (.inp, .rpt, .out) after evaluation
        for p in paths:
            base = os.path.splitext(p)[0]
            for ext in (".inp", ".rpt", ".out"):
                f = base + ext
                if os.path.isfile(f):
                    os.remove(f)

        Y = torch.tensor([r["kpi"] for r in results], **self._tkwargs)
        return Y, results

    def _fit_gp(
        self, train_X: torch.Tensor, train_Y: torch.Tensor
    ) -> ModelListGP:
        """Fit independent GP per objective (ModelListGP pattern).

        Uses Normalize input transform (bounds from self._bounds) because
        per-conduit v_max can vary by orders of magnitude.
        """
        models = []
        for i in range(train_Y.shape[-1]):
            gp = SingleTaskGP(
                train_X,
                train_Y[:, i : i + 1],
                input_transform=Normalize(d=self._N, bounds=self._bounds),
                outcome_transform=Standardize(m=1),
            )
            models.append(gp)

        model = ModelListGP(*models)
        mll = SumMarginalLogLikelihood(model.likelihood, model)
        fit_gpytorch_mll(mll)
        return model

    def _initial_samples(self) -> torch.Tensor:
        """Generate n_init initial samples in [0, v_max]^N satisfying Σ x ≤ A.

        Uses scrambled Sobol draws scaled to bounds, rejecting any row whose
        sum exceeds the budget. Caps total attempts at 1000 × n_init.
        """
        sobol = torch.quasirandom.SobolEngine(
            dimension=self._N, scramble=True, seed=self._seed
        )
        accepted: list[torch.Tensor] = []
        lo = self._bounds[0]
        hi = self._bounds[1]
        max_attempts = max(1000 * self._n_init, 10000)
        attempts = 0
        chunk = max(self._n_init, 64)

        while len(accepted) < self._n_init and attempts < max_attempts:
            raw = sobol.draw(chunk).to(**self._tkwargs)
            scaled = lo + (hi - lo) * raw
            sums = scaled.sum(dim=-1)
            mask = sums <= self._budget_A
            for i in range(scaled.shape[0]):
                if bool(mask[i].item()):
                    accepted.append(scaled[i])
                    if len(accepted) >= self._n_init:
                        break
            attempts += chunk

        if len(accepted) < self._n_init:
            sigma_vmax = float((hi - lo).sum().item())
            raise RuntimeError(
                f"Rejection sampling failed: accepted {len(accepted)}/{self._n_init} "
                f"after {attempts} attempts. A={self._budget_A:.4f}, "
                f"Σ v_max={sigma_vmax:.4f}. Try increasing A or reducing n_init."
            )

        acceptance = len(accepted) / float(attempts) if attempts else 1.0
        print(f"  Acceptance rate: {acceptance * 100:.1f}% ({attempts} draws)")
        return torch.stack(accepted, dim=0)
