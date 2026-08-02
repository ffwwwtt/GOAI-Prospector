"""
知识图谱数据模型 — 文献调研的核心数据结构
===========================================
定义材料实体、性质记录、合成条件、关系三元组，
以及跨文献知识融合（实体对齐 + 关系去重 + 冲突检测）。
"""
from __future__ import annotations

import json
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
