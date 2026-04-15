"""Step 4 — OutputqEHVISWMM: extract Pareto set and generate JSON report."""

import json
import os

import torch
from botorch.utils.multi_objective.pareto import is_non_dominated


class OutputqEHVISWMM:
    """Extract Pareto-optimal solutions and generate the optimization report."""

    @staticmethod
    def extract_pareto(
        train_X: torch.Tensor, train_Y: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, list[int]]:
        """Find non-dominated rank-1 solutions (minimization).

        For minimization, a point y dominates y' if y <= y' in all objectives
        and y < y' in at least one. BoTorch's is_non_dominated works on
        maximization, so we negate Y.

        Args:
            train_X: All evaluated decision vectors, shape (n, N).
            train_Y: All KPI vectors, shape (n, 3).

        Returns:
            (pareto_X, pareto_Y, indices) where indices are positions
            in the original train_X/train_Y tensors.
        """
        # is_non_dominated expects maximization → negate for minimization
        pareto_mask = is_non_dominated(-train_Y)
        indices = torch.where(pareto_mask)[0].tolist()
        return train_X[pareto_mask], train_Y[pareto_mask], indices

    @staticmethod
    def generate_report(
        pareto_X: torch.Tensor,
        pareto_results: list[dict],
        conduit_names: list[str],
        output_path: str,
    ) -> str:
        """Generate JSON report with Pareto-optimal solutions.

        Args:
            pareto_X: Pareto decision vectors, shape (p, N).
            pareto_results: List of evaluate() result dicts for Pareto solutions.
            conduit_names: Ordered conduit names mapping index to name.
            output_path: Path to write the JSON report.

        Returns:
            Path to the generated JSON file.
        """
        solutions = []
        for i in range(pareto_X.shape[0]):
            x = pareto_X[i]
            r = pareto_results[i]

            # sed_points = conduit names where x[j] == 1 (maintained)
            sed_points = [
                conduit_names[j]
                for j in range(len(conduit_names))
                if int(x[j].item()) == 1
            ]

            solutions.append(
                {
                    "sed_points": sed_points,
                    "kpi": r["kpi"],
                    "num_flood": r["num_flood"],
                    "volume_flood": r["volume_flood"],
                }
            )

        report = {"solutions": solutions}

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4, ensure_ascii=False)

        return output_path
