# REPORT ON PROPOSED COMPREHENSIVE OBJECTIVE FUNCTION FOR URBAN SEWER NETWORK EVALUATION

---

# 1. PROBLEM STATEMENT

## 1.1. Related Studies

Existing studies approach the problem of sewer network evaluation in a fragmented manner: some works focus on rehabilitation investment costs (Cunha et al., 2019; Pan et al., 2025), others assess economic damage (Jafar et al., 2022), while others examine pipe asset condition (Aljafari et al., 2022; Lisandro et al., 2024) or composite risk indices (Shakeel et al., 2025). Each approach provides a valuable perspective but has its own limitations:

- Pure economic objective functions ignore hydraulic constraints (self-cleaning velocity, Q/Q_full ratio), leading to low-cost solutions that are prone to sediment accumulation.
- Isolated hydraulic indicators (flood volume, overflow duration) do not reflect economic impacts and long-term maintenance burdens.
- Most studies have not integrated sedimentation as a dynamic state variable affecting both hydraulic capacity and operational costs.
- Decision-making based on multiple discrete, unlinked KPIs lacks consistency and is difficult to apply in multi-objective optimization problems.

This reality creates an urgent need for a comprehensive objective function capable of simultaneously integrating three evaluation dimensions — network condition, sedimentation, and flooding — to serve sewer network optimization problems.

## 1.2. Research Objectives

This report aims at two specific objectives:

1. Review and critically analyze KPIs and objective functions used in urban sewer network research.
2. Propose a multi-component objective function integrating hydraulics (F₁), drainage capacity (F₂), and sedimentation–maintenance (F₃).

---

# 2. REVIEW OF OBJECTIVE FUNCTIONS FOR SEWER NETWORK EVALUATION

## 2.1. Studies Reviewed

Table 1 summarizes the reviewed studies, classified by KPI or objective function used and the KPI calculation method.

**Table 1. Summary of KPIs and Objective Functions from Reviewed Studies**

| No. | Paper Title | KPI / Objective Function | Calculation Method |
|-----|-------------|--------------------------|-------------------|
| 1 | Multi-Objective Optimization for Urban Drainage or Sewer Networks Rehabilitation through Pipes Substitution and Storage Tanks Installation (2019, Cunha et al.) | - Investment cost <br> - Flood damage cost | - KPI 1 = total pipe replacement cost + storage tank installation cost <br> - KPI 2 = damage at nodes (nonlinear function of flood depth) |
| 2 | Vulnerability Analysis of Urban Drainage Systems: Tree vs. Loop Networks (2017, Zhang et al.) | - Vulnerability Index (VI) <br> - Overflow flow ratio | - KPI 1 = average overflow ratio when each pipe is blocked (simulating diameter → 0) |
| 3 | Condition Modeling of Railway Drainage Pipes (2022, Aljafari et al.) | - Structural condition score (STRC) <br> - Service condition score (SRVC) | Multi-class classification (NN, DT, KNN) on CCTV inspection data; scale 1–5 |
| 4 | Development of a risk-based optimization approach to improve the performance of urban drainage systems (2022, Jafar et al.) | - Expected Annual Damage (EAD) <br> - Annual benefit/cost ratio (EAB/AC) | - EAD = applying MCS over multiple rainfall scenarios <br> - EAB/AC = (baseline damage − post-intervention damage) / annual cost |
| 5 | Graph method for critical pipe analysis of branched and looped drainage networks (2023, Dastgir et al.) | - $EBC_{e}^{R}$ (Flow edge betweenness centrality) <br> - $EBC_{e}^{C}$ (Capacity edge betweenness centrality) | - $EBC_{e}^{R}$ = total contributing flow area through the pipe (shortest path) <br> - $EBC_{e}^{C}$ = Manning–Strickler capacity |
| 6 | Exploring the driving factors of urban flood at the catchment scale (2024, Zhang et al.) | - River network density <br> - Building density <br> - Coverage ratio <br> - Building crowding index <br> - Topographic Wetness Index (TWI) | - KPI 1 = river length in catchment / catchment area <br> - KPI 2 = number of buildings / catchment area <br> - KPI 3 = total building footprint area / catchment area <br> - KPI 4 = total building volume / (catchment area × minimum catchment elevation) <br> - KPI 5 = ln(contributing area / tan(terrain slope)) |
| 7 | Maintenance Strategies for Sewer Pipes with Multi-State Degradation and Deep Reinforcement Learning (2024, Lisandro et al.) | - Health state vector <br> - Policy cost <br> - Reward function | - KPI 1: Normalize number of segments at each severity level k (nd_k) over total segments (nd). <br> - KPI 2: <br>&nbsp;&nbsp;- Maintenance cost (C_M): calculated based on severity level and fixed cost. <br>&nbsp;&nbsp;- Replacement cost: based on pipe length and diameter. <br> - KPI 3: Sum of all costs (maintenance, replacement, failure), normalized. |
| 8 | Generalization of an intelligent real-time flood prediction model… considering the effect of drainage pipeline siltation (2025, Di et al.) | - Equivalent siltation coefficient (CSC) <br> - Pipe Siltation Index (SI) | - CSC = total sediment volume / total network volume <br> - SI = average (siltation length/pipe length + siltation thickness/pipe diameter) |
| 9 | Optimization Study of Drainage Network Systems Based on the SWMM for the Wujin District (2025, Pan et al.) | - Nash–Sutcliffe Efficiency (NSE) <br> - Peak flow error <br> - LID cost function | Calibrate SWMM using NSE; optimize LID measure costs |
| 10 | Building resilient urban drainage systems by integrated flood risk index for evidence-based planning (2025, Shakeel et al.) | Flood Risk Index (FRI) comprising three main components: socioeconomic pressure, drainage system condition, and effectiveness of green infrastructure measures. | - Normalize indices <br> - Assign weights using Analytic Hierarchy Process (AHP) <br> - Calculate component indices <br> - Aggregate FRI |

## 2.2. Analysis by Approach Group

### 2.2.1. Cost and Economic Approach Group

- Cunha et al. (2019) used NSGA-II to simultaneously optimize rehabilitation costs and flood damage, laying the foundation for multi-objective optimization in this field.
- Jafar et al. (2022) went further by applying Monte Carlo simulation to calculate Expected Annual Damage (EAD) — a probabilistic risk-based approach more suitable for uncertain rainfall conditions.
- Pan et al. (2025) focused on optimizing the costs of Low Impact Development (LID) measures within the SWMM framework. The common thread of this group is providing a clear economic basis for investment decisions, but all lack integration of sedimentation factors and detailed hydraulic constraints.

### 2.2.2. Sewer Network Condition Approach Group

Aljafari et al. (2022) and Lisandro et al. (2024) focused on degradation modeling and maintenance planning based on the physical condition of pipes. Aljafari et al. used machine learning to classify pipe condition on a 1–5 scale based on CCTV inspection data, while Lisandro et al. applied deep reinforcement learning to optimize maintenance policy under multi-state degradation. Both methods enable forecasting of future maintenance needs, but neither directly links to flow hydraulics and drainage efficiency.

### 2.2.3. Risk and Spatial Analysis Approach Group

- Shakeel et al. (2025) proposed a Flood Risk Index (FRI) integrating three groups of pressure–state–response indicators, weighted using AHP and normalized to a [0–100] scale.
- Zhang et al. (2024) used Getis-Ord Gi* hotspot analysis and geographically weighted spatial regression to identify urban morphological factors driving flooding at the catchment scale. Zhang et al. (2017) assessed structural vulnerability through simulated hypothetical blockages in individual pipes.
- Dastgir et al. (2023) developed a graph-theory-based betweenness centrality index to identify the most critical pipes without requiring dynamic simulation.

The strength of this group lies in its ability to spatially locate network weaknesses; the limitation is the lack of economic and sedimentation integration.

### 2.2.4. Sedimentation Research

Di et al. (2025) is the only study in the reviewed set that directly incorporates sedimentation into the quantitative evaluation model. The Equivalent Siltation Coefficient (CSC) and Pipe Siltation Index (SI) were proposed as correction inputs for a real-time flood prediction model. However, this study does not integrate results with system optimization or maintenance cost assessment.

## 2.3. Research Gaps

From the above analysis, three main research gaps are identified:

- Lack of an objective function that considers all three factors — flooding, hydraulics, and sedimentation — within a SWMM-based multi-objective optimization framework. Existing studies either separate economics from hydraulics, or completely disregard sedimentation.
- Lack of weight balance analysis between factors based on objectives of flood reduction, maintenance cost, and network design.

---

# 3. RESEARCH METHODOLOGY

## 3.1. General Framework

The sewer network optimization problem is formulated as a multi-objective optimization problem:

$$\min\ F(x)\ =\ [F_1(x),\ F_2(x),\ F_3(x)]$$

where **$x$** is the decision variable vector (e.g., upgraded pipe diameters, detention tank volumes, pipe dredging schedules). The three component objective functions represent:

- Flood Severity Index (F₁)
- Drainage Capacity Index (F₂)
- Sedimentation–Maintenance Index (F₃)

## 3.2. F₁ — Flood Severity Index (FSI)

F₁ quantifies the severity of flooding at nodes, accounting for both flood volume and flood duration, adjusted by the importance of each node:

$$F_1(x) = \sum_{i} w_i \cdot \left[ \alpha \cdot \frac{V_i^{flood}}{V_i^{ref}} + \beta \cdot \frac{T_i^{flood}}{T^{ref}} \right]$$

where:

- **$N$**: total number of nodes in the network
- **$w_i$**: importance weight of node i (determined by land use, population density in the corresponding area)
- **$V_i^{flood}$**: flood volume at node i (m³), extracted from SWMM
- **$V_i^{ref}$**: reference normalization volume (m³), may be taken as the total rainfall volume reaching node i during the design storm
- **$T_i^{flood}$**: flood duration at node i (hours), extracted from SWMM
- **$T^{ref}$**: reference duration (hours), typically taken as the total design storm duration
- **$α, β$**: weighting coefficients for the importance of flood volume and duration (α + β = 1)

*Formula reference: Dastgir et al. (2023), Yazdi et al. (2022), Cunha et al. (2019)*

## 3.3. F₂ — Drainage Capacity Index

F₂ evaluates the operational condition of the pipe system, penalizing pipes that are surcharged or operating beyond safe thresholds:

$$F_2(x) = \sum_{j=1}^{M} L_j \cdot \left[ \zeta \cdot \frac{I_j}{I_j^{full}} + \gamma \cdot \frac{T_j^{surch}}{T^{ref}} - \delta \cdot \frac{Q_j}{Q_j^{full}} \right]$$

where:

- **$M$**: total number of pipe segments in the network
- **$L_j$**: length of pipe segment j (m), used as a spatial weight
- **$T_j^{surch}$**: surcharge duration of pipe j (hours), extracted from SWMM
- **$I_j / I_j^{full}$**: ratio of actual inflow to full-pipe capacity of pipe j, extracted from SWMM
- **$Q_j / Q_j^{full}$**: ratio of actual discharge flow to full-pipe capacity of pipe j, extracted from SWMM
- **$ζ, γ, δ$**: weighting coefficients adjusting the relative importance of each component

*Formula reference: Dastgir et al. (2023)*

## 3.4. F₃ — Sedimentation–Maintenance Index

F₃ reflects the long-term operational burden due to sedimentation, encompassing both the physical extent of sedimentation and the corresponding maintenance costs:

$$F_3(x)\ =\ \sum_{j} \left[ \mu \cdot \frac{S_j L_j}{C_j^{cap}} + \nu \cdot \frac{C_j^{maint}}{C_j^{cap}} \right]$$

where:

- **$S_j$**: sedimentation accumulation rate in pipe j (m³/m/year or kg/m/year)
- **$C_j^{cap}$**: full storage volume of pipe j (m³)
- **$C_j^{maint}$**: estimated sediment volume requiring dredging/maintenance in pipe j (VND/year)
- **$μ, ν$**: weighting coefficients

The sedimentation rate **$S_j$** can be estimated via SWMM's water quality module, a simplified sediment transport model (e.g., Engelund–Hansen), or from field survey data of pipe conditions in the study area. The SI index proposed by Di et al. (2025) can be used directly as a proxy for **$S_j$** when survey data is available.

*Formula reference: Di et al. (2025)*

---

# 4. CONCLUSION

This report has proposed a three-component comprehensive objective function **[F₁, F₂, F₃]** for evaluating urban sewer networks within a multi-objective optimization framework combined with SWMM simulation. The main contributions include:

- Synthesis and analysis of related studies, identifying three gaps: lack of sedimentation integration, lack of multi-dimensional standardization, and lack of weight sensitivity analysis in the Vietnamese context.
- Proposing F₁ to quantify flood severity by volume and duration weighted by node importance; F₂ to evaluate pipe operational condition with self-cleaning velocity constraints; F₃ to quantify sedimentation burden and maintenance costs.

---

# REFERENCES

**[1]** Cunha et al. (2019). Multi-Objective Optimization for Urban Drainage or Sewer Networks Rehabilitation through Pipes Substitution and Storage Tanks Installation.

**[2]** Zhang et al. (2017). Vulnerability Analysis of Urban Drainage Systems: Tree vs. Loop Networks.

**[3]** Aljafari et al. (2022). Condition Modeling of Railway Drainage Pipes.

**[4]** Jafar et al. (2022). Development of a risk-based optimization approach to improve the performance of urban drainage systems.

**[5]** Dastgir et al. (2023). Graph method for critical pipe analysis of branched and looped drainage networks.

**[6]** Zhang et al. (2024). Exploring the driving factors of urban flood at the catchment scale.

**[7]** Lisandro et al. (2024). Maintenance Strategies for Sewer Pipes with Multi-State Degradation and Deep Reinforcement Learning.

**[8]** Di et al. (2025). Generalization of an intelligent real-time flood prediction model… considering the effect of drainage pipeline siltation.

**[9]** Pan et al. (2025). Optimization Study of Drainage Network Systems Based on the SWMM for the Wujin District.

**[10]** Shakeel et al. (2025). Building resilient urban drainage systems by integrated flood risk index for evidence-based planning.