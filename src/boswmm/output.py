"""Step 4 — Output: extract solutions and generate JSON + figures.

Mode-aware output:

  * ``single`` mode: the report contains a single ``best`` entry with the
    minimizing ``x`` and its FROI. Visualization = convergence curve.
  * ``multi`` mode: the report contains the Pareto set, each entry with the
    full KPI vector ``[FHI, FEI, FVI, 1-FRI]`` and its sub-index breakdown.
    Visualization = pairwise 2D projections (6 pairs for 4 objectives) +
    Pareto solutions table.
"""

import itertools
import json
import os

import matplotlib.pyplot as plt
import numpy as np
import torch
from botorch.utils.multi_objective.pareto import is_non_dominated


# Canonical objective labels per mode
_MULTI_OBJ_LABELS = ["FHI", "FEI", "FVI", "1-FRI"]
_SINGLE_OBJ_LABELS = ["FROI"]


class Output:
    """Solution extraction, JSON report, and visualization."""

    # ------------------------------------------------------------------
    # Pareto / best extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_pareto(
        train_X: torch.Tensor, train_Y: torch.Tensor
    ) -> tuple[torch.Tensor, torch.Tensor, list[int]]:
        """Non-dominated rank-1 solutions (minimization).

        BoTorch's ``is_non_dominated`` maximizes, so we negate ``train_Y``.
        """
        pareto_mask = is_non_dominated(-train_Y)
        indices = torch.where(pareto_mask)[0].tolist()
        return train_X[pareto_mask], train_Y[pareto_mask], indices

    # ------------------------------------------------------------------
    # JSON report
    # ------------------------------------------------------------------

    @staticmethod
    def generate_report(
        pareto_X: torch.Tensor,
        pareto_results: list[dict],
        conduit_names: list[str],
        output_path: str,
        mode: str = "multi",
    ) -> str:
        """Write a JSON report with either the Pareto set (multi) or the
        best solution (single). Each solution stores the full dense
        maintenance-volume vector ``x`` (length N, in m^3).
        """
        solutions = []
        for i in range(pareto_X.shape[0]):
            x = pareto_X[i]
            r = pareto_results[i]

            x_list = [float(v) for v in x.tolist()]
            total = float(sum(x_list))

            entry = {
                "x": x_list,
                "total_volume_m3": total,
                "kpi": list(r["kpi"]),
                "froi": r.get("froi"),
                "fhi": r.get("fhi"),
                "fei": r.get("fei"),
                "fvi": r.get("fvi"),
                "fri": r.get("fri"),
                "num_flood": r.get("num_flood"),
                "volume_flood": r.get("volume_flood"),
            }
            solutions.append(entry)

        report = {
            "mode": mode,
            "objective_labels": (
                _MULTI_OBJ_LABELS if mode == "multi" else _SINGLE_OBJ_LABELS
            ),
            "conduit_names": list(conduit_names),
            "solutions": solutions,
        }

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4, ensure_ascii=False)

        return output_path

    # ------------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------------

    @staticmethod
    def visualize(
        train_Y: torch.Tensor,
        progress_history: list[float],
        report_path: str,
        output_dir: str = "result/optimization",
    ) -> str:
        """Convergence + solution summary figure.

        Dispatches on the mode recorded in the JSON report:
          * single → single-panel convergence + best-solution caption.
          * multi  → 4-obj pairwise 2D scatter + convergence.
        """
        os.makedirs(output_dir, exist_ok=True)

        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        mode = report.get("mode", "multi")

        if mode == "single":
            return Output._visualize_single(
                train_Y, progress_history, report, output_dir
            )
        return Output._visualize_multi(
            train_Y, progress_history, report, output_dir
        )

    # --- helpers ---

    @staticmethod
    def _visualize_single(
        train_Y: torch.Tensor,
        progress_history: list[float],
        report: dict,
        output_dir: str,
    ) -> str:
        all_Y = train_Y.cpu().numpy().squeeze(-1)  # (n,) for single obj
        best_sol = report["solutions"][0] if report["solutions"] else None

        fig, (ax_hist, ax_trace) = plt.subplots(1, 2, figsize=(14, 5))

        # Trace of best-so-far per BO iteration
        ax_trace.plot(
            range(1, len(progress_history) + 1),
            progress_history,
            color="red", linewidth=2, marker="o", markersize=4,
        )
        ax_trace.set_xlabel("Iteration")
        ax_trace.set_ylabel("Best-so-far (-FROI)")
        ax_trace.set_title("Convergence")
        ax_trace.grid(True, alpha=0.3)

        # Histogram of evaluated FROI values
        ax_hist.hist(all_Y, bins=30, color="royalblue", alpha=0.7)
        if best_sol is not None:
            ax_hist.axvline(
                best_sol["kpi"][0], color="red", linestyle="--",
                linewidth=2, label=f"best FROI={best_sol['kpi'][0]:.4f}",
            )
            ax_hist.legend()
        ax_hist.set_xlabel("FROI")
        ax_hist.set_ylabel("Count")
        ax_hist.set_title("Distribution of evaluated FROI")
        ax_hist.grid(True, alpha=0.3)

        fig.suptitle("BOSWMM Single-Objective Results", fontsize=14, fontweight="bold")
        fig_path = os.path.join(output_dir, "optimization_results.png")
        fig.tight_layout()
        fig.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return fig_path

    @staticmethod
    def _visualize_multi(
        train_Y: torch.Tensor,
        progress_history: list[float],
        report: dict,
        output_dir: str,
    ) -> str:
        all_Y = train_Y.cpu().numpy()
        labels = report.get("objective_labels", _MULTI_OBJ_LABELS)
        M = all_Y.shape[1]
        pareto_kpis = np.array(
            [s["kpi"] for s in report["solutions"]]
        ) if report["solutions"] else np.empty((0, M))

        # Pairwise pairs: C(M, 2). For M=4 this is 6.
        pairs = list(itertools.combinations(range(M), 2))

        # Layout: pairs grid + one convergence subplot
        n_pairs = len(pairs)
        cols = 3
        rows = (n_pairs + 2) // cols + 1  # extra row for convergence
        fig = plt.figure(figsize=(5 * cols, 4 * rows), constrained_layout=True)
        gs = fig.add_gridspec(rows, cols)

        for idx, (i, j) in enumerate(pairs):
            r, c = divmod(idx, cols)
            ax = fig.add_subplot(gs[r, c])
            ax.scatter(
                all_Y[:, i], all_Y[:, j],
                c="royalblue", alpha=0.35, s=25, label="All evaluated",
            )
            if pareto_kpis.shape[0] > 0:
                ax.scatter(
                    pareto_kpis[:, i], pareto_kpis[:, j],
                    c="limegreen", edgecolors="darkgreen", s=80, linewidths=0.8,
                    label="Pareto front", zorder=5,
                )
            ax.set_xlabel(labels[i])
            ax.set_ylabel(labels[j])
            ax.set_title(f"{labels[i]} vs {labels[j]}")
            ax.grid(True, alpha=0.3)
            ax.legend(loc="upper right", fontsize=8)

        # Convergence subplot on the last row
        ax_hv = fig.add_subplot(gs[rows - 1, :])
        ax_hv.plot(
            range(1, len(progress_history) + 1),
            progress_history,
            color="red", linewidth=2, marker="o", markersize=4,
        )
        ax_hv.set_xlabel("Iteration")
        ax_hv.set_ylabel("Hypervolume")
        ax_hv.set_title("Hypervolume Convergence")
        ax_hv.grid(True, alpha=0.3)

        fig.suptitle(
            "BOSWMM Multi-Objective Results", fontsize=14, fontweight="bold"
        )
        fig_path = os.path.join(output_dir, "optimization_results.png")
        fig.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return fig_path
