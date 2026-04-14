Here is a detailed explanation of Section 3, building each subsection step by step.

---

## Section 3: Differentiable q-Expected Hypervolume Improvement — Detailed Explanation

*(Note: the markdown file contains the section in Vietnamese, but the content is mathematically identical to the original English paper. All explanations below are sourced from Section 3, pp. 3–5.)*

---

### Foundational Definitions

Before deriving qEHVI, the paper establishes three definitions (Section 3, opening).

**Definition 1 — Hypervolume (HV):** Given a reference point r ∈ ℝᴹ (a user-specified lower bound on acceptable objective values), the hypervolume of a Pareto set P is the M-dimensional Lebesgue measure of the space that P dominates and that lies above r:

$$\text{HV}(\mathcal{P}, r) = \lambda_M\left(\bigcup_{i=1}^{|\mathcal{P}|} [r, y_i]\right)$$

Intuitively, the larger this dominated volume, the better the Pareto front is covering the objective space.

**Definition 2 — Hypervolume Improvement (HVI):** Given a current Pareto set P and a new set of points Y, the HVI is simply how much the hypervolume grows when Y is added:

$$\text{HVI}(\mathcal{Y}, \mathcal{P}, r) = \text{HV}(\mathcal{P} \cup \mathcal{Y}, r) - \text{HV}(\mathcal{P}, r)$$

**EHVI** is then the *expected* value of HVI taken over the GP posterior: $\alpha_{\text{EHVI}}(\mathcal{X}_\text{cand}) = \mathbb{E}[\text{HVI}(f(\mathcal{X}_\text{cand}))]$. For the sequential q=1 case with independent GPs, this has a closed-form expression; for q > 1 or correlated outputs, it must be approximated via Monte Carlo integration.

---

### 3.1 — HVI via Box Decomposition (single point, q = 1)

The core challenge is that the region Δ({f(x)}, P, r) — the space newly dominated by a candidate f(x) but not already dominated by P — is in general a **non-rectangular polytope**. This makes direct volume computation hard.

The solution is to **partition the non-dominated space** into K disjoint axis-aligned hyper-rectangles {Sₖ}ₖ₌₁ᴷ. Each rectangle Sₖ has a lower vertex lₖ ∈ ℝᴹ and an upper vertex uₖ ∈ ℝᴹ ∪ {∞}. The key geometric insight is: even though Δ is non-rectangular, its intersection with any individual box Sₖ *is* a rectangle. Therefore the volume in each box is easy to compute.

For a single new point f(x), its upper bound within Sₖ is the component-wise minimum:

$$z_k := \min[u_k, f(x)]$$

The HVI contribution within Sₖ is then:

$$\text{HVI}_k(f(x), l_k, u_k) = \prod_{m=1}^{M}\left[z_k^{(m)} - l_k^{(m)}\right]_+$$

where $[\cdot]_+$ clamps negative values to zero (i.e., if f(x) does not reach lₖ in any dimension, the contribution is zero). Summing over all K boxes gives the total HVI (Equation 1):

$$\text{HVI}(f(x)) = \sum_{k=1}^{K} \prod_{m=1}^{M}\left[z_k^{(m)} - l_k^{(m)}\right]_+$$

---

### 3.2 — Extending to q > 1 via the Inclusion-Exclusion Principle

*(Section 3.2, pp. 4–5)*

When evaluating q candidates simultaneously, the challenge is that their individually dominated regions Aᵢ = Δ({f(xᵢ)}, P, r) **overlap**. The joint HVI is the volume of the *union* of all Aᵢ, not their sum. Naively summing would double-count overlaps.

The paper resolves this with the **inclusion-exclusion principle**. Define each Aᵢ independently (as if the other q−1 points do not exist). Then:

$$\text{HVI}(\{f(x_i)\}_{i=1}^q) = \lambda_M\left(\bigcup_{i=1}^q A_i\right) = \sum_{j=1}^{q}(-1)^{j+1} \sum_{1 \leq i_1 \leq \dots \leq i_j \leq q} \lambda_M(A_{i_1} \cap \dots \cap A_{i_j}) \quad (2)$$

The alternating sign pattern adds singletons, subtracts pairwise intersections, adds triple intersections, and so on. To compute each intersection term, the same box decomposition trick applies — since {Sₖ} is a disjoint partition:

$$\lambda_M(A_{i_1} \cap \dots \cap A_{i_j}) = \sum_{k=1}^K \lambda_M(S_k \cap A_{i_1} \cap \dots \cap A_{i_j})$$

Within each box Sₖ, the intersection $S_k \cap A_{i_1} \cap \dots \cap A_{i_j}$ is again a rectangle. Its upper bound is:

$$z_{k, X_j}^{(m)} := \min\left(u_k^{(m)},\ \min_{x' \in X_j} f^{(m)}(x')\right)$$

i.e., the component-wise minimum of the box ceiling and all candidate values in the subset Xⱼ. This yields the final closed-form expression for q-HVI (Equation 3):

$$\text{HVI}(\{f(x_i)\}_{i=1}^q) = \sum_{k=1}^{K}\sum_{j=1}^{q}\sum_{X_j \in \mathcal{X}_j}(-1)^{j+1}\prod_{m=1}^{M}\left[z_{k,X_j}^{(m)} - l_k^{(m)}\right]_+$$

The paper highlights three key advantages of this formulation: (1) all intersection regions are rectangular, simplifying volume computation; (2) the upper bound zₖ,Xⱼ of each intersection is trivially derived as a component-wise minimum; (3) the entire computation over all K boxes and all 2^q − 1 subsets is **embarrassingly parallel**, enabling GPU acceleration.

---

### 3.3 — Monte Carlo Estimation of qEHVI

*(Section 3.3, p. 5)*

In Bayesian optimization, the true values f(xᵢ) are unknown — only the GP posterior is available. The acquisition function is therefore defined as the expectation over the posterior (Equation 4):

$$\alpha_{q\text{EHVI}}(\mathcal{X}_\text{cand}) = \mathbb{E}[\text{HVI}(f(\mathcal{X}_\text{cand}))] = \int_{-\infty}^{\infty} \text{HVI}(f(\mathcal{X}_\text{cand}))\, df$$

Since no closed-form expression exists for q > 1 (or for correlated outputs), this is approximated by drawing N samples from the joint posterior: $\{f_t(x_i)\}_{i=1}^q \sim P(f(x_1), \dots, f(x_q) \mid \mathcal{D})$, yielding the MC estimator (Equation 5):

$$\hat{\alpha}^N_{q\text{EHVI}}(\mathcal{X}_\text{cand}) = \frac{1}{N}\sum_{t=1}^{N}\sum_{k=1}^{K}\sum_{j=1}^{q}\sum_{X_j \in \mathcal{X}_j}(-1)^{j+1}\prod_{m=1}^{M}\left[z_{k,X_j,t}^{(m)} - l_k^{(m)}\right]_+$$

where $z_{k,X_j,t}^{(m)} = \min\left(u_k^{(m)}, \min_{x' \in X_j} f_t^{(m)}(x')\right)$ uses the t-th posterior sample. The MC error scales as 1/√N regardless of search space dimension, and in practice **randomized quasi-MC (QMC)** methods (N = 128 samples) further reduce variance.

**Computational complexity:** On a single-threaded machine, the time complexity is T₁ = O(MNK(2^q − 1)). However, since all iterations over k, j, and Xⱼ are independent, the critical path (the minimum non-parallelizable work unit) is T∞ = O(1) — meaning with sufficient GPU cores, wall time is theoretically constant. In practice, computation time remains nearly flat as q increases until the available GPU cores are saturated.

---

### 3.4 — Outcome Constraints

*(Section 3.4, p. 5–6)*

To handle V black-box constraints c^(v)(x) ≥ 0, the feasible HVI for a single candidate is defined as:

$$\text{HVI}_C(f(x), c(x)) := \text{HVI}[f(x)] \cdot \mathbf{1}[c(x) \geq 0]$$

In the parallel setting, an infeasible candidate contributes zero marginal HVI — its contribution is zeroed out from the inclusion-exclusion sum by multiplying each subset term by a feasibility indicator over all members of that subset. For differentiability, the hard indicator is replaced by a **sigmoid approximation**:

$$\mathbf{1}[c^{(v)}(x') \geq 0] \approx s(c^{(v)}(x'); \epsilon) = \frac{1}{1 + \exp(-c^{(v)}(x')/\epsilon)}$$

which becomes exact as ε → 0. Importantly, the paper proves (Theorem 1, Appendix A.3) that HVIC is mathematically equivalent to an unconstrained HVI computed in an augmented (M + V)-dimensional objective space, confirming that the inclusion-exclusion structure remains valid under constraints.

---

### Visual Summary---

### How the four subsections connect

Section 3.1 establishes the single-point building block: decompose the non-dominated space into rectangles so that volume computation becomes a simple product. Section 3.2 extends this to q > 1 using inclusion-exclusion, which handles overlapping dominated regions exactly without ever computing a Pareto front per sample. Section 3.3 wraps everything in a Monte Carlo expectation over the GP posterior, making the formulation compatible with the unknown-function BO setting. Section 3.4 adds constraints by multiplying each subset's volume contribution by a feasibility indicator (approximated differentiably with a sigmoid), which slots directly into the existing sum without any structural change to the formula.