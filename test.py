"""End-to-end test of the BO-SWMM optimization pipeline."""
import os

from src.boswmm import BOSWMM, InputqEHVISWMM, KPIEvaluation
from src.boswmm._config import load_default_config
from src.kpi.froi import FROIComputer, load_expert_matrices
from src.kpi._config import load_default_config as load_kpi_config
from src.scenario.utils.parser import parse_inp

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

# Step 2: FROI computer (shared by every KPI evaluation)
bo_cfg = load_default_config()
kpi_cfg = load_kpi_config()
sections = parse_inp(BASE_INP)

froi = FROIComputer(
    sections,
    exposure_csv=kpi_cfg["data_paths"]["exposure"],
    vulnerability_csv=kpi_cfg["data_paths"]["vulnerability"],
    resilience_csv=kpi_cfg["data_paths"]["resilience"],
    expert_matrices=load_expert_matrices(kpi_cfg["weights"]["expert_matrices"]),
    rainfall_depth_mm=kpi_cfg["indicators"]["fhi"]["rainfall_depth_mm"],
    sim_duration_hours=6.0,  # Site_Drainage_Model runs 6 hours by default
    r4_zeta=kpi_cfg["indicators"]["fri"]["r4_zeta"],
    r4_gamma=kpi_cfg["indicators"]["fri"]["r4_gamma"],
    aggregation_method=kpi_cfg["aggregation"]["method"],
)

# Seed R4 reference from a baseline SWMM run on the unmodified model.
baseline_node, baseline_cond, baseline_hours = KPIEvaluation._run_swmm(BASE_INP)
froi.set_r4_reference_from_baseline(baseline_cond, baseline_hours)

# Step 3: KPI evaluator (thin wrapper around SWMM + FROIComputer)
sedimentation = dict(zip(inp.conduit_names, [0.2, 0.4, 0.3, 0.15, 0.25]))
evaluator = KPIEvaluation(
    inp_sections=sections,
    sedimentation=sedimentation,
    froi_computer=froi,
    mode=bo_cfg["optimization"]["mode"],
)

# Step 4: Optimization
optimizer = BOSWMM(input_module=inp, kpi_evaluator=evaluator)
result = optimizer.run(output_path="temp_data/report.json")

print("\n--- Summary ---")
print(f"Mode             : {result['mode']}")
print(f"Iterations       : {result['n_iterations']}")
print(f"Total evaluations: {result['train_X'].shape[0]}")
print(f"Solutions on front: {result['pareto_X'].shape[0]}")
print(f"Report           : {result['report_path']}")
