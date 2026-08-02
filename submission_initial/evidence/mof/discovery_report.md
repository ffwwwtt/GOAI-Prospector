# Structure-Property Relationship Discovery

**Generated:** 2026-08-02 14:05
**Total candidates explored:** 328
**Validated:** 0 | **Refuted:** 0
**Literature supported:** 8 | **Inconclusive:** 0 | **Pending:** 0
**Materials Project hits:** 0

## Search Summary

Explored 8 hypotheses via Bayesian optimization and MCTS; literature-supported 8. Model comparison available (hyp[5], n=37).

---

## Discovered Structure-Property Relationships

### 1. 📚 缺陷类型决定CO2容量效应方向：占位型（甲酸盐）抑制 vs 造孔型（配体缺失）提升

**Confidence:** 0.98 | **Novelty:** 0.90 | **LLM Plausibility:** 1.00

**Description:** 在同一MOF-74骨架上分别引入两类缺陷：(a) DMF分解产生的甲酸盐缺陷（占据/屏蔽OMS）；(b) 配体缺失缺陷（Cl-竞争/调制剂，制造介孔）。假设缺陷效应方向由缺陷化学角色决定而非浓度：甲酸盐缺陷使容量随浓度定量下降（p121），配体缺失缺陷使容量与Qst提升（p122，饱和容量+50%、Qst 36→46 kJ/mol）。存在缺陷浓度-容量非单调关系的分岔点。

**Expected Relationship:** 缺陷类型（占位vs造孔）是容量效应方向的开关；同类型缺陷浓度-容量关系单调，跨类型则方向相反

**Materials:** MOF-74(Mg/Ni/Co), 甲酸缺陷MOF-74, 配体缺失缺陷MOF-74
**Property:** CO2吸附容量与Qst（1 bar）

**Source Gap:** Gap 7
**Search Method:** bayesian (30 iterations, 41 candidates)

**Evidence Chain:**
  - p121
  - p122
  - p17

**Scientific Explanation (LLM):**
> 占位型缺陷（如甲酸盐占据配位不饱和金属位点）直接减少了CO₂的主要吸附位点，同时可能通过空间位阻或改变局部电场削弱吸附强度，因此容量下降；而配体缺失型缺陷本质上是一种造孔行为，可暴露更多开放金属位点或形成微孔环境，有利于CO₂的富集和吸附热提升。这一“缺陷类型决定容量方向”的构效关系已部分隐含于MOF缺陷工程的相关研究中，但将其明确归纳为占位与造孔的“开关效应”并区分同类型单调、跨类型反向的规律，属于对现有知识的系统化新知。该关系的失效边界可能出现在缺陷浓度过高导致结构崩塌、缺陷间协同或竞争效应掩盖单一类型贡献，以及CO₂吸附由孔道填充主导而不再依赖开放金属位点的压力或温度区间。

**External Validation:**
  - overall_match: True
  - validation_source: literature
  - validation_notes: ["文献证据链：37 篇独立论文（['p1', 'p104', 'p108', 'p115', 'p12', 'p121', 'p122', 'p130', 'p132', 'p135', 'p136', 'p143', 'p158', 'p159', 'p164', 'p168', 'p17', 'p24', 'p25', 'p28', 'p29', 'p30', 'p31', 'p32', '
  - databases_checked: []
  - supporting_evidence: ["papers: ['p1', 'p104', 'p108', 'p115', 'p12', 'p121', 'p122', 'p130', 'p132', 'p135', 'p136', 'p143', 'p158', 'p159', 'p164', 'p168', 'p17', 'p24', 'p25', 'p28', 'p29', 'p30', 'p31', 'p32', 'p33', '
  - details: {}

---

### 2. 📚 Ni/Co-MOF-74双金属比例-容量非对称协同机制

**Confidence:** 0.97 | **Novelty:** 0.88 | **LLM Plausibility:** 1.00

**Description:** 制备Ni:Co比例为10:0、9:1、6:1、1:1、1:6、1:9、0:10的MOF-74系列。假设容量不是Co含量的单调函数，而在Ni1Co1处出现极大值（8.30 mmol/g），因为Ni和Co在DOBDC链上形成异金属Ni-O-Co交替排列产生更强CO2结合位点。

**Expected Relationship:** 容量序列为Ni1Co1>Ni1Co6>Co>Ni>Ni6Co1；容量与异金属Ni-O-Co对密度正相关

**Materials:** Ni_xCo_y-MOF-74
**Property:** CO2吸附容量（0 °C, 1 bar）

**Source Gap:** Gap 2
**Search Method:** bayesian (30 iterations, 41 candidates)

**Evidence Chain:**
  - p29
  - p7
  - p17

**Scientific Explanation (LLM):**
> Ni/Co-MOF-74中异金属Ni-O-Co对的存在会在氧簇节点引入不对称的电子分布，使相邻金属位点的Lewis酸性及局部静电场发生差异化的调变，从而增强材料对CO₂的吸附亲和力；因此异金属对密度越高，单位质量内这类协同位点越多，容量越接近最优比例，这解释了Ni1Co1容量最高的非单调趋势。该“双金属协同增强吸附”的机制与文献中关于MOF-74系列混合金属节点可改善气体吸附性能的报道方向一致，但本假设进一步指出容量并非随某一金属比例线性变化，而是与异金属对密度呈正相关，属于对已有“协同效应”认识的细化与补充。该关系的失效边界可能出现在极端Ni/Co比例或合成条件不足以形成均匀混合节点的情况：此时体系趋向于富Ni区和富Co区的物理混合，异金属对密度低或实际形成的是分离相，上述协同机制不再主导，容量序列将偏离预期。同时，若CO₂吸附由孔径筛分、比表面差异等物理因素主导（如微孔结构发生显著改变），异金属对密度与容量的相关性也会被掩盖，假设适用性受限。

**External Validation:**
  - overall_match: True
  - validation_source: literature
  - validation_notes: ["文献证据链：37 篇独立论文（['p1', 'p104', 'p108', 'p115', 'p12', 'p121', 'p122', 'p130', 'p132', 'p135', 'p136', 'p143', 'p158', 'p159', 'p164', 'p168', 'p17', 'p24', 'p25', 'p28', 'p29', 'p30', 'p31', 'p32', '
  - databases_checked: []
  - supporting_evidence: ["papers: ['p1', 'p104', 'p108', 'p115', 'p12', 'p121', 'p122', 'p130', 'p132', 'p135', 'p136', 'p143', 'p158', 'p159', 'p164', 'p168', 'p17', 'p24', 'p25', 'p28', 'p29', 'p30', 'p31', 'p32', 'p33', '
  - details: {}

---

### 3. 📚 水效应二象性临界线：吸附机制（物理vs化学）决定水对CO2捕获的符号

**Confidence:** 0.85 | **Novelty:** 0.88 | **LLM Plausibility:** 0.95

**Description:** 系统收集物理吸附MOF（Mg-MOF-74、ELM-11、ZIF）与化学吸附MOF（胺化体系：HP-PMOF-DETA、PEI@MIL-100、MOF-808-AA、mmen-Mg2(dobpdc)、TYUT-ATZ-β）的干/湿态容量数据。假设存在以胺负载量或Qst为横轴的符号翻转临界线：低Qst/低胺负载（物理主导）→水负效应；高胺负载（化学主导）→水正效应（碳酸氢盐路径、胺可及性提升、水固定位点）；中间过渡区存在最优RH。

**Expected Relationship:** 水效应符号由吸附机制决定：物理吸附负、化学吸附正；存在Qst或胺负载临界值

**Materials:** Mg-MOF-74, ELM-11, HP-PMOF-DETA, PEI@MIL-100(Cr), MOF-808-AA, mmen-Mg2(dobpdc), TYUT-ATZ-β
**Property:** 湿态/干态CO2容量比（RH 0-90%）

**Source Gap:** Gap 8
**Search Method:** bayesian (30 iterations, 41 candidates)

**Evidence Chain:**
  - p30
  - p49
  - p152
  - p132
  - p135
  - p136
  - p158
  - p164
  - p168

**Scientific Explanation (LLM):**
> 该构效关系的核心机制在于水分子的竞争吸附与促进胺基甲酸铵形成的双重角色：对依赖范德华力或孔道填充的物理吸附体系，水会优先占据活性位点并堵塞孔道，从而削弱CO₂吸附容量；而对含胺基等化学吸附位点的材料，水分子可作为质子转移媒介降低氨基甲酸铵生成能垒，甚至促进碳酸氢盐/氨基甲酸根物种的稳定，因而表现为正效应。这实际上将已知的“水对胺基吸附剂有促进、对纯物理MOF有抑制”的碎片化观察统一为以吸附机制为判据的“符号转折”框架，属于对已有文献规律的概念性整合而非全新发现。该关系的失效边界可能出现在水含量极端情形下——当湿度接近饱和时，即使化学吸附体系中的水也会因毛细凝聚堵塞孔道或引发胺基溶胀流失而转为负效应；此外，若物理吸附位点本身对水亲和力极低（如疏水孔壁），水的负效应可能不明显，或当化学吸附强度过高（Qst极大）时，水无法介入反应，正效应也可能消失。

**External Validation:**
  - overall_match: True
  - validation_source: literature
  - validation_notes: ["文献证据链：61 篇独立论文（['p1', 'p104', 'p108', 'p115', 'p12', 'p121', 'p122', 'p128', 'p130', 'p131', 'p132', 'p135', 'p136', 'p137', 'p14', 'p143', 'p144', 'p145', 'p148', 'p152', 'p154', 'p155', 'p156', 'p
  - databases_checked: []
  - supporting_evidence: ["papers: ['p1', 'p104', 'p108', 'p115', 'p12', 'p121', 'p122', 'p128', 'p130', 'p131', 'p132', 'p135', 'p136', 'p137', 'p14', 'p143', 'p144', 'p145', 'p148', 'p152', 'p154', 'p155', 'p156', 'p158', '
  - details: {}

---

### 4. 📚 胺功能化MOF最佳负载量与孔道结构预测关系

**Confidence:** 0.99 | **Novelty:** 0.75 | **LLM Plausibility:** 1.00

**Description:** 在MIL-101、MOF-177、MOF-808、HP-PMOF等不同孔径/孔容MOF中负载PEI/TEPA/DETA/EDA，系统改变胺负载量（0-100 wt%）。假设最佳胺负载量随初始孔容和孔径增大而线性升高，随胺链长/分子体积增加而下降；胺效率随负载量呈衰减曲线。

**Expected Relationship:** 最佳胺负载量与MOF孔容/孔径正相关，与胺分子体积负相关；超过最佳值后容量下降

**Materials:** PEI@MIL-101(Cr), TEPA@MOF-177, TEPA@MOF-808, HP-PMOF-DETA
**Property:** 低压CO2容量（0.15 bar/400 ppm）及胺效率

**Source Gap:** Gap 3
**Search Method:** bayesian (30 iterations, 41 candidates)

**Evidence Chain:**
  - p38
  - p40
  - p41
  - p1
  - p135
  - p136

**Scientific Explanation (LLM):**
> 该构效关系在机制上可能成立，因为胺分子负载于MOF孔道内时，需以分散状态暴露活性位点；孔容/孔径越大，可容纳的胺分子总量越高，而胺分子体积越大则越易堵塞孔道或阻碍CO2扩散，因此最佳负载量随孔容/孔径增大而提高、随胺体积增大而降低。超过最佳负载量后，过量胺会填充或阻塞孔道，导致CO2传质受阻且胺基无法有效接触CO2，胺效率与容量同步下降。这一认识与文献中“胺负载量存在最优窗口”的普遍结论一致，但将最佳负载量同MOF孔容/孔径及胺分子体积建立定量关联属于对既有构效关系的新提炼。该关系的失效边界可能出现在胺与骨架发生共价反应、胺在孔内聚集形成非晶态团簇而非均匀分散，或低压测试条件下动力学扩散控制占主导时，此时孔道结构参数不再是唯一决定因素。

**External Validation:**
  - overall_match: True
  - validation_source: literature
  - validation_notes: ["文献证据链：32 篇独立论文（['p1', 'p104', 'p121', 'p122', 'p128', 'p130', 'p131', 'p132', 'p135', 'p136', 'p137', 'p14', 'p143', 'p145', 'p158', 'p164', 'p167', 'p168', 'p17', 'p170', 'p171', 'p172', 'p173', 'p
  - databases_checked: []
  - supporting_evidence: ["papers: ['p1', 'p104', 'p121', 'p122', 'p128', 'p130', 'p131', 'p132', 'p135', 'p136', 'p137', 'p14', 'p143', 'p145', 'p158', 'p164', 'p167', 'p168', 'p17', 'p170', 'p171', 'p172', 'p173', 'p176', '
  - details: {}

---

### 5. 📚 MOF-74(Ni)合成条件-微观结构-CO2容量火山形关系

**Confidence:** 0.97 | **Novelty:** 0.75 | **LLM Plausibility:** 1.00

**Description:** 通过冷凝回流与溶剂热两种路线合成MOF-74(Ni)，系统改变合成温度（120-160°C）与时长（6-48 h），定量改变产物中OMS密度、结晶度和缺陷浓度。假设CO2容量与可接触OMS密度及结晶度正相关，但存在最优合成窗口（约140°C、24-48h）。

**Expected Relationship:** CO2容量随合成温度/时间呈火山形关系；最优窗口对应最大可接触OMS密度和适中缺陷浓度

**Materials:** MOF-74(Ni), Ni-DOBDC
**Property:** CO2吸附容量（1 bar, 273 K/298 K）

**Source Gap:** Gap 1
**Search Method:** bayesian (30 iterations, 41 candidates)

**Evidence Chain:**
  - p17
  - p7
  - p1

**Scientific Explanation (LLM):**
> 该构效关系可能成立的核心机制在于，MOF-74(Ni)的合成温度与时间决定了晶体成核-生长动力学与缺陷引入速率的竞争：过低温度或过短时间导致结晶不完全、可接触开放金属位点（OMS）密度不足，而过高温或过长时间则可能引发骨架部分塌陷或过度缺陷化，阻塞孔道并降低有效OMS数量，因此CO₂容量随合成条件呈现先升后降的火山形趋势，且最优窗口对应“OMS充分暴露—缺陷浓度适中”的微观结构平衡。这与已有文献中关于MOF-74系列“配位不饱和Ni位点是CO₂主要吸附位点”以及“适度缺陷可增加吸附能但过量缺陷会破坏骨架稳定性”的结论一致，属于已知机制在该材料体系中的具体化表达。该关系的失效边界可能出现在合成条件改变孔道尺寸分布或引入不可逆结构相变的区域，例如极端溶剂热条件下发生配体重排或金属簇聚集，使缺陷浓度与OMS密度不再呈单调关联，或当CO₂吸附由微孔填充主导而表面缺陷贡献可忽略时，火山形关系将不再适用。

**External Validation:**
  - overall_match: True
  - validation_source: literature
  - validation_notes: ["文献证据链：37 篇独立论文（['p1', 'p104', 'p108', 'p115', 'p12', 'p121', 'p122', 'p130', 'p132', 'p135', 'p136', 'p143', 'p158', 'p159', 'p164', 'p168', 'p17', 'p24', 'p25', 'p28', 'p29', 'p30', 'p31', 'p32', '
  - databases_checked: []
  - supporting_evidence: ["papers: ['p1', 'p104', 'p108', 'p115', 'p12', 'p121', 'p122', 'p130', 'p132', 'p135', 'p136', 'p143', 'p158', 'p159', 'p164', 'p168', 'p17', 'p24', 'p25', 'p28', 'p29', 'p30', 'p31', 'p32', 'p33', '
  - details: {}

---

### 6. 📚 孔径-压力窗口统一描述：从超微孔DAC到中孔高压捕获

**Confidence:** 0.82 | **Novelty:** 0.85 | **LLM Plausibility:** 0.92

**Description:** 利用CRAFTED数据库（726 MOF的GCMC等温线）及实验数据（ZU-16-Co、SIFSIX-3-Ni、MOF-74(Ni)、agw型）构建孔径-压力-CO2容量三维曲面。假设每个目标压力下CO2容量随孔径呈单峰分布，最优孔径d*随压力降低而减小：0.01 bar→3.5-4.0 Å，0.15 bar→4-6 Å，1 bar→6-10 Å。

**Expected Relationship:** 最优孔径d*与log10(P)负相关；超微孔在低压下因高Qst占优，中孔在中高压下优势显现

**Materials:** ZU-16-Co, SIFSIX-3-Ni, MOF-74(Ni), CRAFTED/CoRE MOF数据库材料集
**Property:** CO2吸附容量（0.01/0.15/1 bar分压下的最优孔径d*）

**Source Gap:** Gap 5
**Search Method:** bayesian (30 iterations, 41 candidates)

**Evidence Chain:**
  - p78
  - p82
  - p17
  - p10
  - p151
  - p123

**Scientific Explanation (LLM):**
> 该构效关系在机制上可归因于气体吸附的热力学与孔道限域效应的协同：超微孔（<1 nm）在低分压下提供更强的孔壁势场叠加，导致CO₂吸附焓（Qst）显著升高，从而在低压区占据优势；而随着压力升高，孔内吸附势垒逐渐被克服，中孔（2–50 nm）因具有更大的孔容和更快的传质动力学，其单位体积吸附量优势在中高压区得以显现，因此最优孔径随压力升高向更大尺寸移动，表现为d*与log10(P)负相关。这一趋势与已有文献中关于“低压下超微孔决定CO₂捕获性能、高压下中孔贡献总容量”的共识一致，属于已知规律的统一表述，而非全新机制；但其新颖之处在于用“孔径-压力窗口”将离散材料（如超微孔SIFSIX-3-Ni与中孔MOF-74(Ni)）纳入同一标度框架。该关系的失效边界可能出现在以下情形：当材料存在开放金属位点或极性官能团时，化学特异性吸附会打破纯几何孔径依赖；或当孔道发生柔性响应（如呼吸效应）时，有效孔径随压力变化，静态d*不再适用；此外，在极高压力下所有孔径的吸附趋于饱和，最优孔径差异将消失。

**External Validation:**
  - overall_match: True
  - validation_source: literature
  - validation_notes: ["文献证据链：53 篇独立论文（['p1', 'p10', 'p104', 'p108', 'p115', 'p116', 'p117', 'p12', 'p121', 'p122', 'p125', 'p130', 'p132', 'p135', 'p136', 'p143', 'p144', 'p148', 'p154', 'p155', 'p156', 'p158', 'p159', 'p
  - databases_checked: []
  - supporting_evidence: ["papers: ['p1', 'p10', 'p104', 'p108', 'p115', 'p116', 'p117', 'p12', 'p121', 'p122', 'p125', 'p130', 'p132', 'p135', 'p136', 'p143', 'p144', 'p148', 'p154', 'p155', 'p156', 'p158', 'p159', 'p164', '
  - details: {}

---

### 7. 📚 开放金属位点密度与湿度耐受性的权衡曲线

**Confidence:** 0.83 | **Novelty:** 0.82 | **LLM Plausibility:** 0.93

**Description:** 选择OMS密度不同的同构MOF-74系列（Mg/Ni/Co）以及无OMS的ZIF-94、有化学位点的en-CPM-200、水固定型TYUT-ATZ-β，在0-90% RH模拟烟气下测CO2容量保持率。假设OMS密度越高干态容量越高但湿态保持率越低；最优OMS密度位于中等Qst（约30-40 kJ/mol）区间。

**Expected Relationship:** OMS密度与湿态容量保持率近似线性负相关；存在最优OMS密度使湿态工作容量最大化

**Materials:** Mg-MOF-74, Ni-MOF-74, Co-MOF-74, ZIF-94, en-CPM-200, TYUT-ATZ-β
**Property:** 湿态CO2容量保持率（RH 0-90%）

**Source Gap:** Gap 4
**Search Method:** bayesian (30 iterations, 41 candidates)

**Evidence Chain:**
  - p30
  - p49
  - p115
  - p104
  - p164

**Scientific Explanation (LLM):**
> 开放金属位点（OMS）密度越高，越有利于提供强吸附位点以提升干态CO₂容量，但在高湿条件下水分子会优先占据OMS并通过氢键网络阻隔CO₂接近，导致湿态容量保持率随OMS密度增加而近似线性下降，因此二者形成权衡关系；同时存在一个最优OMS密度，使湿态下的有效工作容量（而非单纯保持率）达到最大。这一关系与文献中关于“OMS亲水性增强会加剧水竞争吸附”的普遍认识一致，属于已知机制的定量化延伸，而非全新发现。其失效边界可能出现在湿度极低（水竞争可忽略）或OMS被化学修饰/配体屏蔽而不再直接参与吸附的情形，此时保持率与OMS密度的线性负相关将不再成立。

**External Validation:**
  - overall_match: True
  - validation_source: literature
  - validation_notes: ["文献证据链：55 篇独立论文（['p1', 'p104', 'p108', 'p115', 'p12', 'p121', 'p122', 'p130', 'p132', 'p135', 'p136', 'p137', 'p143', 'p144', 'p145', 'p148', 'p152', 'p154', 'p155', 'p156', 'p158', 'p159', 'p160', '
  - databases_checked: []
  - supporting_evidence: ["papers: ['p1', 'p104', 'p108', 'p115', 'p12', 'p121', 'p122', 'p130', 'p132', 'p135', 'p136', 'p137', 'p143', 'p144', 'p145', 'p148', 'p152', 'p154', 'p155', 'p156', 'p158', 'p159', 'p160', 'p161', 
  - details: {}

---

### 8. 📚 等温线形状决定循环级性能：阶梯等温线MOF的TSA/VSA工作容量与再生能耗优势

**Confidence:** 0.75 | **Novelty:** 0.90 | **LLM Plausibility:** 0.85

**Description:** 对比阶梯等温线MOF（F4_MIL-140A(Ce)、mmen-Mg2(dobpdc)、二胺接枝体系）与常规Langmuir型MOF（MOF-177、HKUST-1、UiO-66、13X）的循环级性能。假设TSA/VSA工作容量（Δ载量）与等温线阶梯陡度正相关、与再生温度摆幅负相关；MOF-177类弱吸附体在TSA中无正工作容量（p137），而相变MOF在PVSA中恢复率/纯度最优（p154）。

**Expected Relationship:** 阶梯等温线MOF的工作容量和能耗表现系统优于Langmuir型；工作容量与阶梯压力/陡度强相关

**Materials:** F4_MIL-140A(Ce), mmen-Mg2(dobpdc), MOF-177, HKUST-1, 13X, CALF-20
**Property:** TSA/VSA循环工作容量（Δ载量）与寄生能耗

**Source Gap:** Gap 9
**Search Method:** bayesian (30 iterations, 41 candidates)

**Evidence Chain:**
  - p137
  - p145
  - p154
  - p128
  - p176

**Scientific Explanation (LLM):**
> 阶梯等温线因在狭窄压力区间内发生吸附量的突增，使循环操作可在较小的压力摆幅或温度摆幅下获得较高的Δ载量，同时避免了Langmuir型等温线在低压段“拖尾”所导致的不可逆吸附残留，因此寄生能耗更低；这一关系与文献中关于“工作容量取决于等温线形状而非比表面积”的共识一致，属于已知规律的实例化，而非新机制。其失效边界在于：若阶梯压力远离实际循环的吸附/脱附压力窗口，或阶梯过于陡峭导致传质动力学受限、再生需更高温度或更长吹扫时间，则工作容量与能耗优势可能被抵消；此外，当循环条件进入阶梯平台区之外时，阶梯型材料的性能会退化为普通Langmuir型甚至更差。

**External Validation:**
  - overall_match: True
  - validation_source: literature
  - validation_notes: ["文献证据链：64 篇独立论文（['p1', 'p10', 'p104', 'p106', 'p108', 'p115', 'p12', 'p121', 'p122', 'p125', 'p128', 'p130', 'p131', 'p132', 'p135', 'p136', 'p137', 'p14', 'p143', 'p144', 'p145', 'p148', 'p152', 'p1
  - databases_checked: []
  - supporting_evidence: ["papers: ['p1', 'p10', 'p104', 'p106', 'p108', 'p115', 'p12', 'p121', 'p122', 'p125', 'p128', 'p130', 'p131', 'p132', 'p135', 'p136', 'p137', 'p14', 'p143', 'p144', 'p145', 'p148', 'p152', 'p154', 'p
  - details: {}

---
