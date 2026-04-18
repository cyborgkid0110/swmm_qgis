"""Step 4 — OutputqEHVISWMM: extract Pareto set and generate JSON report."""

import json
import os

import matplotlib.pyplot as plt
import numpy as np
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

        Each solution stores the full dense maintenance-volume vector x
        (length N, in m^3). Positions align with report-root `conduit_names`.

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

            x_list = [float(v) for v in x.tolist()]
            total = float(sum(x_list))

            solutions.append(
                {
                    "x": x_list,
                    "total_volume_m3": total,
                    "kpi": r["kpi"],
                    "num_flood": r["num_flood"],
                    "volume_flood": r["volume_flood"],
                }
            )

        report = {"conduit_names": list(conduit_names), "solutions": solutions}

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=4, ensure_ascii=False)

        return output_path

    @staticmethod
    def visualize(
        train_Y: torch.Tensor,
        hv_history: list[float],
        report_path: str,
        output_dir: str = "result/optimization",
    ) -> str:
        """Generate optimization result visualization.

        Produces a figure with 5 panels:
            Top row:     Three 3D scatter plots (views 1-3)
            Bottom-left: HV convergence line chart (red)
            Bottom-right: Table of 3 notable solutions (best F1, F2, F3)

        Args:
            train_Y: All KPI vectors, shape (n, 3).
            hv_history: Hypervolume at each BO iteration.
            report_path: Path to the Pareto report JSON file.
            output_dir: Directory to save figures.

        Returns:
            Path to the saved figure.
        """
        os.makedirs(output_dir, exist_ok=True)

        # Load final Pareto solutions from JSON report
        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        pareto_kpis = np.array([s["kpi"] for s in report["solutions"]])
        conduit_names = report.get("conduit_names", [])
        # Format each dense x vector as "name=volume" pairs for positive entries
        pareto_solutions = []
        for s in report["solutions"]:
            x = s.get("x", [])
            pairs = [
                f"{conduit_names[j] if j < len(conduit_names) else j}={v:.2f}"
                for j, v in enumerate(x)
                if v > 0.0
            ]
            pareto_solutions.append(pairs)

        all_Y = train_Y.cpu().numpy()

        fig = plt.figure(figsize=(20, 14), constrained_layout=True)
        gs = fig.add_gridspec(2, 6)

        # --- Top row: three 3D scatter plots with different viewing angles ---
        # Use a mirrored azimuth for View 2 so F3 appears on the left side.
        views = [(30, 45), (30, -135), (15, 225)]
        for idx, (elev, azim) in enumerate(views):
            ax = fig.add_subplot(gs[0, idx * 2:(idx + 1) * 2], projection="3d")
            ax.scatter(
                all_Y[:, 0], all_Y[:, 1], all_Y[:, 2],
                c="royalblue", alpha=0.4, s=30, label="All evaluated",
            )
            ax.scatter(
                pareto_kpis[:, 0], pareto_kpis[:, 1], pareto_kpis[:, 2],
                c="limegreen", edgecolors="darkgreen", s=80, linewidths=0.8,
                label="Pareto front", zorder=5,
            )
            ax.set_xlabel("F1 (Flood)", labelpad=8)
            ax.set_ylabel("F2 (Drainage)", labelpad=8)
            ax.set_zlabel("F3 (Sediment)", labelpad=8)
            ax.set_title(f"Pareto Front — View {idx + 1}")
            ax.view_init(elev=elev, azim=azim)
            ax.legend(loc="upper left", fontsize=8)

        # --- Bottom-left: HV convergence ---
        ax_hv = fig.add_subplot(gs[1, 0:3])
        iterations = list(range(1, len(hv_history) + 1))
        ax_hv.plot(iterations, hv_history, color="red", linewidth=2, marker="o",
                   markersize=4)
        ax_hv.set_xlabel("Iteration")
        ax_hv.set_ylabel("Hypervolume")
        ax_hv.set_title("Hypervolume Convergence")
        ax_hv.grid(True, alpha=0.3)

        # --- Bottom-right: Table of 3 notable solutions ---
        ax_tbl = fig.add_subplot(gs[1, 3:6])
        ax_tbl.axis("off")

        # Find best (lowest) for each objective among Pareto solutions
        best_indices = [int(np.argmin(pareto_kpis[:, obj])) for obj in range(3)]
        labels = ["Best F1 (Flood)", "Best F2 (Drainage)", "Best F3 (Sediment)"]

        col_labels = ["F1", "F2", "F3", "Solution"]
        cell_text = []
        for label, bi in zip(labels, best_indices):
            kpi = pareto_kpis[bi]
            sol = ", ".join(pareto_solutions[bi])
            cell_text.append([
                f"{kpi[0]:.4f}", f"{kpi[1]:.4f}", f"{kpi[2]:.4f}", sol,
            ])

        table = ax_tbl.table(
            cellText=cell_text,
            rowLabels=labels,
            colLabels=col_labels,
            loc="center",
            cellLoc="center",
        )
        table.auto_set_font_size(False)
        table.set_fontsize(9)
        table.scale(2.0, 3.6)
        table.auto_set_column_width(list(range(len(col_labels))))

        # Style header row
        for j in range(len(col_labels)):
            table[0, j].set_facecolor("#4472C4")
            table[0, j].set_text_props(color="white", fontweight="bold")
        # Style row labels
        for i in range(len(labels)):
            table[i + 1, -1].set_facecolor("#D6E4F0")

        ax_tbl.set_title("Notable Pareto Solutions", pad=20)

        fig.suptitle("qEHVI-SWMM Optimization Results", fontsize=16, fontweight="bold")

        fig_path = os.path.join(output_dir, "optimization_results.png")
        fig.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return fig_path

    @staticmethod
    def visualize_pareto(
        train_Y: torch.Tensor,
        report_path: str,
        output_dir: str = "result/optimization",
    ) -> str:
        """Generate Pareto front focused visualization.

        Produces a figure with 6 panels:
            Top row:    Three 3D scatter plots (different viewing angles)
            Bottom row: Three 2D scatter plots for each objective pair
                        (F1-F2, F1-F3, F2-F3)

        Colors: blue = all evaluated, green = Pareto front.

        Args:
            train_Y: All KPI vectors, shape (n, 3).
            report_path: Path to the Pareto report JSON file.
            output_dir: Directory to save figures.

        Returns:
            Path to the saved figure.
        """
        os.makedirs(output_dir, exist_ok=True)

        with open(report_path, "r", encoding="utf-8") as f:
            report = json.load(f)
        pareto_kpis = np.array([s["kpi"] for s in report["solutions"]])

        all_Y = train_Y.cpu().numpy()

        fig = plt.figure(figsize=(20, 14), constrained_layout=True)
        gs = fig.add_gridspec(2, 6)

        # --- Top row: three 3D scatter plots (each spans 2 columns) ---
        # Keep 3D view orientation consistent with visualize().
        views = [(30, 45), (30, -135), (15, 225)]
        for idx, (elev, azim) in enumerate(views):
            ax = fig.add_subplot(gs[0, idx * 2:(idx + 1) * 2], projection="3d")
            ax.scatter(
                all_Y[:, 0], all_Y[:, 1], all_Y[:, 2],
                c="royalblue", alpha=0.35, s=25, label="All evaluated",
            )
            ax.scatter(
                pareto_kpis[:, 0], pareto_kpis[:, 1], pareto_kpis[:, 2],
                c="limegreen", edgecolors="darkgreen", s=80, linewidths=0.8,
                label="Pareto front", zorder=5,
            )
            ax.set_xlabel("F1 (Flood)", labelpad=8)
            ax.set_ylabel("F2 (Drainage)", labelpad=8)
            ax.set_zlabel("F3 (Sediment)", labelpad=8)
            ax.set_title(f"Pareto Front 3D — View {idx + 1}")
            ax.view_init(elev=elev, azim=azim)
            ax.legend(loc="upper left", fontsize=8)

        # --- Bottom row: three 2D pairwise projections (each spans 2 columns) ---
        obj_names = ["F1 (Flood)", "F2 (Drainage)", "F3 (Sediment)"]
        pairs = [(0, 1), (0, 2), (1, 2)]

        for idx, (i, j) in enumerate(pairs):
            ax = fig.add_subplot(gs[1, idx * 2:(idx + 1) * 2])
            ax.scatter(
                all_Y[:, i], all_Y[:, j],
                c="royalblue", alpha=0.35, s=25, label="All evaluated",
            )
            ax.scatter(
                pareto_kpis[:, i], pareto_kpis[:, j],
                c="limegreen", edgecolors="darkgreen", s=80, linewidths=0.8,
                label="Pareto front", zorder=5,
            )
            ax.set_xlabel(obj_names[i])
            ax.set_ylabel(obj_names[j])
            ax.set_title(f"{obj_names[i]} vs {obj_names[j]}")
            ax.grid(True, alpha=0.3)
            ax.legend(loc="upper right", fontsize=8)

        fig.suptitle(
            "qEHVI-SWMM Pareto Front Analysis", fontsize=16, fontweight="bold"
        )

        fig_path = os.path.join(output_dir, "pareto_front.png")
        fig.savefig(fig_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        return fig_path
