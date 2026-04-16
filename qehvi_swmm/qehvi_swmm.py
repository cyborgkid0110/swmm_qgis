"""Step 3 — qEHVISWMM: multi-objective Bayesian optimization loop using qEHVI."""

import os

import torch
import yaml
from botorch.acquisition.multi_objective.logei import (
    qLogExpectedHypervolumeImprovement,
)
from botorch.fit import fit_gpytorch_mll
from botorch.models import ModelListGP, SingleTaskGP
from botorch.models.transforms.outcome import Standardize
from botorch.optim import optimize_acqf
from botorch.sampling.normal import SobolQMCNormalSampler
from botorch.utils.multi_objective.box_decompositions import (
    NondominatedPartitioning,
)
from botorch.utils.multi_objective.hypervolume import Hypervolume
from gpytorch.mlls import SumMarginalLogLikelihood

from .input import InputqEHVISWMM
from .kpi_evaluation import KPIEvaluation
from .output import OutputqEHVISWMM

# Load default config
_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
with open(_CONFIG_PATH, "r", encoding="utf-8") as _f:
    _DEFAULT_CONFIG = yaml.safe_load(_f)


class qEHVISWMM:
    """Multi-objective Bayesian optimization using qEHVI for sedimentation
    maintenance point selection.

    Wraps the BoTorch qLogExpectedHypervolumeImprovement acquisition function
    with SWMM hydraulic simulation as the black-box objective.

    The optimization loop:
        1. Generate initial binary samples via Sobol sequence
        2. Evaluate via SWMM (InputqEHVISWMM + KPIEvaluation)
        3. Fit GP surrogate (ModelListGP)
        4. Optimize qLogEHVI acquisition → continuous candidates
        5. Discretize to binary → evaluate via SWMM
        6. Update Pareto front, check convergence
        7. Repeat 3-6 until converged or max iterations
        8. Extract Pareto set, generate JSON report
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
            config: Optional config dict overriding config.yaml optimization section.
        """
        self._input = input_module
        self._kpi_eval = kpi_evaluator

        cfg = (config or _DEFAULT_CONFIG).get("optimization", _DEFAULT_CONFIG["optimization"])
        self._n_init = cfg["n_init"]
        self._max_iter = cfg["max_iter"]
        self._batch_size = cfg["batch_size"]
        self._num_restarts = cfg["num_restarts"]
        self._raw_samples = cfg["raw_samples"]
        self._mc_samples = cfg["mc_samples"]
        self._patience = cfg["patience"]
        self._seed = cfg["seed"]
        self._ref_point_offset = cfg["ref_point_offset"]

        self._N = input_module.N
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._tkwargs = {"dtype": torch.double, "device": device}
        self._bounds = torch.stack(
            [
                torch.zeros(self._N, **self._tkwargs),
                torch.ones(self._N, **self._tkwargs),
            ]
        )

        # Counter for unique scenario IDs across all evaluations
        self._scenario_counter = 0

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def run(self, output_path: str = "output/report.json") -> dict:
        """Run the full qEHVI optimization loop.

        Args:
            output_path: Path for the JSON report file.

        Returns:
            Dict with keys:
                train_X: all evaluated decision vectors (Tensor)
                train_Y: all KPI vectors (Tensor)
                all_results: list of evaluate() dicts
                pareto_X: Pareto-optimal X (Tensor)
                pareto_Y: Pareto-optimal Y (Tensor)
                report_path: path to JSON report
                n_iterations: number of BO iterations completed
        """
        print(f"qEHVI-SWMM Optimization")
        print(f"  N={self._N}, n_init={self._n_init}, max_iter={self._max_iter}, "
              f"batch_size={self._batch_size}, patience={self._patience}")
        print()

        # --- Step 1: Initial sampling ---
        print(f"Generating {self._n_init} initial samples (Sobol)...")
        sobol = torch.quasirandom.SobolEngine(
            dimension=self._N, scramble=True, seed=self._seed
        )
        train_X = torch.round(sobol.draw(self._n_init)).to(**self._tkwargs)

        print(f"Evaluating initial samples via SWMM...")
        train_Y, all_results = self._evaluate(train_X)
        print(f"  Initial Y mean: {train_Y.mean(dim=0).tolist()}")
        print()

        # --- Step 2: BO loop ---
        hv_history = []
        best_hv = -float("inf")
        stagnation_count = 0

        for iteration in range(self._max_iter):
            print(f"=== Iteration {iteration + 1}/{self._max_iter} ===")

            # Fit GP surrogate (negate Y for maximization)
            neg_Y = -train_Y
            model = self._fit_gp(train_X, neg_Y)

            # Reference point
            ref_point = neg_Y.min(dim=0).values + self._ref_point_offset

            # Partitioning
            partitioning = NondominatedPartitioning(
                ref_point=ref_point, Y=neg_Y
            )

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

            # Optimize acquisition function
            candidate, acqf_value = optimize_acqf(
                acq_function=acqf,
                bounds=self._bounds,
                q=self._batch_size,
                num_restarts=self._num_restarts,
                raw_samples=self._raw_samples,
            )

            # Discretize and evaluate
            new_X = torch.round(candidate.detach()).to(**self._tkwargs)
            print(f"  Evaluating {new_X.shape[0]} new candidates via SWMM...")
            new_Y, new_results = self._evaluate(new_X)

            # Update dataset
            train_X = torch.cat([train_X, new_X])
            train_Y = torch.cat([train_Y, new_Y])
            all_results.extend(new_results)

            # Compute hypervolume for convergence check
            neg_train_Y = -train_Y
            ref_pt = neg_train_Y.min(dim=0).values + self._ref_point_offset
            pareto_mask = NondominatedPartitioning(
                ref_point=ref_pt, Y=neg_train_Y
            )
            hv_calc = Hypervolume(ref_point=ref_pt)
            pareto_Y_neg = neg_train_Y[
                OutputqEHVISWMM.extract_pareto(train_X, train_Y)[2]
            ]
            current_hv = hv_calc.compute(pareto_Y_neg) if pareto_Y_neg.shape[0] > 0 else 0.0
            hv_history.append(current_hv)

            print(f"  New Y mean: [{', '.join(f'{v:.4f}' for v in new_Y.mean(dim=0).tolist())}]")
            print(f"  Total samples: {train_X.shape[0]}, HV: {current_hv:.4f}")

            # Convergence check (disabled when patience == -1)
            if self._patience >= 0:
                if current_hv > best_hv:
                    best_hv = current_hv
                    stagnation_count = 0
                else:
                    stagnation_count += 1

                if stagnation_count >= self._patience:
                    print(f"\n  Converged: HV stagnated for {self._patience} iterations.")
                    break

            print()

        n_iterations = min(iteration + 1, self._max_iter)
        print(f"\nOptimization complete. {n_iterations} iterations, "
              f"{train_X.shape[0]} total evaluations.")

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
        """Evaluate binary decision vectors via SWMM.

        Args:
            X: Binary tensor of shape (n, N).

        Returns:
            (Y, results) where Y is shape (n, 3) and results is list of dicts.
        """
        # Use unique scenario IDs across all evaluations
        paths = []
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

        Y = torch.tensor(
            [r["kpi"] for r in results], **self._tkwargs
        )
        return Y, results

    @staticmethod
    def _fit_gp(
        train_X: torch.Tensor, train_Y: torch.Tensor
    ) -> ModelListGP:
        """Fit independent GP per objective (ModelListGP pattern from test.py).

        Args:
            train_X: shape (n, N)
            train_Y: shape (n, M) — negated KPIs for maximization
        """
        models = []
        for i in range(train_Y.shape[-1]):
            gp = SingleTaskGP(
                train_X,
                train_Y[:, i : i + 1],
                outcome_transform=Standardize(m=1),
            )
            models.append(gp)

        model = ModelListGP(*models)
        mll = SumMarginalLogLikelihood(model.likelihood, model)
        fit_gpytorch_mll(mll)
        return model
