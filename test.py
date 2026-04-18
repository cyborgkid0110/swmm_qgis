"""End-to-end test of the qEHVI-SWMM optimization pipeline."""
import os

from src.qehvi_swmm import InputqEHVISWMM, KPIEvaluation, OutputqEHVISWMM, qEHVISWMM

# Create test sedimentation CSV
os.makedirs("temp_data", exist_ok=True)
with open("temp_data/sed.csv", "w") as f:
    f.write("conduit,filled_depth\n")
    f.write(
        "C1,0.2\nC2,0.35\nC3,0.4\nC4,0.1\nC5,0.3\n"
        "C6,0.25\nC7,0.15\nC8,0.45\nC9,0.25\nC10,0.3\nC11,0.2\n"
    )

# Step 1: Input
inp = InputqEHVISWMM(
    base_inp_path="models/Site_Drainage_Model.inp",
    sedimentation_csv="temp_data/sed.csv",
    output_dir="temp_data/scenarios",
)

# Step 2: KPI Evaluator — reuse parsed base sections from the builder
sedimentation = inp.filled_depths
evaluator = KPIEvaluation(inp_sections=inp.base_sections, sedimentation=sedimentation)

# Step 3+4: Optimization
optimizer = qEHVISWMM(input_module=inp, kpi_evaluator=evaluator)
result = optimizer.run(output_path="result/optimization/report.json")

print(f"\n--- Summary ---")
print(f"Iterations: {result['n_iterations']}")
print(f"Total evaluations: {result['train_X'].shape[0]}")
print(f"Pareto solutions: {result['pareto_X'].shape[0]}")
print(f"Report: {result['report_path']}")

# Step 5: Visualization
fig_path = OutputqEHVISWMM.visualize(
    train_Y=result["train_Y"],
    hv_history=result["hv_history"],
    report_path="result/optimization/report.json",
    output_dir="result/optimization",
)
print(f"Visualization: {fig_path}")

pareto_path = OutputqEHVISWMM.visualize_pareto(
    train_Y=result["train_Y"],
    report_path="result/optimization/report.json",
    output_dir="result/optimization",
)
print(f"Pareto analysis: {pareto_path}")
