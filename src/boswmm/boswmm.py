"""Step 3 — BOSWMM: Bayesian optimization loop for sediment maintenance.

Supports both single-objective (EI) and multi-objective (EHVI) modes through
a pluggable :class:`AcquisitionFunction` strategy. The mode is chosen in
``config.yaml`` via ``optimization.mode``.
"""

import os

import torch

from ._config import resolve_config
from .acquisition import make_acquisition
from .input import InputqEHVISWMM
from .kpi_evaluation import KPIEvaluation
from .output import OutputqEHVISWMM


class BOSWMM:
    """Bayesian optimization for sediment-maintenance volume selection.

    Two modes (selected via ``optimization.mode`` in the config):

      * ``single`` — Minimize the scalar FROI using qLogExpectedImprovement.
      * ``multi``  — Minimize ``[FHI, FEI, FVI, 1 − FRI]`` on the Pareto front
        using qLogExpectedHypervolumeImprovement.

    Decision variable: x in R^N with x[i] in [0, v_max[i]] and sum(x) <= A.

    Loop:
        1. Generate initial continuous samples via Sobol + rejection (budget).
        2. Evaluate via SWMM (InputqEHVISWMM + KPIEvaluation).
        3. Fit GP surrogate via the acquisition strategy.
        4. Optimize the acquisition function with budget inequality constraint.
        5. Evaluate candidates (no discretization).
        6. Update dataset, track progress metric (best-so-far / hypervolume),
           check convergence.
        7. Repeat 3–6 until converged or max iterations.
        8. Extract Pareto set (multi) or best solution (single) and emit JSON.
    """

    def __init__(
        self,
        input_module: InputqEHVISWMM,
        kpi_evaluator: KPIEvaluation,
        config: dict | None = None,
    ):
        """
        Args:
            input_module: Initialized :class:`InputqEHVISWMM`.
            kpi_evaluator: Initialized :class:`KPIEvaluation`. Its ``mode``
                property must match the BO mode in the config.
            config: Optional config dict overriding ``src/boswmm/config.yaml``.
        """
        self._input = input_module
        self._kpi_eval = kpi_evaluator

        cfg = resolve_config(config)
        opt_cfg = cfg["optimization"]
        constraints_cfg = cfg["constraints"]

        self._mode = opt_cfg["mode"]
        if self._mode != kpi_evaluator.mode:
            raise ValueError(
                f"Mode mismatch: config.optimization.mode={self._mode!r} but "
                f"kpi_evaluator.mode={kpi_evaluator.mode!r}"
            )

        self._n_init = opt_cfg["n_init"]
        self._max_iter = opt_cfg["max_iter"]
        self._batch_size = opt_cfg["batch_size"]
        self._num_restarts = opt_cfg["num_restarts"]
        self._raw_samples = opt_cfg["raw_samples"]
        self._mc_samples = opt_cfg["mc_samples"]
        self._patience = opt_cfg["patience"]
        self._seed = opt_cfg["seed"]
        self._ref_point_offset = opt_cfg["ref_point_offset"]
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
            f"sum(v_max)={v_max_sum:.4f} m^3, max(v_max)={v_max_max:.4f} m^3"
        )
        if self._budget_A >= v_max_sum:
            print("  Warning: A >= sum(v_max) — budget constraint is inactive.")
        if self._budget_A < v_max_max and self._N > 0:
            print(
                "  Warning: A < max(v_max_i) — rejection sampling may be inefficient."
            )

        # Encode sum(x_i) <= A as sum(-1 * x_i) >= -A for BoTorch optimize_acqf
        self._ineq_constraints = [
            (
                torch.arange(self._N, dtype=torch.long, device=device),
                torch.full((self._N,), -1.0, **self._tkwargs),
                -self._budget_A,
            )
        ]

        # Acquisition strategy
        self._acq = make_acquisition(
            mode=self._mode,
            bounds=self._bounds,
            ineq_constraints=self._ineq_constraints,
            batch_size=self._batch_size,
            num_restarts=self._num_restarts,
            raw_samples=self._raw_samples,
            mc_samples=self._mc_samples,
            ref_point_offset=self._ref_point_offset,
            n_objectives=kpi_evaluator.n_objectives,
        )

        # Counter for unique scenario IDs across all evaluations
        self._scenario_counter = 0

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    @property
    def mode(self) -> str:
        return self._mode

    def run(self, output_path: str = "output/report.json") -> dict:
        """Run the full BO optimization loop."""
        print(f"BOSWMM Optimization (mode={self._mode!r})")
        print(
            f"  N={self._N}, n_init={self._n_init}, max_iter={self._max_iter}, "
            f"batch_size={self._batch_size}, patience={self._patience}"
        )
        print()

        # --- Step 1: Initial sampling (Sobol + rejection on budget constraint) ---
        print(
            f"Generating {self._n_init} initial samples (Sobol + rejection, "
            f"sum(x) <= {self._budget_A:.4f})..."
        )
        train_X = self._initial_samples()

        print("Evaluating initial samples via SWMM...")
        train_Y, all_results = self._evaluate(train_X)
        print(f"  Initial Y mean: {train_Y.mean(dim=0).tolist()}")
        print()

        # --- Step 2: BO loop ---
        progress_history: list[float] = []
        best_progress = -float("inf")
        stagnation_count = 0
        iteration = -1
        metric_name = "HV" if self._mode == "multi" else "best-so-far"

        for iteration in range(self._max_iter):
            print(f"=== Iteration {iteration + 1}/{self._max_iter} ===")

            # Propose and evaluate new candidates
            candidate = self._acq.propose_candidate(train_X, train_Y)
            new_X = candidate.to(**self._tkwargs)
            new_X = torch.clamp(new_X, min=self._bounds[0], max=self._bounds[1])

            print(f"  Evaluating {new_X.shape[0]} new candidates via SWMM...")
            new_Y, new_results = self._evaluate(new_X)

            # Update dataset
            train_X = torch.cat([train_X, new_X])
            train_Y = torch.cat([train_Y, new_Y])
            all_results.extend(new_results)

            # Progress metric via the acquisition strategy
            progress = self._acq.progress_metric(train_Y)
            progress_history.append(progress)

            new_Y_str = ", ".join(f"{v:.4f}" for v in new_Y.mean(dim=0).tolist())
            n_samples = train_X.shape[0]

            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            print(f"  New Y mean: [{new_Y_str}]")
            print(f"  Total samples: {n_samples}, {metric_name}: {progress:.6f}")

            # Convergence check (disabled when patience == -1)
            if self._patience >= 0:
                if progress > best_progress:
                    best_progress = progress
                    stagnation_count = 0
                else:
                    stagnation_count += 1

                if stagnation_count >= self._patience:
                    print(
                        f"\n  Converged: {metric_name} stagnated for "
                        f"{self._patience} iterations."
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

        # --- Step 3: Extract solutions and generate report ---
        if self._mode == "multi":
            solution_X, solution_Y, solution_indices = OutputqEHVISWMM.extract_pareto(
                train_X, train_Y
            )
            solution_results = [all_results[i] for i in solution_indices]
            print(f"Pareto front: {solution_X.shape[0]} solutions")
        else:
            best_idx = int(train_Y.argmin().item())
            solution_X = train_X[best_idx:best_idx + 1]
            solution_Y = train_Y[best_idx:best_idx + 1]
            solution_indices = [best_idx]
            solution_results = [all_results[best_idx]]
            print(f"Best single-objective solution at index {best_idx}, "
                  f"kpi={train_Y[best_idx].tolist()}")

        report_path = OutputqEHVISWMM.generate_report(
            pareto_X=solution_X,
            pareto_results=solution_results,
            conduit_names=self._input.conduit_names,
            output_path=output_path,
            mode=self._mode,
        )
        print(f"Report saved to: {report_path}")

        return {
            "mode": self._mode,
            "train_X": train_X,
            "train_Y": train_Y,
            "all_results": all_results,
            "pareto_X": solution_X,
            "pareto_Y": solution_Y,
            "pareto_indices": solution_indices,
            "report_path": report_path,
            "n_iterations": n_iterations,
            "progress_history": progress_history,
            # Back-compat alias for the old qEHVI-only 'hv_history' key
            "hv_history": progress_history,
        }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _evaluate(
        self, X: torch.Tensor
    ) -> tuple[torch.Tensor, list[dict]]:
        """Evaluate maintenance-volume decision vectors via SWMM."""
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

    def _initial_samples(self) -> torch.Tensor:
        """Generate n_init initial samples in [0, v_max]^N satisfying sum(x) <= A."""
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
                f"sum(v_max)={sigma_vmax:.4f}. Try increasing A or reducing n_init."
            )

        acceptance = len(accepted) / float(attempts) if attempts else 1.0
        print(f"  Acceptance rate: {acceptance * 100:.1f}% ({attempts} draws)")
        return torch.stack(accepted, dim=0)


# Back-compat alias so legacy imports of ``qEHVISWMM`` continue to resolve.
qEHVISWMM = BOSWMM
