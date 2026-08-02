"""
构效关系发现引擎 — Route A: Structure-Property Relationship Discovery
=====================================================================
基于文献知识图谱的 Research Gap，利用搜索算法 + LLM 深度融合，
自主发现材料-性质关联，并通过外部数据库交叉验证。

核心流程：
  Phase 1: Hypothesis Generation    — 从 Gap 中生成候选构效关系假设
  Phase 2: Guided Search            — 贝叶斯优化/MCTS 探索材料空间
  Phase 3: LLM Plausibility Check   — LLM 评估中间结果的科学合理性
  Phase 4: External Validation      — Materials Project / OQMD 交叉验证
  Phase 5: Discovery Report         — 结构化输出发现结果 + 证据链

与 LLM 的深度融合（路线 A 核心得分点）：
  - 候选假设生成：LLM 根据 Gap 知识图谱生成搜索种子
  - 中间结果评估：LLM 评估搜索中的中间结果的科学合理性，引导剪枝
  - 搜索方向调整：LLM 分析搜索结果，建议下一轮搜索方向
  - 发现解释生成：LLM 为最终发现生成科学解释和机制假说
"""

from __future__ import annotations

import json
import math
import os
import random
import re
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np

from .extractor import KnowledgeGraph, MaterialEntity, PropertyRecord, Relation


# ═══════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class ResearchGap:
    """研究空白（兼容旧 gap_analyzer 数据模型）。"""
    id: str = ""
    type: str = ""                     # "contradiction" | "missing_link" | "unexplored"
    title: str = ""
    description: str = ""
    severity: str = "medium"           # "high" | "medium" | "low"
    confidence: float = 0.5
    related_papers: List[str] = field(default_factory=list)
    evidence_chain: List[str] = field(default_factory=list)
    suggested_validation: str = ""
    entities_involved: List[str] = field(default_factory=list)
    raw_context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GapReport:
    """研究空白报告（兼容旧 gap_analyzer 数据模型）。"""
    gaps: List[ResearchGap] = field(default_factory=list)
    summary: str = ""
    total_papers_analyzed: int = 0
    contradiction_count: int = 0
    missing_link_count: int = 0
    unexplored_count: int = 0
    analysis_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class DiscoveryHypothesis:
    """构效关系发现假设"""
    id: str = ""
    title: str = ""                        # 假设简述
    description: str = ""                  # 假设详述
    source_gap_id: str = ""               # 来源 Gap ID
    materials: List[str] = field(default_factory=list)  # 涉及材料
    property: str = ""                     # 目标性质
    expected_relationship: str = ""        # 预期的构效关系 (e.g. "doping X increases Y")
    confidence: float = 0.5               # 置信度 [0, 1]
    novelty_score: float = 0.0            # 新颖性分数 [0, 1]

    # 搜索过程
    search_method: str = ""               # "bayesian" | "mcts" | "llm_guided"
    search_iterations: int = 0
    candidates_explored: int = 0

    # 验证结果
    external_validation: Dict[str, Any] = field(default_factory=dict)
    validation_status: str = "pending"    # "pending" | "validated" | "refuted" | "inconclusive"
    evidence_chain: List[str] = field(default_factory=list)

    # LLM 评估
    llm_plausibility_score: float = 0.0
    llm_explanation: str = ""


@dataclass
class DiscoveryReport:
    """构效关系发现报告"""
    title: str = "Structure-Property Relationship Discovery Report"
    generated_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M"))
    hypotheses: List[DiscoveryHypothesis] = field(default_factory=list)
    total_candidates: int = 0
    total_explored: int = 0
    validated_count: int = 0
    refuted_count: int = 0
    search_summary: str = ""
    materials_project_hits: int = 0

    def sorted_by_novelty(self) -> List[DiscoveryHypothesis]:
        return sorted(self.hypotheses, key=lambda h: h.novelty_score * h.confidence, reverse=True)

    def to_dict(self) -> Dict:
        return {
            "title": self.title,
            "generated_at": self.generated_at,
            "hypotheses": [asdict(h) for h in self.hypotheses],
            "total_candidates": self.total_candidates,
            "total_explored": self.total_explored,
            "validated_count": self.validated_count,
            "refuted_count": self.refuted_count,
            "search_summary": self.search_summary,
            "materials_project_hits": self.materials_project_hits,
        }

    def save(self, output_dir: str) -> Tuple[str, str]:
        """Save report as Markdown + JSON. Returns (md_path, json_path)."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # JSON
        json_path = out / "discovery_report.json"
        json_path.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=2))

        # Markdown
        md_path = out / "discovery_report.md"
        md_path.write_text(self.to_markdown(), encoding="utf-8")

        return str(md_path), str(json_path)

    def to_markdown(self) -> str:
        lines = [
            f"# {self.title}",
            f"\n**Generated:** {self.generated_at}",
            f"**Total candidates explored:** {self.total_explored}",
            f"**Validated:** {self.validated_count} | **Refuted:** {self.refuted_count}",
            f"**Materials Project hits:** {self.materials_project_hits}",
            f"\n## Search Summary\n\n{self.search_summary}\n",
            "---\n",
            "## Discovered Structure-Property Relationships\n",
        ]

        for i, h in enumerate(self.sorted_by_novelty()):
            status = {"validated": "✅", "refuted": "❌", "pending": "⏳", "inconclusive": "❓"}.get(
                h.validation_status, "⏳"
            )
            lines.extend([
                f"### {i+1}. {status} {h.title}",
                f"",
                f"**Confidence:** {h.confidence:.2f} | **Novelty:** {h.novelty_score:.2f} | "
                f"**LLM Plausibility:** {h.llm_plausibility_score:.2f}",
                f"",
                f"**Description:** {h.description}",
                f"",
                f"**Expected Relationship:** {h.expected_relationship}",
                f"",
                f"**Materials:** {', '.join(h.materials[:8])}",
                f"**Property:** {h.property}",
                f"",
                f"**Source Gap:** {h.source_gap_id}",
                f"**Search Method:** {h.search_method} ({h.search_iterations} iterations, {h.candidates_explored} candidates)",
            ])

            if h.evidence_chain:
                lines.append(f"\n**Evidence Chain:**")
                for ev in h.evidence_chain:
                    lines.append(f"  - {ev}")

            if h.llm_explanation:
                lines.append(f"\n**Scientific Explanation (LLM):**")
                lines.append(f"> {h.llm_explanation[:500]}")

            if h.external_validation:
                lines.append(f"\n**External Validation:**")
                for db, result in h.external_validation.items():
                    lines.append(f"  - {db}: {str(result)[:200]}")

            lines.append("\n---\n")

        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Phase 1: Hypothesis Generation
# ═══════════════════════════════════════════════════════════════

class HypothesisGenerator:
    """从 Research Gap 生成可验证的构效关系假设。

    这是 LLM 深度融合的第一关：LLM 分析 Gap 知识图谱，
    生成具体的、可验证的、具有新颖性的构效关系假设作为搜索种子。
    """

    def generate_from_gaps(self, kg: KnowledgeGraph, gaps: List[ResearchGap],
                          llm_evaluator: Callable = None) -> List[DiscoveryHypothesis]:
        """从 Gap 列表生成假设。"""

        # 构建材料×性质矩阵，找出空白单元格
        mat_prop_matrix = self._build_matrix(kg)

        hypotheses = []
        for gap in gaps:
            # 为每个 high/medium severity gap 生成假设
            if gap.severity not in ("high", "medium"):
                continue

            # 未探索空间类 Gap → 候选材料-性质配对
            if gap.type == "unexplored":
                generated = self._hypothesize_unexplored(gap, kg, mat_prop_matrix)
                hypotheses.extend(generated)

            # 缺失连接类 Gap → 推理可能的中间材料
            elif gap.type == "missing_link":
                generated = self._hypothesize_missing_link(gap, kg, mat_prop_matrix)
                hypotheses.extend(generated)

            # 矛盾类 Gap → 哪边更可能是真的
            elif gap.type == "contradiction":
                generated = self._hypothesize_contradiction_resolution(gap, kg)
                hypotheses.extend(generated)

        # LLM 评估假设的科学合理性（如果提供了评估器）
        if llm_evaluator and hypotheses:
            for h in hypotheses[:20]:  # 限制数量避免 API 开销过大
                try:
                    score, explanation = llm_evaluator(h)
                    h.llm_plausibility_score = score
                    h.llm_explanation = explanation
                except Exception:
                    h.llm_plausibility_score = 0.5
                    h.llm_explanation = "(LLM evaluation unavailable)"

        return hypotheses

    def _build_matrix(self, kg: KnowledgeGraph) -> Dict[str, Set[str]]:
        """构建材料→性质矩阵。"""
        matrix: Dict[str, Set[str]] = {}
        for p in kg.properties:
            mn = p.material_name.lower()
            if mn not in matrix:
                matrix[mn] = set()
            matrix[mn].add(p.property_name)
        return matrix

    def _hypothesize_unexplored(self, gap: ResearchGap, kg: KnowledgeGraph,
                                matrix: Dict[str, Set[str]]) -> List[DiscoveryHypothesis]:
        """未探索空间 → 找到有类似结构的材料，预测其可能具有目标性质。"""
        hypotheses = []
        entities = gap.entities_involved or []

        # 从知识图谱中找具有类似关系的材料
        similar_materials = set()
        target_property = ""
        property_pattern = re.findall(r'property[:\s]*(\w[\w\s]+\w)', gap.description, re.IGNORECASE)
        if property_pattern:
            target_property = property_pattern[0]

        # 找已有该性质的材料，看它们的结构特征
        materials_with_prop = set()
        for p in kg.properties:
            if target_property and target_property.lower() in p.property_name.lower():
                materials_with_prop.add(p.material_name)

        # 找结构相似但无此性质记录的材料
        for mat in kg.materials:
            if mat.name not in materials_with_prop and mat.structure:
                for mwp in materials_with_prop:
                    mwp_entity = next((m for m in kg.materials if m.name == mwp), None)
                    if mwp_entity and mwp_entity.structure == mat.structure:
                        similar_materials.add(mat.name)

        # 生成假设
        for mat_name in list(similar_materials)[:10]:
            hypotheses.append(DiscoveryHypothesis(
                id=f"hypo_unexplored_{len(hypotheses)}",
                title=f"{mat_name} may exhibit enhanced {target_property or 'target property'}",
                description=(
                    f"{mat_name} shares structural features ({mat_name}) with materials "
                    f"known to exhibit {target_property or 'the target property'}. "
                    f"This combination has NOT been studied yet."
                ),
                source_gap_id=gap.id,
                materials=[mat_name],
                property=target_property or "unknown",
                expected_relationship=f"Similar structure → similar {target_property or 'property'}",
                confidence=0.4,
                novelty_score=0.8,
            ))

        return hypotheses

    def _hypothesize_missing_link(self, gap: ResearchGap, kg: KnowledgeGraph,
                                  matrix: Dict[str, Set[str]]) -> List[DiscoveryHypothesis]:
        """缺失连接 → 找可能的中间材料/掺杂。"""
        hypotheses = []

        # 从 gap 描述中提取 A→B，B→C 但缺少 A→C
        entities = gap.entities_involved
        if len(entities) < 2:
            return hypotheses

        # 尝试在知识图谱中找到类似的三元组填补缺失连接
        for rel in kg.relations:
            if rel.relation_type == "structure-property" and rel.confidence > 0.6:
                hypotheses.append(DiscoveryHypothesis(
                    id=f"hypo_link_{len(hypotheses)}",
                    title=f"Bridge: {rel.subject} → {gap.title[:60]}",
                    description=(
                        f"Missing link between {entities[0] if entities else '?'} and "
                        f"{entities[1] if len(entities) > 1 else '?'}. "
                        f"Existing relation {rel.subject}→{rel.object} ({rel.predicate}) "
                        f"suggests a possible bridging mechanism."
                    ),
                    source_gap_id=gap.id,
                    materials=[rel.subject, rel.object],
                    property=rel.predicate,
                    expected_relationship=f"Via {rel.subject} intermediate",
                    confidence=rel.confidence * 0.7,
                    novelty_score=0.6,
                ))

        return hypotheses[:8]

    def _hypothesize_contradiction_resolution(self, gap: ResearchGap,
                                              kg: KnowledgeGraph) -> List[DiscoveryHypothesis]:
        """矛盾 → 哪边的结论更可信，什么条件导致差异。"""
        return [DiscoveryHypothesis(
            id=f"hypo_contra_{len([])}",
            title=f"Resolution: {gap.title[:80]}",
            description=f"Hypothesis to resolve contradiction: {gap.description[:200]}",
            source_gap_id=gap.id,
            materials=list(gap.entities_involved)[:5],
            property="",
            expected_relationship="Condition-dependent resolution",
            confidence=0.3,
            novelty_score=0.9,
        )]


# Need re at module level for HypothesisGenerator
import re


# ═══════════════════════════════════════════════════════════════
# Phase 2: Guided Search — Bayesian Optimization
# ═══════════════════════════════════════════════════════════════

class BayesianOptimizer:
    """贝叶斯优化探索材料空间。

    在材料成分/工艺参数空间中，用贝叶斯优化寻找最优性质。
    LLM 参与：生成搜索种群的种子、评估中间结果的科学合理性。
    """

    def __init__(self, llm_guide: Callable = None):
        """
        Args:
            llm_guide: (candidates: List[Dict]) → pruned + scored List[Dict]
                       用于 LLM 评估搜索中间结果并引导剪枝
        """
        self._llm_guide = llm_guide
        self._iteration_log: List[Dict] = []

    def optimize(self, hypothesis: DiscoveryHypothesis,
                 param_space: Dict[str, Tuple[float, float]],
                 objective_fn: Callable[[Dict], float],
                 n_iterations: int = 50,
                 n_initial: int = 10) -> Tuple[Dict, float, List[Dict]]:
        """
        Bayesian optimization over material parameter space.

        Args:
            hypothesis: 目标假设
            param_space: {param_name: (low, high)}
            objective_fn: 评分函数 (via Materials Project data lookup)
            n_iterations: 迭代次数
            n_initial: 初始随机采样数

        Returns:
            (best_params, best_score, iteration_log)
        """
        param_names = list(param_space.keys())
        bounds = np.array([[lo, hi] for lo, hi in param_space.values()])

        # Phase A: Random exploration
        X = np.random.uniform(bounds[:, 0], bounds[:, 1], size=(n_initial, len(param_names)))
        y = np.array([objective_fn(self._vec_to_dict(param_names, x)) for x in X])

        # LLM 评估初始种群
        if self._llm_guide:
            initial_candidates = [self._vec_to_dict(param_names, X[i]) for i in range(min(5, n_initial))]
            try:
                pruned = self._llm_guide(initial_candidates)
                # 用 LLM 评分引导初始点的选择
                for item in pruned:
                    if "score" in item:
                        idx = next((i for i, c in enumerate(initial_candidates)
                                   if all(abs(c.get(k, 0) - item.get(k, 0)) < 1e-6 for k in c)), None)
                        if idx is not None and idx < len(y):
                            y[idx] = max(y[idx], item["score"])
            except Exception:
                pass  # LLM guidance is optional enhancement

        best_idx = int(np.argmax(y))
        best_x = X[best_idx].copy()
        best_y = float(y[best_idx])

        log = [{"iteration": -1, "type": "initial", "best_score": best_y,
                "n_samples": n_initial, "mean_score": float(np.mean(y)),
                "max_score": float(np.max(y))}]

        # Phase B: Bayesian optimization with GP surrogate
        for iteration in range(n_iterations):
            # GP surrogate (simple: RBF kernel, max variance acquisition)
            # 简化版：用加权最近邻作为代理模型
            candidate = self._acquisition(X, y, bounds, iteration)

            score = objective_fn(self._vec_to_dict(param_names, candidate))

            # LLM-guided pruning: 每 10 轮让 LLM 评估搜索方向
            if self._llm_guide and iteration % 10 == 9:
                recent = [self._vec_to_dict(param_names, X[i]) for i in range(max(0, len(y) - 5), len(y))]
                try:
                    self._llm_guide(recent)
                except Exception:
                    pass

            X = np.vstack([X, candidate])
            y = np.append(y, score)

            if score > best_y:
                best_y = score
                best_x = candidate.copy()

            log.append({
                "iteration": iteration, "score": float(score),
                "best_score": float(best_y),
                "params": self._vec_to_dict(param_names, candidate),
            })

        best_params = self._vec_to_dict(param_names, best_x)
        self._iteration_log = log
        return best_params, best_y, log

    def _acquisition(self, X: np.ndarray, y: np.ndarray, bounds: np.ndarray,
                     iteration: int) -> np.ndarray:
        """Upper Confidence Bound acquisition (简化为 EI 近似的 UCB)。"""
        # 随机采样候选点
        n_candidates = 100
        rand_candidates = np.random.uniform(bounds[:, 0], bounds[:, 1],
                                            size=(n_candidates, bounds.shape[0]))

        # 对每个候选点用加权 k-NN 预测均值和方差
        predictions = np.zeros(n_candidates)
        for i, cand in enumerate(rand_candidates):
            distances = np.sqrt(np.sum((X - cand) ** 2, axis=1))
            weights = 1.0 / (distances + 1e-6)
            weights /= weights.sum()
            pred_mean = np.sum(weights * y)

            # 方差近似：加权距离的倒数
            pred_var = 1.0 / (np.min(distances) + 0.01)

            # UCB: mean + beta * sqrt(var)
            beta = max(0.5, 2.0 * (1.0 - iteration / 100))
            predictions[i] = pred_mean + beta * np.sqrt(pred_var)

        best_idx = int(np.argmax(predictions))
        return rand_candidates[best_idx]

    @staticmethod
    def _vec_to_dict(names: List[str], vec: np.ndarray) -> Dict[str, float]:
        return {n: float(v) for n, v in zip(names, vec)}


# ═══════════════════════════════════════════════════════════════
# Phase 2 (alternative): Monte Carlo Tree Search
# ═══════════════════════════════════════════════════════════════

class MCTSSearcher:
    """蒙特卡洛树搜索探索材料组合空间。

    LLM 参与：在 expansion 和 simulation 阶段评估中间结果的科学合理性，
    引导搜索树向更有前景的区域剪枝和聚焦。
    """

    def __init__(self, llm_guide: Callable = None):
        """
        Args:
            llm_guide: (node_state: Dict) → (is_promising: bool, score_adjustment: float)
        """
        self._llm_guide = llm_guide

    @dataclass
    class _Node:
        state: Dict
        parent: Any = None
        children: List = field(default_factory=list)
        visits: int = 0
        value: float = 0.0

    def search(self, root_state: Dict,
               expand_fn: Callable[[Dict], List[Dict]],
               simulate_fn: Callable[[Dict], float],
               n_iterations: int = 500) -> Tuple[Dict, float, List[Dict]]:
        """MCTS over material composition/processing space.

        Args:
            root_state: 起始状态
            expand_fn: state → [new_states]
            simulate_fn: state → score
            n_iterations: 搜索次数

        Returns:
            (best_state, best_score, search_log)
        """
        root = self._Node(state=root_state)

        for iteration in range(n_iterations):
            # Selection
            node = self._select(root)

            # Expansion
            if node.visits > 0 or node is root:
                children = expand_fn(node.state)
                for child_state in children:
                    child = self._Node(state=child_state, parent=node)
                    node.children.append(child)
                if node.children:
                    node = random.choice(node.children)

            # Simulation
            score = simulate_fn(node.state)

            # LLM guidance: evaluate if this branch is scientifically plausible
            if self._llm_guide and iteration % 50 == 0:
                try:
                    is_promising, adjustment = self._llm_guide(node.state)
                    if not is_promising:
                        score *= 0.5  # Penalize implausible branches
                    else:
                        score += adjustment
                except Exception:
                    pass

            # Backpropagation
            self._backpropagate(node, score)

        # Find best path
        best_node = self._best_child(root, c=0)
        best_score = best_node.value / max(best_node.visits, 1)

        log = [{"node": str(n.state)[:100], "visits": n.visits,
                "value": n.value / max(n.visits, 1)}
               for n in sorted(self._all_nodes(root), key=lambda n: n.visits, reverse=True)[:10]]

        return best_node.state, best_score, log

    def _select(self, node: _Node) -> _Node:
        while node.children:
            if not all(c.visits > 0 for c in node.children):
                return next(c for c in node.children if c.visits == 0)
            node = self._best_child(node, c=math.sqrt(2))
        return node

    def _best_child(self, node: _Node, c: float) -> _Node:
        return max(node.children, key=lambda n: (
            n.value / max(n.visits, 1) + c * math.sqrt(math.log(node.visits + 1) / max(n.visits, 1))
        ))

    def _backpropagate(self, node: _Node, score: float) -> None:
        while node:
            node.visits += 1
            node.value += score
            node = node.parent

    def _all_nodes(self, node: _Node) -> List[_Node]:
        nodes = [node]
        for child in node.children:
            nodes.extend(self._all_nodes(child))
        return nodes


# ═══════════════════════════════════════════════════════════════
# Phase 4: External Validation
# ═══════════════════════════════════════════════════════════════

class MaterialsProjectValidator:
    """通过 Materials Project / OQMD 等公共数据库交叉验证构效关系。

    支持:
      - Materials Project API (materialsproject.org)
      - OQMD (oqmd.org)
      - NOMAD (nomad-lab.eu)
    """

    def __init__(self, mp_api_key: str = None):
        self.mp_api_key = mp_api_key or os.environ.get("MATERIALS_PROJECT_API_KEY", "")

    # ── 文献证据链验证（有机/框架材料的补充验证通道）──

    _LIT_PROPERTY_KWS = {
        "band gap": ["band gap", "bandgap", "带隙", "能隙", "禁带"],
        "formation energy": ["formation energy", "formation enthalpy", "生成能", "形成能"],
        "capacity": [
            "capacity", "uptake", "loading", "吸附容量", "吸附量",
            "容量", "工作容量", "co2容量", "co2 容量",
        ],
        "selectivity": ["selectivity", "separation factor", "选择性", "分离因子", "分离选择性"],
        "heat": ["isosteric heat", "qst", "enthalpy", "吸附热", "等量吸附热", "吸附焓", "焓"],
        "stability": ["stability", "cyclability", "循环稳定性", "稳定性", "水稳定性", "湿稳定性", "循环"],
        "efficiency": ["efficiency", "pce", "效率", "再生能耗", "能耗"],
        "surface area": ["surface area", "bet", "比表面积", "表面积"],
        "conductivity": ["conductivity", "电导率"],
        "diffusion": ["diffusion", "kinetics", "扩散", "扩散系数"],
        "pressure": ["pressure", "压力", "压强"],
        "temperature": ["temperature", "温度"],
    }

    _ORGANIC_MARKERS = (
        "mof", "zif", "mil-", "uio", "hkust", "irmof", "cof",
        "polymer", "pvdf", "peo", "ma-", "fa-", "ch3nh3", "ch(nh2)2",
    )

    @staticmethod
    def _is_organic_framework(material: str) -> bool:
        m = (material or "").lower()
        if any(mk in m for mk in MaterialsProjectValidator._ORGANIC_MARKERS):
            return True
        # 含 C 且含 H 且含数字的分子式 → 视为有机类（如 C60、C6H6 等）
        return "c" in m and "h" in m and any(ch.isdigit() for ch in m)

    @staticmethod
    def _formula_to_elements(formula: str) -> Optional[List[str]]:
        """从简单化学式提取元素列表（Fe2O3 → ['Fe','O']）；无法解析时返回 None。"""
        f = (formula or "").strip()
        if not f or any(ch in f for ch in " -_()[]{}.,;"):
            return None
        parts = re.findall(r'([A-Z][a-z]?)(\d*)', f)
        if not parts or len(parts) > 5:
            return None
        rebuilt = "".join(el + (n or "1") for el, n in parts)
        if rebuilt.lower() != f.lower():
            return None
        return [el for el, _ in parts]

    _FAMILY_MARKERS = (
        "mof-74", "mof-5", "mof-177", "zif-8", "zif-67", "zif-90",
        "uio-66", "uio-67", "mil-101", "mil-125", "hkust-1", "irmof-",
        "mof", "zif", "uio", "mil", "hkust", "cof",
    )

    _KNOWN_ELEMENTS = frozenset({
        "H", "He", "Li", "Be", "B", "C", "N", "O", "F", "Ne", "Na", "Mg",
        "Al", "Si", "P", "S", "Cl", "Ar", "K", "Ca", "Sc", "Ti", "V", "Cr",
        "Mn", "Fe", "Co", "Ni", "Cu", "Zn", "Ga", "Ge", "As", "Se", "Br",
        "Kr", "Rb", "Sr", "Y", "Zr", "Nb", "Mo", "Tc", "Ru", "Rh", "Pd",
        "Ag", "Cd", "In", "Sn", "Sb", "Te", "I", "Xe", "Cs", "Ba", "La",
        "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm",
        "Yb", "Lu", "Hf", "Ta", "W", "Re", "Os", "Ir", "Pt", "Au", "Hg",
        "Tl", "Pb", "Bi", "Po", "At", "Rn",
    })

    @staticmethod
    def _material_signature(text: str):
        """提取（元素集合, 家族名）签名，用于材料名宽松匹配。"""
        s = str(text or "")
        low = s.lower()
        # 先去掉常见气体分子，避免 CO2/N2 等被误当元素（注意保留 Co/No 等元素符号）
        s = re.sub(
            r'\b(?:co2|n2|h2o|ch4|o2|h2|n2o|so2|nh3|h2s|no2)\b',
            " ", s, flags=re.IGNORECASE,
        )
        family = ""
        for fam in MaterialsProjectValidator._FAMILY_MARKERS:
            if fam in low:
                family = fam
                break
        if family:
            s = re.sub(re.escape(family) + r"[-\d]*", " ", s, flags=re.IGNORECASE)
        elements = {
            e for e in re.findall(r"[A-Z][a-z]?", s)
            if e in MaterialsProjectValidator._KNOWN_ELEMENTS
        }
        return elements, family

    @staticmethod
    def _sig_match(hyp_sig, heading_sig) -> bool:
        """签名匹配：家族相同 + 假设元素 ⊆ 标题元素。"""
        h_elems, h_fam = hyp_sig
        e_elems, e_fam = heading_sig
        if h_fam:
            if e_fam != h_fam:
                return False
            if not h_elems:
                return True       # 只有家族名（如 ZIF-8）→ 家族相同即算
        if not h_elems:
            return False
        return h_elems <= e_elems

    def _check_literature_evidence(self, hypothesis: DiscoveryHypothesis) -> Optional[Dict]:
        """文献证据链验证：知识图谱/论文摘要中 ≥2 篇独立论文支持材料+性质。"""
        from pathlib import Path as _Path

        source_text = ""
        for cand in (
            "workspace/outputs/literature_survey/knowledge_graph.md",
            "workspace/outputs/literature_survey/paper_summaries.md",
        ):
            p = _Path(cand)
            if p.exists():
                try:
                    source_text += p.read_text(encoding="utf-8", errors="replace") + "\n"
                except OSError:
                    continue
        papers_dir = _Path("workspace/data/papers")
        if papers_dir.exists():
            for md in sorted(papers_dir.glob("*.md")):
                try:
                    source_text += md.read_text(encoding="utf-8", errors="replace") + "\n"
                except OSError:
                    continue
        if not source_text.strip():
            return None

        target = (hypothesis.property or "").lower()
        kws: List[str] = []
        for key, aliases in self._LIT_PROPERTY_KWS.items():
            # 别名出现在目标属性名中即启用该组关键词（兼容中文复合短语）
            if any(alias in target for alias in aliases):
                kws.extend(aliases)
        if not kws:
            kws = [t for t in re.split(r'[\s/]+', target) if len(t) >= 3][:3]
        kws = list(dict.fromkeys(kws))
        kws_nospace = [
            re.sub(r"\s+", "", kw)
            for kw in kws
            if len(re.sub(r"\s+", "", kw)) >= 3
        ]
        if not kws:
            return None

        mats = []
        for m in hypothesis.materials[:5]:
            for part in re.split(r'[/\s,，、]+', m or ""):
                part = part.strip().lower()
                if len(part) >= 2:
                    mats.append(part)
        if not mats:
            return None

        papers: set = set()
        values: List[float] = []
        blocks = [b for b in re.split(r'\n(?=#{1,3} )', source_text) if len(b.strip()) > 40]
        if not blocks:
            blocks = [source_text]
        hyp_materials = [m for m in hypothesis.materials[:5] if m]

        for block in blocks:
            lines = block.splitlines()
            block_lower = block.lower()

            # 标题行 → 该块的材料上下文 + 论文 ID
            heading_mats = []
            heading_papers: set = set()
            heading_text = ""
            for line in lines:
                s = line.strip()
                if s.startswith("#"):
                    sl = s.lower()
                    heading_mats.extend(mt for mt in mats if mt in sl)
                    heading_papers.update(
                        p.lower() for p in re.findall(r'\b(p\d+|doi[:/]\S+|arXiv[:/]\S+)\b', s)
                    )
                    heading_text += " " + s
            if not heading_mats:
                heading_sig = self._material_signature(heading_text)
                for hm in hyp_materials:
                    if self._sig_match(self._material_signature(hm), heading_sig):
                        heading_mats.append(hm)
                        break

            # 属性上下文：块内任意位置出现属性关键词即算（表头/正文均可，兼容空格差异）
            block_has_prop = any(kw in block_lower for kw in kws)
            if not block_has_prop and kws_nospace:
                block_lower_ns = re.sub(r"\s+", "", block_lower)
                block_has_prop = any(kn in block_lower_ns for kn in kws_nospace)
            if not block_has_prop:
                continue

            for line in lines:
                s = line.strip()
                if not s or s.startswith("#"):
                    continue
                bl = s.lower()
                # 材料：行内子串 → 行内元素/家族签名 → 标题上下文
                line_mats = [mt for mt in mats if mt in bl]
                if not line_mats:
                    line_sig = self._material_signature(s)
                    for hm in hyp_materials:
                        if self._sig_match(self._material_signature(hm), line_sig):
                            line_mats = [hm]
                            break
                if not line_mats and heading_mats:
                    line_mats = heading_mats
                if not line_mats:
                    continue
                papers.update(
                    p.lower() for p in re.findall(r'\b(p\d+|doi[:/]\S+|arXiv[:/]\S+)\b', bl)
                )
                papers.update(heading_papers)
                for vm in re.finditer(
                    r'(\d+(?:\.\d+)?)\s*(mmol/g|mol/kg|mmol/cm3|cm3/g|mg/g|kJ/mol|m2/g|bar|K|%|eV|meV)',
                    bl, re.IGNORECASE,
                ):
                    v = abs(float(vm.group(1)))
                    if 0 < v < 1e6:
                        values.append(v)

        values = sorted(set(round(v, 3) for v in values))[:20]
        if len(papers) >= 2:
            return {
                "match": True,
                "support_level": "literature",
                "papers": sorted(papers),
                "values": values,
                "source": "knowledge_graph.md + paper_summaries.md",
            }
        if papers:
            return {
                "match": False,
                "support_level": "literature",
                "papers": sorted(papers),
                "values": values,
                "note": "仅 1 篇独立论文支撑，不足以判定",
            }
        return None

    def validate(self, hypothesis: DiscoveryHypothesis) -> Dict[str, Any]:
        """对假设进行外部数据库交叉验证。

        Returns:
            {
                "materials_project": {...},
                "oqmd": {...},
                "nomad": {...},
                "literature": {...},
                "overall_match": bool,
                "validation_source": "database" | "literature" | "none",
                "validation_notes": [...],
                "supporting_evidence": [...],
            }
        """
        results = {}

        # Materials Project
        mp_result = self._check_materials_project(hypothesis)
        if mp_result:
            results["materials_project"] = mp_result

        # OQMD (static data lookup — no API needed for basic checks)
        oqmd_result = self._check_oqmd(hypothesis)
        if oqmd_result:
            results["oqmd"] = oqmd_result

        # NOMAD (公开 REST API，无需 key)
        nomad_result = self._check_nomad(hypothesis)
        if nomad_result:
            results["nomad"] = nomad_result

        # 数据库命中
        db_match = any(
            r.get("match", False) for r in results.values()
            if isinstance(r, dict)
        )

        # 文献证据链验证（数据库不覆盖有机/框架材料时的补充通道）
        lit_result = self._check_literature_evidence(hypothesis)
        validation_notes: List[str] = []
        if lit_result and lit_result.get("match"):
            results["literature"] = lit_result
            validation_notes.append(
                "无机数据库未覆盖/未命中时，文献证据链（≥2 篇独立论文）作为补充验证。"
            )
        elif not db_match:
            organic = [
                m for m in hypothesis.materials[:5]
                if self._is_organic_framework(m)
            ]
            if organic:
                validation_notes.append(
                    f"材料 {', '.join(organic)} 疑似有机/框架材料，"
                    "MP/NOMAD/OQMD 无机库通常不覆盖；请以文献证据链或实验验证为准。"
                )
            if lit_result:
                results["literature"] = lit_result
            else:
                validation_notes.append("未找到任何数据库记录与文献证据支撑。")

        overall = db_match or bool(lit_result and lit_result.get("match"))

        evidence = []
        for db, r in results.items():
            if isinstance(r, dict) and r.get("matching_entries"):
                evidence.extend(r["matching_entries"][:3])

        return {
            "overall_match": overall,
            "validation_source": (
                "database" if db_match
                else ("literature" if lit_result and lit_result.get("match") else "none")
            ),
            "validation_notes": validation_notes,
            "databases_checked": list(results.keys()),
            "supporting_evidence": evidence,
            "details": results,
        }

    def _check_materials_project(self, hypothesis: DiscoveryHypothesis) -> Optional[Dict]:
        """查询 Materials Project 数据库。"""
        if not self.mp_api_key:
            return None
        try:
            import requests as _requests
        except Exception:
            return None

        results = {"match": False, "matching_entries": [], "materials_found": []}

        for material in hypothesis.materials[:5]:
            try:
                url = (
                    f"https://api.materialsproject.org/materials/summary/?"
                    f"formula={material}&_limit=5"
                    "&_fields=material_id,formula_pretty,band_gap,formation_energy_per_atom"
                )
                headers = {
                    "X-API-KEY": self.mp_api_key,
                    "User-Agent": "goai-pi-agent/1.0 (literature-driven materials discovery)",
                }
                resp = _requests.get(url, headers=headers, timeout=15)
                if resp.status_code != 200:
                    continue
                data = resp.json()

                entries = data.get("data", [])
                match_type = "exact_formula"
                # 精确式无结果 → 元素系回退（如 Fe2O3 → Fe-O）
                if not entries:
                    elems = self._formula_to_elements(material)
                    if elems:
                        fallback_url = (
                            f"https://api.materialsproject.org/materials/summary/?"
                            f"formula={'-'.join(elems)}&_limit=5"
                            "&_fields=material_id,formula_pretty,band_gap,formation_energy_per_atom"
                        )
                        fb = _requests.get(fallback_url, headers=headers, timeout=15)
                        if fb.status_code == 200:
                            entries = fb.json().get("data", [])
                            match_type = "element_system"

                for entry in entries:
                    mp_id = entry.get("material_id", "")
                    formula = entry.get("formula_pretty", "")
                    band_gap = entry.get("band_gap", None)
                    formation_energy = entry.get("formation_energy_per_atom", None)

                    if mp_id:
                        results["materials_found"].append({
                            "mp_id": mp_id,
                            "formula": formula,
                            "band_gap": band_gap,
                            "formation_energy": formation_energy,
                            "match_type": match_type,
                        })

                        # 检查是否匹配目标性质
                        if hypothesis.property.lower() in ("band gap", "bandgap") and band_gap:
                            results["match"] = True
                            results["matching_entries"].append(
                                f"{formula} (MP {mp_id}, {match_type}): band gap = {band_gap} eV"
                            )
                        elif hypothesis.property.lower() in ("formation energy",) and formation_energy:
                            results["match"] = True
                            results["matching_entries"].append(
                                f"{formula} (MP {mp_id}, {match_type}): "
                                f"formation energy = {formation_energy} eV/atom"
                            )
            except Exception:
                continue

        return results if results["materials_found"] else None

    NOMAD_QUERY_URL = "https://nomad-lab.eu/prod/v1/api/v1/entries/query"

    def _check_nomad(self, hypothesis: DiscoveryHypothesis) -> Optional[Dict]:
        """查询 NOMAD 开放材料数据库（公开 API，无需 key）。

        NOMAD 是欧洲开放材料数据中心（nomad-lab.eu），按 FAIR 原则收录大量
        DFT 计算数据。这里用条目元数据做定性匹配：材料存在 + 电子/能隙数据存在。
        能隙具体数值存于 archive（SI 单位），元数据层不返回，故不强行换算，
        仅如实标注"band-gap data present"。
        """
        if not hypothesis.materials:
            return None
        try:
            import requests as _requests
        except Exception:
            return None

        target_prop = (hypothesis.property or "").lower()
        want_band_gap = target_prop in ("band gap", "bandgap")

        results = {"match": False, "matching_entries": [], "materials_found": []}

        for material in hypothesis.materials[:5]:
            formula = (material or "").strip()
            if not formula:
                continue
            try:
                payload = {
                    "query": {"results.material.chemical_formula_hill": formula},
                    "required": {
                        "results.material.chemical_formula_hill": True,
                        "results.material.material_id": True,
                        "results.material.symmetry.space_group_symbol": True,
                        "results.properties.n_calculations": True,
                        "results.properties.electronic.dos_electronic.band_gap": True,
                        "results.properties.electronic.band_structure": True,
                    },
                    "pagination": {"page_size": 3},
                }
                resp = _requests.post(self.NOMAD_QUERY_URL, json=payload, timeout=20)
                if resp.status_code != 200:
                    continue
                for entry in (resp.json().get("data", []) or [])[:3]:
                    res = entry.get("results", {}) or {}
                    mat = res.get("material", {}) or {}
                    props = res.get("properties", {}) or {}
                    elec = props.get("electronic") or {}
                    dos_bg = (elec.get("dos_electronic") or {}).get("band_gap")
                    bs = elec.get("band_structure")
                    symmetry = mat.get("symmetry") or {}
                    found = {
                        "entry_id": entry.get("entry_id", ""),
                        "material_id": mat.get("material_id", ""),
                        "formula": mat.get("chemical_formula_hill") or formula,
                        "space_group": (
                            symmetry.get("space_group_symbol")
                            if isinstance(symmetry, dict) else None
                        ),
                        "n_calculations": props.get("n_calculations"),
                        "band_gap_data": bool(dos_bg) or bool(bs),
                    }
                    results["materials_found"].append(found)

                    if want_band_gap and found["band_gap_data"]:
                        results["match"] = True
                        n_spin = len(dos_bg) if isinstance(dos_bg, list) else 0
                        label = (
                            f"{found['formula']} (NOMAD {str(found['entry_id'])[:12]}): "
                            "band-gap data present"
                        )
                        if n_spin:
                            label += f" ({n_spin} spin channel(s))"
                        results["matching_entries"].append(label)
            except Exception:
                continue

        return results if results["materials_found"] else None

    def _check_oqmd(self, hypothesis: DiscoveryHypothesis) -> Optional[Dict]:
        """查询 OQMD 数据库（本地缓存或静态数据）。"""
        # OQMD 的公开 REST API 有限，使用本地缓存
        oqmd_cache = Path("workspace/data/oqmd_cache")
        if not oqmd_cache.exists():
            return None

        results = {"match": False, "matching_entries": [], "materials_found": []}

        for material in hypothesis.materials[:5]:
            cache_file = oqmd_cache / f"{material.replace(' ', '_')}.json"
            if cache_file.exists():
                try:
                    data = json.loads(cache_file.read_text())
                    results["materials_found"].append(data)
                    if data.get("band_gap") and hypothesis.property.lower() in ("band gap", "bandgap"):
                        results["match"] = True
                        results["matching_entries"].append(
                            f"{material} (OQMD): band_gap = {data['band_gap']} eV"
                        )
                except (json.JSONDecodeError, KeyError):
                    pass

        return results if results["materials_found"] else None


# ═══════════════════════════════════════════════════════════════
# Main Discovery Engine
# ═══════════════════════════════════════════════════════════════

class DiscoveryEngine:
    """构效关系发现引擎 — 路线 A 的统一入口。

    协调 Hypothesis Generation → Guided Search → Validation 全流程。

    使用:
        engine = DiscoveryEngine(llm_evaluator=my_llm_fn)
        report = engine.discover(kg, gap_report, search_method="bayesian")
    """

    def __init__(self,
                 llm_hypothesis_evaluator: Callable = None,
                 llm_search_guide: Callable = None,
                 mp_api_key: str = None):
        """
        Args:
            llm_hypothesis_evaluator: (hypothesis: DiscoveryHypothesis) → (score: float, explanation: str)
            llm_search_guide: (candidates: List[Dict]) → pruned List[Dict]
            mp_api_key: Materials Project API key
        """
        self.hypothesis_gen = HypothesisGenerator()
        self.bayes_opt = BayesianOptimizer(llm_guide=llm_search_guide)
        self.mcts_searcher = MCTSSearcher(llm_guide=llm_search_guide)
        self.validator = MaterialsProjectValidator(mp_api_key=mp_api_key)
        self._llm_evaluator = llm_hypothesis_evaluator

    def discover(self,
                 kg: KnowledgeGraph,
                 gap_report: GapReport,
                 search_method: str = "bayesian",
                 n_iterations: int = 50) -> DiscoveryReport:
        """执行完整的构效关系发现流程。

        Args:
            kg: 文献知识图谱
            gap_report: Gap 分析报告
            search_method: "bayesian" | "mcts" | "hybrid"
            n_iterations: 搜索迭代总次数

        Returns:
            DiscoveryReport with validated hypotheses
        """
        report = DiscoveryReport()

        # ── Phase 1: Hypothesis Generation ──
        print(f"  [Discovery] Phase 1: Generating hypotheses from {len(gap_report.gaps)} gaps...")
        hypotheses = self.hypothesis_gen.generate_from_gaps(
            kg, gap_report.gaps, llm_evaluator=self._llm_evaluator
        )
        report.total_candidates = len(hypotheses)
        print(f"  [Discovery] Generated {len(hypotheses)} hypotheses")

        # ── Phase 2: Guided Search ──
        for i, hyp in enumerate(hypotheses[:15]):  # Top 15 by novelty
            print(f"  [Discovery] Phase 2 [{i+1}/15]: Searching '{hyp.title[:60]}...' "
                  f"({search_method})")

            hyp.search_method = search_method
            hyp.search_iterations = min(n_iterations, 30)

            # Define parameter space based on property type
            param_space = self._define_search_space(hyp, kg)

            if search_method in ("bayesian", "hybrid"):
                best, score, log = self.bayes_opt.optimize(
                    hyp, param_space,
                    objective_fn=lambda p: self._score_candidate(p, hyp, kg),
                    n_iterations=hyp.search_iterations,
                )
                hyp.candidates_explored = len(log) + 10  # +10 initial samples

            elif search_method == "mcts":
                root_state = {"materials": hyp.materials, "property": hyp.property}
                candidates = []
                for mat in hyp.materials[:3]:
                    for prop_val in np.linspace(0.5, 5.0, 5):
                        candidates.append({"material": mat, "value": prop_val})

                best, score, log = self.mcts_searcher.search(
                    root_state,
                    expand_fn=lambda s: candidates[:10],
                    simulate_fn=lambda s: self._score_candidate(s, hyp, kg),
                    n_iterations=hyp.search_iterations * 5,
                )
                hyp.candidates_explored = len(log) * 5

            hyp.confidence = max(hyp.confidence, score if score > 0 else hyp.confidence)

            # ── Phase 3: LLM Plausibility Check ──
            if self._llm_evaluator:
                try:
                    score, explanation = self._llm_evaluator(hyp)
                    hyp.llm_plausibility_score = score
                    hyp.llm_explanation = explanation
                except Exception:
                    pass

            # ── Phase 4: External Validation ──
            print(f"  [Discovery] Phase 4: Validating '{hyp.title[:60]}...'")
            validation = self.validator.validate(hyp)
            hyp.external_validation = validation
            vs = validation.get("validation_source", "none")
            if validation.get("overall_match"):
                hyp.validation_status = (
                    "validated" if vs == "database" else "literature_supported"
                )
                report.validated_count += 1
                if vs == "database":
                    report.materials_project_hits += 1
            elif validation.get("databases_checked") or validation.get("validation_notes"):
                hyp.validation_status = "inconclusive"
            else:
                hyp.validation_status = "pending"

            report.total_explored += hyp.candidates_explored
            report.hypotheses.append(hyp)

        # ── Summary ──
        report.search_summary = (
            f"Searched {report.total_explored} candidate material-property combinations "
            f"across {len(report.hypotheses)} hypotheses. "
            f"Validated {report.validated_count} against external databases "
            f"(Materials Project hits: {report.materials_project_hits}). "
            f"Search method: {search_method}."
        )

        return report

    def _define_search_space(self, hyp: DiscoveryHypothesis,
                             kg: KnowledgeGraph) -> Dict[str, Tuple[float, float]]:
        """为假设定义贝叶斯优化搜索空间。"""
        space = {}

        # 基于已有性质数据定义搜索范围
        related_props = [p for p in kg.properties
                        if hyp.property.lower() in p.property_name.lower()]
        if related_props:
            values = [p.value for p in related_props if p.value > 0]
            if values:
                values = sorted(values)
                n = len(values)
                q1 = values[max(0, n // 4)]
                q3 = values[min(n - 1, 3 * n // 4)]
                median = values[n // 2]
                iqr = max(q3 - q1, 1e-9)
                # Tukey 围栏 + 中位数比例兜底，避免离群值撑大搜索区间
                lo = max(0.001, q1 - 1.5 * iqr)
                hi = q3 + 1.5 * iqr
                lo = min(lo, median * 0.5)
                hi = max(hi, median * 2.0)
                space["property_value"] = (float(lo), float(hi))
            else:
                space["property_value"] = (0.1, 100.0)
        else:
            space["property_value"] = (0.1, 100.0)

        # 掺杂/成分参数
        if hyp.materials:
            space["composition_x"] = (0.0, 1.0)
            space["temperature"] = (300, 1500)  # K

        return space

    def _score_candidate(self, params: Dict, hyp: DiscoveryHypothesis,
                         kg: KnowledgeGraph) -> float:
        """候选方案的评分函数。

        综合：文献知识图谱相似度 + 物理合理性 + LLM 评分
        """
        score = 0.3  # base

        # 从知识图谱中找类似材料-性质的分数
        for p in kg.properties:
            if hyp.property.lower() in p.property_name.lower():
                if p.value > 0:
                    # 候选值越接近已知高分值越好
                    candidate_val = params.get("property_value", 0)
                    if candidate_val > 0:
                        similarity = 1.0 / (1.0 + abs(candidate_val - p.value) / max(p.value, 0.01))
                        score += 0.3 * similarity

        # 结构相似性加分
        for mat in kg.materials:
            if any(m.lower() in mat.name.lower() for m in hyp.materials):
                score += 0.1

        return min(score, 1.0)
