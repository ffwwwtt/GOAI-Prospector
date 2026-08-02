# 文献调研报告：halide perovskite solar cells band gap stability

## 1. 执行摘要

卤化物钙钛矿太阳能电池（PSC）的核心优势之一是其带隙可通过组分连续调谐（约 1.2–2.4 eV），实现单结/叠层最优光谱匹配。然而**带隙稳定性**构成产业化关键瓶颈：带隙的可调性源于离子晶格的组分自由度，而这恰恰是带隙漂移（光致卤化物分离、相变、分解）的热力学根源。本调研基于 96 篇论文（sciverse 80 / arxiv 16，2016–2024）系统梳理了带隙稳定性的三大机制、关键定量关系与研究空白。

**核心发现**：
1. 光致卤化物分离（Hoke 效应）是混合卤化物带隙不稳定的主机制，存在激发强度阈值（0.03–0.2 mW/cm²）[p26]
2. CsPbI₃ 的 α→δ 相变导致带隙从 ~1.73 eV 跳变至 ~2.82 eV，纳米晶尺寸 <5.6 nm 可实现热力学稳定 [p55]
3. A 位 Cs 替代比 X 位 Br 替代更有利于"带隙-稳定性"权衡 [p53]，但与混合焓数据存在表面矛盾 [p26]
4. 带隙漂移的**定量动力学规律**（速率 vs 组分/激发/温度）是最大空白

## 2. 文献综述

### 2.1 光致卤化物分离与带隙红移
Hoke 等首次报道 MAPb(I₁₋ₓBrₓ)₃ 光照下 PL 红移 [p26]。p26 提出带隙热力学模型：光生载流子在富 I 畴区累积，其带隙梯度提供分离驱动力（ΔF_light 可达 ~1–100 eV 量级，远超混合焓 ~10 meV 与熵 ~−20 meV）。模型预测 x_terminal 随激发强度增大而减小（CsPb(I₀.₅Br₀.₅)₃ 薄膜：0.46→0.05 @ 0.2–1000 mW/cm²），并存在阈值强度。Cl⁻ 掺杂 [p28]、2D 间隔阳离子 [p31, p36]、表面处理 [p7]、后热退火 [p41] 均可抑制分离。

### 2.2 CsPbI₃ 相稳定性
α 相（黑色，~1.73 eV）室温亚稳，转 δ 相（黄色，~2.82 eV）。稳定化路线：纳米晶尺寸效应 [p55]（<5.6 nm 稳定 α/γ 相）、两性离子 [p50]、结晶动力学 [p51]、Bi³⁺+Cl⁻ 共掺杂 [p65]、PEO [p64]、界面网络 [p58]、PbI₃⁻ 络合物 [p60]、Mn 合金化 [p46]。

### 2.3 组分工程（宽带隙/叠层）
p53 在 CsₓFA₁₋ₓPb(Br_yI₁₋y)₃ 空间中证明：**用 Cs 提高带隙优于用 Br**——1.68 eV（17.4%）与 1.75 eV（16.3%）器件光稳定性显著优于高 Br 组分。这与 p26 中 CsPb 体系混合焓更高（45 vs 39 meV/卤原子）的表观矛盾构成 Gap 3。

### 2.4 FAPbI₃ 与热稳定性
FAPbI₃ α 相带隙 ~1.48–1.52 eV 最优但热/相稳定差 [p73, p77]；混合阳离子分解动力学 [p80]；有机-无机稳定性对比 [p49]。

### 2.5 窄带隙与无铅体系
Pb-Sn 低带隙（~1.2–1.3 eV）稳定性 [p87, p95]；Sn 基可逆带隙窄化 [p56]；双钙钛矿带隙工程 [p3, p19, p76, p94]。

## 3. 关键材料与性质对比

| 体系 | 带隙范围 (eV) | 稳定性机制 | 关键数据 | 来源 |
|---|---|---|---|---|
| MAPb(I₁₋ₓBrₓ)₃ | 1.58–2.33 | 光致分离（阈值 0.03–0.1 mW/cm²） | b=0.095–1.042 | [p26] |
| CsPb(I₁₋ₓBrₓ)₃ | 1.79–2.37 | 光致分离（阈值 ~0.2 mW/cm²） | U=45 meV/卤原子 | [p26] |
| CsPbI₃ | 1.73（α）/2.82（δ） | α→δ 相变 | NC<5.6nm 稳定 α | [p55] |
| FAPbI₃ | ~1.48–1.52 | 热分解 | — | [p73, p77] |
| CsₓFA₁₋ₓPb(Br,I)₃ | 1.68/1.75 | Cs 替代提升光稳定 | 效率 17.4/16.3% | [p53] |
| Pb-Sn 混合 | ~1.2–1.3 | 氧化降解 | — | [p87, p95] |

## 4. 研究空白与未来方向

（详见 gap_report.md，Top 3：）
1. **Gap 3**：A 位 Cs vs X 位 Br 的带隙-稳定性权衡矛盾（p53 vs p26）——高优先级
2. **Gap 1**：带隙漂移动力学定量规律缺失——模型就绪可检验
3. **Gap 2**：稳定化策略的带隙偏移缺乏系统量化

## 5. 参考文献（关键论文，DOI 可追溯）

1. Ruth A. et al., "A thermodynamic band gap model for photoinduced phase segregation in mixed-halide perovskites", J. Phys. Chem. C, DOI: 10.1021/acs.jpcc.3c04708 [p26]
2. "Understanding size dependence of phase stability and band gap in CsPbI3 perovskite nanocrystals", J. Appl. Phys., DOI: 10.1063/1.5128016 [p55]
3. "Compositional Engineering for Efficient Wide Band Gap Perovskites with Improved Stability to Photoinduced Phase Segregation", ACS Energy Lett., DOI: 10.1021/acsenergylett.7b01255 [p53]
4. "How Chloride Suppresses Photoinduced Phase Segregation in Mixed Halide Perovskites", Chem. Mater., DOI: 10.1021/acs.chemmater.0c02100 [p28]
5. "Spacer Cations Dictate Photoinduced Phase Segregation in 2D Mixed Halide Perovskites", ACS Energy Lett., DOI: 10.1021/acsenergylett.1c01015 [p31]
6. "Ba-induced phase segregation and band gap reduction in mixed-halide inorganic perovskite solar cells", Nat. Commun., DOI: 10.1038/s41467-019-12678-5 [p35]
7. "Stabilizing the alpha-Phase of CsPbI3 Perovskite by Sulfobetaine Zwitterions", DOI: 10.17615/ns5v-vf17 [p50]
8. "Enhanced Phase Stability and Reduced Bandgap for CsPbI3 Perovskite through Bi3+ and Cl– Co-Doping", Russ. J. Phys. Chem., DOI: 10.1134/s0036024424701279 [p65]
9. "Thermal stability and decomposition kinetics of mixed-cation halide perovskites", Phys. Chem. Chem. Phys., DOI: 10.1039/d3cp03704e [p80]
10. "Reversible Band Gap Narrowing of Sn-Based Hybrid Perovskite Single Crystal", Angew. Chem., DOI: 10.1002/anie.201810481 [p56]
