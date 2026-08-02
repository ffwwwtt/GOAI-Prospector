"""
文档解析器 — 科学文献 PDF/DOCX/HTML 批量解析
============================================
双层架构：
  1. markitdown_utils (本地引擎) — PDF/DOCX/HTML → Markdown
  2. MinerU API (远程引擎) — PDF → 结构化 JSON（保留表格/公式/图表位置）

自动选择策略：
  - 中文论文 + 复杂表格/公式 → 优先 MinerU
  - 英文论文 / 简单文档 → markitdown_utils
  - MinerU 不可用时自动回退

解析结果统一为 ParsedDocument dataclass，包含：
  - 全文 Markdown
  - 章节结构（标题层级树）
  - 参考文献列表
  - 图表引用索引
  - 元数据（标题、作者、DOI 等）
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

# 本地引擎
from markitdown_utils import MarkItDown, parse_document as _md_parse


# ═══════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class Section:
    """文档章节"""
    title: str
    level: int                       # 标题层级 (1=#, 2=##, ...)
    content: str = ""                # 该节正文（不含子节）
    start_line: int = 0
    end_line: int = 0
    subsections: List[Section] = field(default_factory=list)
    tables: List[Dict] = field(default_factory=list)     # [{caption, markdown_table}]
    figures: List[str] = field(default_factory=list)      # [figure_caption]
    equations: List[str] = field(default_factory=list)    # [latex_formula]


@dataclass
class Reference:
    """参考文献条目"""
    index: int = 0
    raw_text: str = ""
    title: Optional[str] = None
    authors: Optional[str] = None
    year: Optional[int] = None
    journal: Optional[str] = None
    doi: Optional[str] = None
    url: Optional[str] = None


@dataclass
class ParsedDocument:
    """统一文档解析结果"""
    filepath: str
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    full_text: str = ""                    # 全文 Markdown
    sections: List[Section] = field(default_factory=list)
    references: List[Reference] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    parse_engine: str = "markitdown"       # "markitdown" | "mineru"
    parse_time_seconds: float = 0.0

    # 材料科学特有字段
    materials_mentioned: List[str] = field(default_factory=list)
    properties_mentioned: List[str] = field(default_factory=list)
    methods_mentioned: List[str] = field(default_factory=list)

    @property
    def text_sections(self) -> List[Section]:
        """返回所有非空的顶层章节"""
        return [s for s in self.sections if s.content.strip() or s.subsections]


# ═══════════════════════════════════════════════════════════════
# MarkItDown Parser Wrapper
# ═══════════════════════════════════════════════════════════════

class MarkItDownParser:
    """基于 markitdown_utils 的本地文档解析器"""

    def parse(self, filepath: str) -> ParsedDocument:
        import time
        t0 = time.time()

        md = MarkItDown()
        result = md.convert(filepath)
        raw_markdown = result.markdown
        title = result.title or self._extract_title(raw_markdown, filepath)

        doc = ParsedDocument(
            filepath=filepath,
            title=title,
            full_text=raw_markdown,
            parse_engine="markitdown",
            parse_time_seconds=round(time.time() - t0, 2),
        )

        # 结构解析
        doc.sections = self._parse_sections(raw_markdown)
        doc.references = self._extract_references(raw_markdown)
        doc.abstract = self._extract_abstract(raw_markdown)
        doc.authors = self._extract_authors(raw_markdown)

        # 材料科学实体快速提取（正则）
        doc.materials_mentioned = _extract_materials(raw_markdown)
        doc.properties_mentioned = _extract_properties(raw_markdown)
        doc.methods_mentioned = _extract_methods(raw_markdown)

        return doc

    def _parse_sections(self, text: str) -> List[Section]:
        """解析 Markdown 标题层级，构建章节树"""
        lines = text.split("\n")
        # 找所有标题行
        heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$')
        headings: List[Tuple[int, int, str, str]] = []  # (line_idx, level, marker, title)

        for i, line in enumerate(lines):
            m = heading_pattern.match(line.strip())
            if m:
                level = len(m.group(1))
                headings.append((i, level, m.group(1), m.group(2).strip()))

        if not headings:
            return [Section(title="Full Text", level=0, content=text)]

        # 构建章节树
        root_sections: List[Section] = []
        stack: List[Section] = []  # 层级栈

        for idx, (line_idx, level, _, title) in enumerate(headings):
            section = Section(title=title, level=level, start_line=line_idx)

            # 确定内容范围
            if idx + 1 < len(headings):
                next_line = headings[idx + 1][0]
                content_lines = lines[line_idx + 1:next_line]
            else:
                content_lines = lines[line_idx + 1:]
            section.content = "\n".join(content_lines).strip()
            section.end_line = line_idx + len(content_lines)

            # 找到正确的父级
            while stack and stack[-1].level >= level:
                stack.pop()

            if stack:
                stack[-1].subsections.append(section)
            else:
                root_sections.append(section)

            stack.append(section)

        return root_sections

    def _extract_abstract(self, text: str) -> str:
        """从文本中提取摘要"""
        patterns = [
            r'(?:^|\n)#*\s*(?:Abstract|ABSTRACT|摘要)\s*\n+(.*?)(?:\n#+\s|\n\n(?:Introduction|INTRO|引言))',
            r'(?:^|\n)(?:Abstract|ABSTRACT)[：:]\s*(.*?)(?:\n\n|\n(?:Keywords|KEYWORDS|关键词))',
        ]
        for pat in patterns:
            m = re.search(pat, text, re.DOTALL | re.IGNORECASE)
            if m:
                return m.group(1).strip()[:2000]
        # Fallback: first substantial paragraph
        paragraphs = text.split("\n\n")
        for p in paragraphs[:5]:
            p = p.strip()
            if len(p) > 100 and not p.startswith("#"):
                return p[:2000]
        return ""

    def _extract_authors(self, text: str) -> List[str]:
        """提取作者列表"""
        # 简单的作者行匹配
        author_patterns = [
            r'(?:Authors?|AUTHORS)[：:]\s*(.+?)(?:\n|$)',
            r'\n([A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:,\s*[A-Z][a-z]+(?:\s+[A-Z]\.?)?){2,})',
        ]
        for pat in author_patterns:
            m = re.search(pat, text[:2000], re.MULTILINE)
            if m:
                names = re.split(r'[,;、]', m.group(1))
                return [n.strip() for n in names if len(n.strip()) > 2]
        return []

    def _extract_references(self, text: str) -> List[Reference]:
        """提取参考文献"""
        refs: List[Reference] = []

        # 找参考文献区域
        ref_section_patterns = [
            r'(?:^|\n)#*\s*(?:References?|REFERENCES|参考文献|Bibliography|BIBLIOGRAPHY)\s*\n+(.*?)(?:\n#+\s|\Z)',
        ]
        ref_text = ""
        for pat in ref_section_patterns:
            m = re.search(pat, text, re.DOTALL)
            if m:
                ref_text = m.group(1)
                break

        if not ref_text:
            return refs

        # 解析编号引用 [1], [2], 等
        ref_entries = re.split(r'\n\s*(?=\[\d+\]|\d+\.\s)', ref_text)
        for i, entry in enumerate(ref_entries):
            entry = entry.strip()
            if not entry or len(entry) < 10:
                continue

            ref = Reference(index=i + 1, raw_text=entry[:500])

            # 提取 DOI
            doi_match = re.search(r'(?:doi|DOI)[：:\s]*([^\s,]+)', entry)
            if doi_match:
                ref.doi = doi_match.group(1).rstrip('.')

            # 提取年份
            year_match = re.search(r'\((\d{4})\)', entry)
            if year_match:
                ref.year = int(year_match.group(1))

            # 提取标题（引号内）
            title_match = re.search(r'[""]([^""]+)[""]', entry)
            if title_match:
                ref.title = title_match.group(1)[:200]

            refs.append(ref)

        return refs

    @staticmethod
    def _extract_title(text: str, filepath: str) -> str:
        """提取文档标题"""
        # 第一个 # 标题
        m = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
        if m:
            return m.group(1).strip()
        # 第一行非空文本
        for line in text.split("\n")[:5]:
            line = line.strip()
            if line and len(line) > 10:
                return line[:200]
        return Path(filepath).stem


# ═══════════════════════════════════════════════════════════════
# MinerU API Client
# ═══════════════════════════════════════════════════════════════

class MinerUParser:
    """MinerU 文档解析引擎客户端

    MinerU 是开源 PDF 解析引擎，支持：
      - PDF → 结构化 Markdown/JSON
      - 表格保留（含复杂合并单元格）
      - 数学公式识别并转为 LaTeX
      - 图表位置保留 + 图片提取

    支持两种模式：
      1. 本地部署（自建服务）
      2. MinerU Cloud API（mineru.net）
    """

    API_BASE = os.environ.get("MINERU_API_URL", "https://api.mineru.net")
    LOCAL_BASE = os.environ.get("MINERU_LOCAL_URL", "http://localhost:8888")

    def __init__(self, api_key: Optional[str] = None, mode: str = "cloud"):
        self.api_key = api_key or os.environ.get("MINERU_API_KEY", "")
        self.mode = mode  # "cloud" | "local"
        self._session = __import__('requests').Session()
        if self.api_key:
            self._session.headers["Authorization"] = f"Bearer {self.api_key}"

    @property
    def available(self) -> bool:
        if self.mode == "cloud":
            return bool(self.api_key)
        else:
            try:
                import requests as _r
                _r.get(f"{self.LOCAL_BASE}/health", timeout=2)
                return True
            except Exception:
                return False

    def parse(self, filepath: str) -> Optional[ParsedDocument]:
        """通过 MinerU 解析文档"""
        if not self.available:
            return None

        import time
        t0 = time.time()

        try:
            if self.mode == "cloud":
                result = self._parse_cloud(filepath)
            else:
                result = self._parse_local(filepath)

            if result:
                result.parse_time_seconds = round(time.time() - t0, 2)

            return result
        except Exception:
            return None

    def _parse_cloud(self, filepath: str) -> Optional[ParsedDocument]:
        import requests as _r
        with open(filepath, "rb") as f:
            resp = _r.post(
                f"{self.API_BASE}/v1/parse",
                files={"file": f},
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=300,
            )
        resp.raise_for_status()
        data = resp.json()
        return self._to_parsed_document(data, filepath, "mineru")

    def _parse_local(self, filepath: str) -> Optional[ParsedDocument]:
        import requests as _r
        with open(filepath, "rb") as f:
            resp = _r.post(
                f"{self.LOCAL_BASE}/parse",
                files={"file": f},
                timeout=300,
            )
        resp.raise_for_status()
        data = resp.json()
        return self._to_parsed_document(data, filepath, "mineru")

    def _to_parsed_document(self, data: Dict, filepath: str, engine: str) -> ParsedDocument:
        md_content = data.get("markdown", data.get("content", ""))
        sections_data = data.get("sections", data.get("structure", []))

        sections = []
        for s in sections_data:
            sections.append(Section(
                title=s.get("title", ""),
                level=s.get("level", 1),
                content=s.get("content", ""),
                tables=s.get("tables", []),
                figures=s.get("figures", []),
                equations=s.get("equations", []),
            ))

        refs = []
        for i, r in enumerate(data.get("references", [])):
            refs.append(Reference(
                index=i + 1,
                raw_text=r.get("raw", ""),
                title=r.get("title"),
                authors=r.get("authors"),
                year=r.get("year"),
                doi=r.get("doi"),
            ))

        return ParsedDocument(
            filepath=filepath,
            title=data.get("title"),
            authors=data.get("authors", []),
            abstract=data.get("abstract", ""),
            full_text=md_content,
            sections=sections,
            references=refs,
            metadata=data.get("metadata", {}),
            parse_engine=engine,
            materials_mentioned=data.get("materials", []),
            properties_mentioned=data.get("properties", []),
            methods_mentioned=data.get("methods", []),
        )


# ═══════════════════════════════════════════════════════════════
# Unified Parser Interface
# ═══════════════════════════════════════════════════════════════

class DocumentParser:
    """统一文档解析入口。

    自动选择最优解析引擎：
      1. MinerU（远程）— 最优质量，需 API Key
      2. MinerU（本地）— 高质量，需本地部署
      3. markitdown_utils — 本地离线，免费

    用法:
        parser = DocumentParser()
        doc = parser.parse("paper.pdf")
        print(doc.title, len(doc.sections))
    """

    def __init__(self,
                 mineru_api_key: Optional[str] = None,
                 prefer_mineru: bool = False):
        self._markitdown = MarkItDownParser()
        self._mineru = MinerUParser(api_key=mineru_api_key)
        self._prefer_mineru = prefer_mineru

    def parse(self, filepath: str) -> ParsedDocument:
        """解析单个文档"""
        # 策略选择
        if self._prefer_mineru and self._mineru.available:
            doc = self._mineru.parse(filepath)
            if doc:
                return doc

        # 中文 PDF 优先尝试 MinerU（中文解析质量更好）
        if filepath.lower().endswith(".pdf") and self._mineru.available:
            doc = self._mineru.parse(filepath)
            if doc:
                return doc

        return self._markitdown.parse(filepath)

    def parse_batch(self,
                    filepaths: List[str],
                    max_workers: int = 4) -> Dict[str, ParsedDocument]:
        """批量并发解析文档

        Args:
            filepaths: 文件路径列表
            max_workers: 并发数

        Returns:
            {filepath: ParsedDocument} 字典
        """
        results = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.parse, fp): fp for fp in filepaths}
            for future in as_completed(futures):
                fp = futures[future]
                try:
                    results[fp] = future.result()
                except Exception as e:
                    # 单文件失败不阻断批量处理
                    results[fp] = ParsedDocument(
                        filepath=fp,
                        full_text=f"[Parse Error: {e}]",
                        parse_engine="error",
                    )
        return results

    def parse_directory(self,
                        directory: str,
                        patterns: List[str] = None) -> Dict[str, ParsedDocument]:
        """解析目录下所有文档

        Args:
            directory: 目录路径
            patterns: 文件扩展名列表，默认 [".pdf", ".docx", ".html", ".txt"]

        Returns:
            {filepath: ParsedDocument} 字典
        """
        patterns = patterns or [".pdf", ".docx", ".html", ".htm", ".txt", ".md"]
        dir_path = Path(directory)
        if not dir_path.exists():
            return {}

        filepaths = []
        for pat in patterns:
            filepaths.extend(str(p) for p in dir_path.glob(f"**/*{pat}"))

        return self.parse_batch(filepaths)


# ═══════════════════════════════════════════════════════════════
# Quick Entity Extractors (Regex-based, for speed)
# ═══════════════════════════════════════════════════════════════

def _extract_materials(text: str) -> List[str]:
    """快速提取材料名（正则）"""
    patterns = [
        r'\b[A-Z][a-z]?[0-9]*(?:[A-Z][a-z]?[0-9]*)+(?:\b|_)',  # 化学式
        r'\b(?:perovskite|MOF|zeolite|graphene|MXene|TMD|HEA|COF|QD)\b',
        r'\b(?:metal-organic framework|covalent organic framework)\b',
        r'\b(?:oxide|sulfide|nitride|carbide|alloy|ceramic|polymer|composite)\b',
        r'\b(?:TiO2|SiO2|Al2O3|ZnO|Fe2O3|CuO|NiO|MoS2|WS2|BN|SiC|GaN|GaAs)\b',
        r'\b(?:MAPbI3|CsPbI3|FAPbI3|YBa2Cu3O7|LiFePO4|LiCoO2|NaFePO4)\b',
        r'\b(?:ZIF-\d+|UiO-\d+|MIL-\d+|HKUST-\d+|IRMOF-\d+)\b',
    ]
    materials = set()
    for i, pat in enumerate(patterns):
        # 化学式模式（索引 0）大小写敏感，避免 IGNORECASE 把普通英文词当材料
        flags = 0 if i == 0 else re.IGNORECASE
        for m in re.findall(pat, text, flags):
            if len(m) > 2:
                materials.add(m)
    return sorted(materials)[:50]


def _extract_properties(text: str) -> List[str]:
    """快速提取性质名"""
    patterns = [
        r'\b(?:band gap|conductivity|resistivity|capacitance|dielectric|permittivity)\b',
        r'\b(?:thermal conductivity|thermal expansion|specific heat|heat capacity)\b',
        r'\b(?:Young\'s modulus|bulk modulus|shear modulus|hardness|tensile strength|yield strength|elastic)\b',
        r'\b(?:PCE|power conversion efficiency|EQE|fill factor|open.circuit voltage|short.circuit current)\b',
        r'\b(?:figure of merit|ZT|Seebeck coefficient|carrier mobility|carrier concentration)\b',
        r'\b(?:catalytic activity|TOF|TON|selectivity|conversion|Faradaic efficiency|overpotential)\b',
        r'\b(?:adsorption capacity|uptake|permeability|permeance|separation factor)\b',
        r'\b(?:corrosion rate|corrosion potential|passivation|pitting|oxidation)\b',
        r'\b(?:magnetic moment|coercivity|remanence|Curie temperature|susceptibility)\b',
        r'\b(?:phase transition temperature|Tc|melting point|decomposition temperature|Tg)\b',
        r'\b(?:stability|degradation|lifetime|durability|cyclability|coulombic efficiency)\b',
        r'\b(?:photoluminescence|PLQY|quantum yield|fluorescence|phosphorescence)\b',
    ]
    props = set()
    for pat in patterns:
        for m in re.findall(pat, text, re.IGNORECASE):
            props.add(m.lower())
    return sorted(props)[:50]


def _extract_methods(text: str) -> List[str]:
    """快速提取实验/计算方法"""
    patterns = [
        r'\b(?:DFT|density functional theory|HF|Hartree.Fock|CCSD|MP2|GW approximation)\b',
        r'\b(?:molecular dynamics|MD simulation|Monte Carlo|MCTS|kinetic Monte Carlo)\b',
        r'\b(?:machine learning|deep learning|neural network|CNN|GNN|random forest|SVM)\b',
        r'\b(?:XRD|XPS|TEM|SEM|STEM|AFM|STM|NMR|EPR|FTIR|Raman|UV.vis|XANES|EXAFS)\b',
        r'\b(?:CVD|PVD|ALD|MBE|sputtering|spin.coating|dip.coating|electrodeposition)\b',
        r'\b(?:sol.gel|hydrothermal|solvothermal|co.precipitation|solid.state|mechanochemical)\b',
        r'\b(?:TG|DSC|DTA|TGA|BET|BJH|porosimetry|chemisorption|physisorption)\b',
        r'\b(?:VASP|Quantum ESPRESSO|CP2K|LAMMPS|GROMACS|Gaussian|ORCA|WIEN2k)\b',
        r'\b(?:Bayesian optimization|genetic algorithm|active learning|transfer learning)\b',
    ]
    methods = set()
    for pat in patterns:
        for m in re.findall(pat, text, re.IGNORECASE):
            methods.add(m)
    return sorted(methods)[:50]


# ═══════════════════════════════════════════════════════════════
# Quick Test
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = DocumentParser()
    import sys
    if len(sys.argv) > 1:
        doc = parser.parse(sys.argv[1])
        print(f"Title: {doc.title}")
        print(f"Authors: {doc.authors}")
        print(f"Abstract: {doc.abstract[:200]}...")
        print(f"Sections: {len(doc.sections)}")
        print(f"References: {len(doc.references)}")
        print(f"Materials: {doc.materials_mentioned[:10]}")
        print(f"Properties: {doc.properties_mentioned[:10]}")
        print(f"Methods: {doc.methods_mentioned[:10]}")
        print(f"Engine: {doc.parse_engine} ({doc.parse_time_seconds}s)")
    else:
        print("Usage: python parser.py <filepath>")
