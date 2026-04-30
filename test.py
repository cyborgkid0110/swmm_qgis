"""End-to-end test of the BO-SWMM optimization pipeline."""
import os

from src.boswmm import BOSWMM, InputqEHVISWMM, KPIEvaluation

# Create test sedimentation CSV
os.makedirs("temp_data", exist_ok=True)
with open("temp_data/sed.csv", "w") as f:
    f.write("conduit,filled_depth\n")
    f.write("C1,0.2\nC3,0.4\nC5,0.3\nC7,0.15\nC9,0.25\n")

BASE_INP = "models/Site_Drainage_Model.inp"

# Step 1: Input (scenario builder)
inp = InputqEHVISWMM(
    base_inp_path=BASE_INP,
    sedimentation_csv="temp_data/sed.csv",
    output_dir="temp_data/scenarios",
)

# Step 2: KPI evaluator (loads configs + builds FROIComputer internally)
evaluator = KPIEvaluation(base_inp_path=BASE_INP)

# Step 3: Optimization
optimizer = BOSWMM(input_module=inp, kpi_evaluator=evaluator)
result = optimizer.run(output_path="temp_data/report.json")

print("\n--- Summary ---")
print(f"Mode             : {result['mode']}")
print(f"Iterations       : {result['n_iterations']}")
print(f"Total evaluations: {result['train_X'].shape[0]}")
print(f"Solutions on front: {result['pareto_X'].shape[0]}")
print(f"Report           : {result['report_path']}")
