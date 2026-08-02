"""
知识图谱数据模型 — 文献调研的核心数据结构
===========================================
定义材料实体、性质记录、合成条件、关系三元组，
以及跨文献知识融合（实体对齐 + 关系去重 + 冲突检测）。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from collections import defaultdict


# ═══════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class MaterialEntity:
    """材料实体"""
    name: str
    chemical_formula: Optional[str] = None
    composition: Dict[str, float] = field(default_factory=dict)
    structure: Optional[str] = None
    space_group: Optional[str] = None
    morphology: Optional[str] = None
    doping: Optional[str] = None
    defects: Optional[str] = None
    source_papers: List[str] = field(default_factory=list)
    source_context: str = ""


@dataclass
class PropertyRecord:
    """性质记录（单个数值）"""
    property_name: str
    value: float
    unit: str = ""
    condition: str = ""
    material_name: str = ""
    measurement_method: str = ""
    is_baseline: bool = False
    comparison: Optional[str] = None
    error_range: Optional[Tuple[float, float]] = None
    source_paper: str = ""
    source_context: str = ""


@dataclass
class SynthesisRecord:
    """合成/工艺记录"""
    material_name: str
    method: str
    precursors: List[str] = field(default_factory=list)
    temperature: Optional[float] = None
    temperature_unit: str = "°C"
    pressure: Optional[float] = None
    pressure_unit: str = "atm"
    duration: Optional[float] = None
    duration_unit: str = "h"
    solvent: Optional[str] = None
    atmosphere: Optional[str] = None
    ph: Optional[float] = None
    yield_value: Optional[float] = None
    yield_unit: str = "%"
    post_treatment: Optional[str] = None
    source_paper: str = ""
    source_context: str = ""


@dataclass
class Relation:
    """知识关系三元组"""
    subject: str
    predicate: str
    object: str
    confidence: float = 0.5
    evidence: str = ""
    source_paper: str = ""
    relation_type: str = ""


@dataclass
class KnowledgeGraph:
    """文献知识图谱"""
    materials: List[MaterialEntity] = field(default_factory=list)
    properties: List[PropertyRecord] = field(default_factory=list)
    synthesis: List[SynthesisRecord] = field(default_factory=list)
    relations: List[Relation] = field(default_factory=list)
    papers_processed: List[str] = field(default_factory=list)
    extraction_metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    def save(self, filepath: str):
        Path(filepath).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2))

    @staticmethod
    def load(filepath: str) -> KnowledgeGraph:
        """从 JSON 文件加载知识图谱（兼容最小化格式）。"""
        data = json.loads(Path(filepath).read_text(encoding="utf-8"))
        kg = KnowledgeGraph()
        kg.materials = [MaterialEntity(**m) for m in data.get("materials", [])]
        kg.properties = [PropertyRecord(**p) for p in data.get("properties", [])]
        kg.synthesis = [SynthesisRecord(**s) for s in data.get("synthesis", [])]
        kg.relations = [Relation(**r) for r in data.get("relations", [])]
        kg.papers_processed = data.get("papers_processed", [])
        kg.extraction_metadata = data.get("extraction_metadata", {})
        return kg

    def stat(self) -> Dict:
        """返回图谱统计信息。"""
        return {
            "materials": len(self.materials),
            "properties": len(self.properties),
            "synthesis_records": len(self.synthesis),
            "relations": len(self.relations),
            "papers_processed": len(self.papers_processed),
            "unique_property_types": len(set(p.property_name for p in self.properties)),
            "unique_methods": len(set(s.method for s in self.synthesis)),
        }


# ═══════════════════════════════════════════════════════════════
# Knowledge Fusion — 跨批/跨文献实体对齐与去重
# ═══════════════════════════════════════════════════════════════

class KnowledgeFusion:
    """跨文献知识融合：实体对齐 + 关系去重 + 冲突检测"""

    @staticmethod
    def merge(kg1: KnowledgeGraph, kg2: KnowledgeGraph) -> KnowledgeGraph:
        """合并两个知识图谱，按实体键去重。"""
        merged = KnowledgeGraph()

        # 材料实体去重（基于名称标准化）
        seen_materials: Dict[str, MaterialEntity] = {}
        for m in kg1.materials + kg2.materials:
            key = (m.chemical_formula or m.name).lower().strip()
            if key in seen_materials:
                seen_materials[key].source_papers.extend(m.source_papers)
                seen_materials[key].source_papers = list(set(seen_materials[key].source_papers))
            else:
                seen_materials[key] = m
        merged.materials = list(seen_materials.values())

        # 性质去重（同材料 + 同性质 + 同条件）
        seen_props: Dict[Tuple, PropertyRecord] = {}
        for p in kg1.properties + kg2.properties:
            key = (p.material_name.lower(), p.property_name.lower(), p.condition.lower())
            if key not in seen_props:
                seen_props[key] = p
        merged.properties = list(seen_props.values())

        # 合成工艺去重
        seen_syn: Set[Tuple] = set()
        for s in kg1.synthesis + kg2.synthesis:
            key = (s.material_name.lower(), s.method.lower(), str(s.temperature))
            if key not in seen_syn:
                seen_syn.add(key)
                merged.synthesis.append(s)

        # 关系去重
        seen_rel: Set[Tuple] = set()
        for r in kg1.relations + kg2.relations:
            key = (r.subject.lower(), r.predicate.lower(), r.object.lower())
            if key not in seen_rel:
                seen_rel.add(key)
                merged.relations.append(r)

        merged.papers_processed = list(set(kg1.papers_processed + kg2.papers_processed))
        return merged


# ═══════════════════════════════════════════════════════════════
# Markdown 知识图谱审计 — Agent 手写知识图谱（Markdown）的结构化体检
# ═══════════════════════════════════════════════════════════════

# 非材料的气体/分子（避免把 CO2、H2O 等吸附质误当材料）
_NON_MATERIALS = {
    "co2", "h2", "n2", "o2", "ch4", "so2", "no2", "nh3", "n2o", "h2s",
    "co", "no", "h2o", "ch3oh", "c2h5oh", "ch3nh2",
}

_MATERIAL_RE = re.compile(
    r'\b(?:'
    r'[A-Z][a-z]?\d+[A-Za-z0-9]*(?:-[A-Za-z0-9]+)*|'   # 化学式 Fe2O3 / MgO / MAPbI3
    r'[A-Z][a-z]?-(?:MOF|ZIF|MIL|UiO|HKUST|IRMOF|COF)-\d+|'  # Mg-MOF-74
    r'ZIF-\d+|UiO-\d+|MIL-\d+|HKUST-\d+|IRMOF-\d+|MOF-\d+|COF-\d+|'
    r'CsPb[A-Za-z0-9]+|FAPbI\d+|MAPbI\d+|MA[A-Za-z0-9]+|FA[A-Za-z0-9]+'
    r')\b'
)

_VALUE_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*'
    r'(mmol/g|mol/kg|mmol/cm3|mg/g|kJ/mol|kj/mol|wt%|m2/g|m²/g|bar|K|°C|℃|%|h|min|eV|meV)',
    re.IGNORECASE,
)

_PAPER_ID_RE = re.compile(r'\b(p\d+|doi[:/]\S+|arXiv[:/]\S+)\b', re.IGNORECASE)

# 性质关键词 → 规范性质键
_PROPERTY_KEYWORDS: Dict[str, List[str]] = {
    "capacity": ["capacity", "uptake", "loading", "吸附容量", "吸附量", "容量"],
    "selectivity": ["selectivity", "separation factor", "选择性", "分离因子", "分离比"],
    "heat": ["isosteric heat", "qst", "enthalpy", "吸附热", "等量吸附热", "焓"],
    "surface_area": ["surface area", "bet", "比表面积", "表面积"],
    "stability": ["stability", "cyclability", "循环稳定性", "稳定性", "再生性能"],
    "band_gap": ["band gap", "bandgap", "带隙", "能隙"],
    "formation_energy": ["formation energy", "生成能", "形成能"],
    "efficiency": ["efficiency", "pce", "效率"],
    "conductivity": ["conductivity", "电导率"],
    "diffusion": ["diffusion", "kinetics", "扩散系数", "扩散"],
    "temperature": ["temperature", "温度"],
    "pressure": ["pressure", "压力"],
    "thermal_conductivity": ["thermal conductivity", "导热系数", "热导率"],
    "dielectric": ["dielectric constant", "介电常数", "介电"],
    "hardness": ["hardness", "硬度"],
    "melting_point": ["melting point", "熔点"],
    "elastic_modulus": ["elastic modulus", "弹性模量", "杨氏模量"],
    "thermoelectric": ["seebeck", "figure of merit", "zt", "功率因子", "热电优值"],
    "ionic_conductivity": ["ionic conductivity", "离子电导率"],
    "strength": ["tensile strength", "强度"],
}


def _norm_material(name: str) -> str:
    """材料名归一化：小写 + 去除非字母数字。"""
    return "".join(ch for ch in str(name).lower() if ch.isalnum())


def audit_markdown_kg(text: str) -> Dict[str, Any]:
    """审计 Agent 手写的 Markdown 知识图谱。

    从自然语言/表格文本中抽取（材料, 性质, 数值, 单位, 论文ID）记录，
    并检测三类问题：
      - 数值冲突：同一材料同一性质、不同论文报告差异显著的数值
      - 实体重复：同一材料的不同写法
      - 溯源缺失：有数值但没有论文 ID 支撑

    Returns:
        {
            "stats": {...},
            "materials": [...],
            "properties": [...],
            "conflicts": [...],
            "duplicates": [...],
            "no_provenance_records": [...],
            "records": [...],
        }
    """
    blocks = [b.strip() for b in re.split(r'\n(?=#{1,3} )', text or "") if len(b.strip()) > 40]
    if not blocks:
        blocks = [text or ""]

    materials_seen: Dict[str, str] = {}       # norm → display name
    records: List[Dict[str, Any]] = []

    for block in blocks:
        current_materials: List[str] = []

        def _collect_materials(segment: str) -> List[str]:
            """从文本段中收集材料名并登记。"""
            found = []
            for m in re.findall(_MATERIAL_RE, segment):
                mn = _norm_material(m)
                if mn in _NON_MATERIALS or len(mn) < 2:
                    continue
                found.append(m)
                if mn not in materials_seen:
                    materials_seen[mn] = m
            return list(dict.fromkeys(found))

        for raw_line in block.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            # 标题行 → 更新当前材料
            if line.startswith("#"):
                mats = _collect_materials(line)
                if mats:
                    current_materials = mats
                continue

            # 非列表/表格行（叙述句）也参与，但列表/表格行优先
            inline_mats = _collect_materials(line)
            mats = inline_mats or current_materials
            if not mats:
                continue

            lower = line.lower()
            line_papers = sorted(set(p.lower() for p in re.findall(_PAPER_ID_RE, line)))
            line_values = []
            for vm in _VALUE_RE.finditer(lower):
                v = abs(float(vm.group(1)))
                if 0 < v < 1e6:
                    line_values.append((v, (vm.group(2) or "").lower()))

            for prop_key, kws in _PROPERTY_KEYWORDS.items():
                if not any(kw.lower() in lower for kw in kws):
                    continue
                if not line_values:
                    # 性质提到但该行无数值：仍记录（用于溯源审计）
                    for mat in mats:
                        records.append({
                            "material": mat,
                            "material_norm": _norm_material(mat),
                            "property": prop_key,
                            "value": None,
                            "unit": "",
                            "papers": line_papers,
                        })
                    continue
                for mat in mats:
                    for v, unit in line_values:
                        records.append({
                            "material": mat,
                            "material_norm": _norm_material(mat),
                            "property": prop_key,
                            "value": v,
                            "unit": unit,
                            "papers": line_papers,
                        })

    # ── 冲突检测：同 (材料, 性质, 单位) 数值差异 > 1.5 倍 ──
    groups: Dict[Tuple, List[Dict]] = {}
    for r in records:
        if r["value"] is None:
            continue
        key = (r["material_norm"], r["property"], r["unit"])
        groups.setdefault(key, []).append(r)

    conflicts = []
    for (mn, prop, unit), group in groups.items():
        vals = sorted(rec["value"] for rec in group)
        if len(vals) < 2 or vals[0] <= 0:
            continue
        if vals[-1] / vals[0] > 1.5:
            min_rec = min(group, key=lambda r: r["value"])
            max_rec = max(group, key=lambda r: r["value"])
            conflicts.append({
                "material": materials_seen.get(mn, mn),
                "property": prop,
                "unit": unit,
                "values": vals,
                "min_paper": min_rec["papers"],
                "max_paper": max_rec["papers"],
            })

    # ── 实体重复：归一化后相同但写法不同 ──
    by_norm: Dict[str, set] = {}
    for mn, display in materials_seen.items():
        by_norm.setdefault(mn, set()).add(display)
    duplicates = [
        {"norm": mn, "names": sorted(names)}
        for mn, names in by_norm.items() if len(names) > 1
    ]

    # ── 溯源缺失：有数值无论文 ID ──
    no_provenance = [
        {k: r[k] for k in ("material", "property", "value", "unit")}
        for r in records if r["value"] is not None and not r["papers"]
    ]

    return {
        "stats": {
            "materials": len(materials_seen),
            "property_records": len(records),
            "conflicts": len(conflicts),
            "duplicates": len(duplicates),
            "no_provenance": len(no_provenance),
        },
        "materials": sorted(materials_seen.values()),
        "properties": sorted(
            {r["property"] for r in records if r["value"] is not None}
        ),
        "conflicts": conflicts,
        "duplicates": duplicates,
        "no_provenance_records": no_provenance[:50],
        "records": records[:500],
    }
