# 文献调研报告：锂离子电池高镍正极容量保持率：衰减机理与改性策略综述

> 生成日期：2026-08-02 | 覆盖 174 篇文献（sciverse）
> 证据追溯：论文 ID（p1-p174）↔ DOI 见文末参考文献表

---

## 1. 执行摘要

高镍层状氧化物正极（LiNixMnyCozO2, x≥0.6；NCA；LiNiO2 基）因其高比容量（~200-275 mAh/g）成为下一代高能量密度锂离子电池的核心候选材料，但其**容量保持率**（capacity retention）受限于多重衰减机制：H2→H3 相变引起的各向异性体积变化与微裂纹（p10, p11, p27）、晶格氧损失与层状→尖晶石→岩盐表面相变（p28, p5）、过渡金属溶解与 CEI 生长（p5, p33, p34）、阳离子混排（p43）以及电解液氧化（p32, p35）。

本调研揭示三组核心构效关系：(1) **Ni 含量-保持率 trade-off**——Ni 含量每升高，初始容量近似线性增加但保持率与热安全成比例下降（p8, p10, p11）；(2) **单晶/多晶形貌矛盾的保持率结论**（p1 vs p62/p67）；(3) **掺杂/包覆/电解液/浓度梯度四类改性普遍提升保持率**，其中 LiNbO3 包覆使 NCM811 的 500 循环保持率从 19% 提升至 70%（p5），1 mol% Al 掺杂使 NMC76 在 4.5V 下 500 循环保持 79.2%（p41），高浓度双盐醚电解液使 Li‖NCM83 150 循环保持 ~95%（p32）。

识别出 6 项研究空白，其中**单晶 vs 多晶矛盾**（Gap 1）、**Co 角色矛盾**（Gap 2）、**掺杂描述符-保持率定量关系缺失**（Gap 3）为高优先级，将作为阶段二构效关系发现的假设来源。

---

## 2. 文献综述

### 2.1 容量衰减机理

**微裂纹主导论**：Ni-rich NCM/NCA 在 ~4.2 V 发生 H2→H3 相变，伴随各向异性晶格体积变化（c 轴突缩），在多晶二次颗粒内沿晶界产生微裂纹（p10, p11, p27）。微裂纹使电解液渗入颗粒内部，加速内部一次颗粒表面退化。NCA 系列（Ni=0.80/0.88/0.95）在充电至 3.9 V 即开始出现微裂纹，且 Ni 含量越高，裂纹传播至颗粒表面的电位越低（p11）。浓度梯度/核壳设计（p49, p59, p74, p150, p153）通过壳层富 Mn 缓冲 H2-H3 应变，显著延长循环寿命。

**表面相变主导论**：界面化学反应使过渡金属价态降低，生成无序岩盐相，进而引发 TM 溶解与不可逆容量损失（p5）。高电压（4.5/4.7V）下晶格氧氧化（与 H2→H3 重叠的容量区间）导致不可逆氧释放，驱动层状-尖晶石-岩盐相变（p28）。Co 在深充电态驱动氧空位形成，诱导晶内裂纹（p103）。

**动力学/结构论**：单晶内 Li 浓度空间不均 → 两相共存（晶胞尺寸差异大）→ 非均匀应力 → 结构缺陷 → Li+ 扩散受阻 → 快速衰减，高倍率与高 Ni 含量加剧（p1, p2）。逐层脱锂导致晶格坍缩与平面滑移（p83）。容量衰减呈非线性滚降特征（p75），与体相结构退化相关（p166）。

### 2.2 形貌工程：单晶 vs 多晶（核心争议）

单晶（SC）正极消除晶间晶界，被认为抗微裂纹、降低寄生表面反应（p12, p17, p50, p56, p64, p84）。但 Ryu et al.（p1, p2）系统对比发现，~3 μm 单晶 NCM（x=0.7/0.8/0.9）的容量与循环稳定性**劣于**多晶，归因于单晶内 Li 浓度不均。相反，多篇工作报道单晶获得超稳定循环：自发应变缓冲设计（p62）、低应变单晶（p87）、亚微米单晶 LiNi0.8Mn0.2O2（p146）、软包电池中单晶循环改善（p121）。全电池层面，单晶 NMC//石墨在 V<4.3V 时低截止电压不影响 100 循环保持率，但 V>4.3V 时氧释放+深放电深度协同加速老化（p22）。**粒径、电压、倍率、Ni 含量的耦合效应尚未系统解耦——这是 Gap 1。**

### 2.3 掺杂改性（元素 × 基体 × 用量）

- **Al**：1 mol% Al 掺杂 NMC76 在 4.5V 下 500 循环保持 79.2%（p41）；Al 稳定 CEI、减少晶格变化（p8）；等价位 Al vs 高价 Ti 定量对比（p25）
- **Zr**：Zr 掺杂富锂 LNO 提升 4.5V 循环稳定性（p40）；Zr-Ti 双掺杂抑制氧释放（p39）
- **Mg**：柱撑效应抑制各向异性晶格坍缩，提升热稳定性（p9）；Mg 掺杂 LiNiO2 的 Li/Ni 双位点效应（p170）
- **Mo**：Mo 掺杂单晶抑制氧空位与晶内裂纹（p18）；Mo 引入无钴高镍（p129）
- **B/Sn-B**：NMC90-5-5 在 25/45/-5°C 全面改善（p43）
- **Fe/Zr**：共掺杂 LiNi0.8Mn0.2O2 达 207.06 mAh/g（0.1C）、200 循环保持 81.55%（p44）
- **卤素（Br/Cl/F）**：5 mol% LiBr/LiCl 提升比表面积、稳定 CEI（p23）
- 其他：Y（p60）、Ce（p122, p132）、Nb（p127, p138）、W（p123）、高熵 Cu/Fe+Zr（p157）、非均匀掺杂（p108）

### 2.4 表面包覆

LiNbO3 包覆单晶 NCM811：500 循环保持率 19%→70%（p5）；Li3PO4 添加剂使 LNMO 全电池 1000 循环 >90%（p42）；钙钛矿包覆（LaMnO3、Sr 掺杂）提升空气/循环稳定性（p97, p98）；SrTiO3（p100）、N 掺杂 LiAlO2（p101）、Li3.2Zr0.4Si0.6O3.6（p114）、W 氧化物稳定夹层（p169）。

### 2.5 电解液与界面工程

高浓度双盐醚电解液（1.25M LiTFSI+2.5M LiFSI/DME）实现 Li‖NCM83 150 循环 ~95% 保持、CE>99.9%（p32）；0.75M FEC+TMP 不燃电解液缓解 Ni-O 共价（p35）；电化学氟化构建 LiF 界面（p34）；PTFE 隔膜实现 4.7V 稳定（p36）；有机硅添加剂减少产气（p15）；高电压氟化碳酸酯添加剂（p30, p31）。

### 2.6 无钴化趋势

Co 在高电位比 Ni 更具破坏性（p4）；Co-free 单晶 NM88 保持率优于含 Co 的 NCM83（p20）；Co-free 高镍通过 Al/Mg 共掺杂（p90）、W 稳定 rock salt（p123）、浓度梯度（p150）、单晶化（p52, p85）等多途径实现。传统观点认为 Co 稳定结构（p71, p158）——形成 Gap 2。

---

## 3. 关键材料与性质对比（含量化数据）

| 材料/策略 | 测试条件 | 初始容量 | 保持率 | 论文 |
|---|---|---|---|---|
| NCM811（裸） | 500 cyc | — | 19% | p5 |
| LiNbO3 包覆 SC-NCM811 | 500 cyc | — | **70%** | p5 |
| NMC76（裸） | 500 cyc @4.5V | — | 较低 | p41 |
| Al(1%)-NMC76 | 500 cyc @4.5V | — | **79.2%** | p41 |
| Fe/Zr-NM82 | 200 cyc @1C | 207.06 mAh/g@0.1C | **81.55%** | p44 |
| NCM83 + HCBE 电解液 | 150 cyc | — | **~95%** | p32 |
| LNMO + Li3PO4 | 1000 cyc | 109 mAh/g(剩余) | **>90%** | p42 |
| LNMO（无添加剂） | 1000 cyc | — | 78% | p42 |
| NCA80/88/95 | 循环 | 随 Ni ↑ | 随 Ni ↓ | p11 |
| SC NCM (x=0.7-0.9, ~3μm) | 循环 | — | < PC 对应物 | p1 |
| Sn-B 掺杂 NMC90-5-5 | 25/45/-5°C | — | ↑ vs 裸 | p43 |

**趋势总结**：
1. Ni 含量每增加 10 at%（0.6→0.9），初始容量增加 ~15-25 mAh/g，保持率下降（无统一量化公式——Gap 4）
2. 包覆/掺杂普遍将长循环（500-1000 cyc）保持率提升 2-4 倍（如 19%→70%）
3. 电解液工程可在 150 循环内维持 >95% 保持（高浓度盐策略）

---

## 4. 研究空白与未来方向

| # | Gap | 类型 | 严重度 | 关键证据 |
|---|---|---|---|---|
| 1 | 单晶 vs 多晶保持率矛盾（粒径/电压/倍率耦合未解耦） | 矛盾 | 高 | p1,p2 vs p62,p67,p121 |
| 2 | Co 含量×电压的"有害-有益"临界点未定量 | 矛盾 | 高 | p4,p20 vs p71,p158 |
| 3 | 掺杂元素描述符→保持率定量构效关系缺失 | 缺失连接 | 高 | p8-p170 多元素数据无统一模型 |
| 4 | Ni 含量→保持率统一数学关系缺失 | 缺失连接 | 中 | p10,p11,p13,p24 |
| 5 | 单晶粒径→保持率标度关系未探索 | 未探索 | 中 | p1,p84,p146 |
| 6 | 衰减曲线滚降起始点与材料参数关联未建模 | 未探索 | 低 | p75,p11,p5 |

未来方向：① 统一测试协议的 SC/PC 对比矩阵；② 数据驱动的掺杂优化（描述符回归/ML）；③ 全电池视角的协同退化建模（p22, p54）；④ 无钴体系的界面-体相协同设计。

---

## 5. 参考文献（关键论文，可追溯）

| ID | 标题 | DOI |
|---|---|---|
| p1/p2 | Capacity Fading Mechanisms in Ni-Rich Single-Crystal NCM Cathodes | 10.1021/acsenergylett.1c01089 |
| p3 | Fundamental and solutions of microcrack in Ni-rich layered oxide cathode materials | 10.1016/j.nanoen.2021.105854 |
| p4 | Understanding Co roles towards developing Co-free Ni-rich cathodes | 10.1038/s41560-021-00776-y |
| p5 | Insights into Capacity Fading Mechanism and Coating Modification of High-Nickel Cathodes | 10.1021/acsami.2c14235 |
| p10 | Capacity Fading Mechanism of Ni-Rich NCA Cathode | 10.1149/ma2019-02/5/327 |
| p11 | Capacity Fading of Ni-Rich NCA Cathodes: Effect of Microcracking Extent | 10.1021/acsenergylett.9b02302 |
| p20 | Balancing Capacity and Cycling Stability of Ni-Rich Cathode: Trace Cobalt Dopant is Unnecessary in Single-Crystal | 10.1002/adfm.202518045 |
| p22 | Synergistic Degradation Mechanism in Single Crystal Ni-Rich NMC//Graphite Cells | 10.1021/acsenergylett.3c01596 |
| p28 | Insight into Performance Degradation of Ni-Rich Layered Cathode Materials | 10.1149/ma2019-02/5/336 |
| p32 | High-Concentrated Binary-Salt Ether Electrolytes for High-Voltage Li Metal Batteries with Ni-Rich Cathode | 10.1021/acsami.4c06491 |
| p41 | Optimized Al Doping Improves Both Interphase Stability and Bulk Structural Integrity of Ni-Rich NMC | 10.1021/acsaem.9b02372 |
| p42 | Cycling stability of Li-ion batteries based on Fe-Ti-doped LiNi0.5Mn1.5O4 and Li3PO4 | 10.18725/oparu-52117 |
| p43 | Improved Cycle Life and Li-Ion Transport at Low Temperature in Doped Ni-Rich NMC | 10.26434/chemrxiv-2025-940p9-v2 |
| p44 | Reconstruction of magnetic exchange networks for high-performance Co-free Ni-rich cathodes | 10.26599/emd.2026.9370094 |
| p49 | Rational design of mechanically robust Ni-rich cathode materials via concentration gradient strategy | 10.1038/s41467-021-26290-z |
| p52 | Crack-free single-crystalline Co-free Ni-rich LiNi0.95Mn0.05O2 | 10.1016/j.esci.2022.02.006 |
| p56 | The Origin of High-Voltage Stability in Single-Crystal Layered Ni-Rich Cathode Materials | 10.1002/anie.202207225 |
| p62 | Spontaneous Strain Buffer Enables Superior Cycling Stability in Single-Crystal NCM | 10.1021/acs.nanolett.1c03613 |
| p67 | Single-Crystalline Ni-Rich layered cathodes with Super-Stable cycling | (见 papers.json) |
| p75 | Unraveling the nonlinear capacity fading mechanisms of Ni-rich layered oxide cathode | (见 papers.json) |
| p83 | Layer-by-layer delithiation during lattice collapse as the origin of planar gliding and microcracking | (见 papers.json) |
| p103 | Oxygen Vacancies Driven by Co in the Deeply Charged State Inducing Intragranular Cracking | (见 papers.json) |
| p129 | Co-free Ni-rich layered cathode with long-term cycling stability | (见 papers.json) |
| p146 | Submicron single-crystal structure for enhanced structural stability of LiNi0.8Mn0.2O2 | (见 papers.json) |
| p150 | Robust Concentration Gradient Co-Free Ni-Rich Cathodes Enable Long-Life Operations | (见 papers.json) |

> 完整 174 篇的 DOI 映射见 workspace/data/literature_cache/papers.json
