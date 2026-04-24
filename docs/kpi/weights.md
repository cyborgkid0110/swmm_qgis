# `src/kpi/weights/` — IFAHP + EWM + Combined Weight Computation

Subjective-and-objective weight fusion per index group. Each group (FHI, FEI, FVI, FRI) gets its own weight vector `ρ` of length `M`, summing to 1.

```
omega  = ifahp_weights(expert_matrices)        # subjective
theta  = ewm_weights(indicator_matrix)         # objective
rho    = combined_weights(omega, theta)        # final
```

All three functions accept plain NumPy arrays and are independent of the rest of the pipeline. They are exercised once at `FROIComputer.__init__` time; the resulting `ρ` vectors are cached for the lifetime of the computer.

---

## IFAHP — Intuitionistic Fuzzy AHP (`ifahp.py`)

Six-step procedure on `K` expert matrices, each of shape `(M, M, 2)` where the last axis holds `(μ, ν)` with `μ + ν ≤ 1`.

```python
from src.kpi.weights import ifahp_weights

result = ifahp_weights([expert_matrix_1, expert_matrix_2], consistency_threshold=0.10)
# result.weights       — (M,), Σ = 1
# result.expert_weights — λ_k for each expert
# result.group_matrix_mu / .group_matrix_nu — aggregated (μ, ν) matrices
# result.cr, .consistent — Consistency Ratio + boolean
# result.indicator_triplets — [(μ_m, ν_m, π_m), …]
```

### Steps

1. **Validate** each expert matrix: `μ + ν ≤ 1`, values in `[0, 1]`.
2. **Expert weights** `λ_k` from per-matrix average membership / non-membership / hesitation.
3. **Aggregate** to the group matrix: `μ_ab = 1 − Π(1 − μ_ab^{(k)})^{λ_k}`.
4. **Consistency Ratio.** The intuitionistic matrix is collapsed to a crisp proxy by the score function `S = μ − ν` mapped via `exp(S · ln 9)` into the Saaty `[1/9, 9]` range. Classical `CI = (λ_max − M) / (M − 1)` and `CR = CI / RI(M)`. Saaty's random-index table is used for `M = 3..15`; `M ≤ 2` returns `CR = 0` (always consistent).
5. **Per-indicator triplets** by row-averaging the group matrix.
6. **Fuzzy entropy** raw weight:
   $$\hat{\omega}_m = -\frac{1}{M \ln 2}\left[\mu_m \ln \mu_m + \nu_m \ln \nu_m + (1 − \pi_m) \ln(1 − \pi_m) − \pi_m \ln 2\right]$$
   Normalized to `Σ ω_m = 1`.

### Edge cases

- Empty expert list → `ValueError`.
- All-zero expert matrix → uniform `λ` fallback.
- Every raw weight is zero (indicators carry no information) → uniform `ω` fallback.

---

## EWM — Entropy Weight Method (`ewm.py`)

Five-step data-driven procedure on an `(N, M)` indicator matrix (N samples × M indicators).

```python
from src.kpi.weights import ewm_weights

theta = ewm_weights(data, directions=[1, 1, -1, 1])
# directions: +1 positive (higher = higher risk), -1 negative (higher = lower risk)
# theta shape (M,), Σ = 1
```

### Steps

1. Min-max standardize per column. Positive: `(x − min) / (max − min)`. Negative: `(max − x) / (max − min)`. A constant column becomes 0.5 everywhere.
2. Proportions `p_nm = r_nm / Σ_n r_nm`.
3. Entropy `e_m = −(1 / ln N) Σ_n p_nm ln p_nm` (with `0 · ln 0 := 0`).
4. Redundancy `d_m = 1 − e_m`, clipped to `[0, ∞)`. Constant columns get `d = 0`.
5. Normalize `θ_m = d_m / Σ d_i`.

### Edge cases

- `N < 2` → uniform fallback (entropy undefined).
- Every column constant → uniform fallback.
- One or more columns constant → those get `θ = 0`, the others renormalize.

---

## Combined weights (`combined.py`)

```python
from src.kpi.weights import combined_weights, preference_coefficients

eps = preference_coefficients(omega, theta)   # ε_m = θ_m^2 / (ω_m^2 + θ_m^2)
rho = combined_weights(omega, theta)          # shape (M,), Σ = 1
```

Formula:
$$\rho_m = \frac{\sqrt{(\varepsilon_m \omega_m)^2 + ((1 − \varepsilon_m) \theta_m)^2}}{\sum_i \sqrt{\cdots}}$$

When `ω_m = θ_m`, `ε = 0.5` (balanced). When `θ ≫ ω`, `ε → 1` and the formula leans on `ω` inside the `εω` term; when `θ ≪ ω`, `ε → 0` and it leans on `θ` inside the `(1-ε)θ` term. This counter-intuitive cross-weighting is the method specified in `weights.md` — it amplifies whichever signal has *less* information (by entropy) relative to the other, balancing confident expert judgments against data with high variance.

Both zero vectors → uniform fallback.
