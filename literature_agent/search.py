"""
文献检索工具 — 多数据源统一的科学文献搜索引擎
==============================================
支持三大数据源，按优先级自动切换：
  1. Sciverse API  — 语义检索 + 全文证据片段定位（需 API Key）
  2. Sci-Base      — HuggingFace 开放数据集，2500万+篇论文（本地/远程）
  3. arXiv API     — 免费开放获取论文检索（兜底方案）

检索结果统一为 SearchResult dataclass，包含标题、作者、摘要、
全文链接、来源数据库、相关度分数等字段。

用法:
    from literature_agent.search import LiteratureSearcher

    searcher = LiteratureSearcher()
    results = searcher.search("perovskite solar cell stability", top_k=20)
    for r in results:
        print(r.title, r.score)
"""

from __future__ import annotations

import json
import os
import re
import time
import hashlib
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlencode
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests


# ═══════════════════════════════════════════════════════════════
# Data Models
# ═══════════════════════════════════════════════════════════════

@dataclass
class SearchResult:
    """统一的文献检索结果"""
    title: str
    authors: List[str] = field(default_factory=list)
    abstract: str = ""
    year: Optional[int] = None
    doi: Optional[str] = None
    url: Optional[str] = None
    source: str = "unknown"            # "sciverse" | "scibase" | "arxiv"
    score: float = 0.0                 # 相关度分数 [0, 1]
    citation_count: int = 0
    journal: Optional[str] = None
    keywords: List[str] = field(default_factory=list)
    full_text_snippet: Optional[str] = None  # 全文证据片段
    pdf_url: Optional[str] = None
    raw_metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str:
        """基于 DOI 或标题的稳定 ID"""
        if self.doi:
            return f"doi:{self.doi}"
        return f"title:{hashlib.md5(self.title.encode()).hexdigest()[:12]}"

    def to_dict(self) -> Dict:
        return asdict(self)

    def to_markdown(self) -> str:
        """格式化为 Markdown 引用条目"""
        authors_str = ", ".join(self.authors[:3])
        if len(self.authors) > 3:
            authors_str += f" et al. ({len(self.authors)} authors)"
        year_str = f" ({self.year})" if self.year else ""
        lines = [
            f"### {self.title}",
            f"**Authors:** {authors_str}{year_str}",
        ]
        if self.journal:
            lines.append(f"**Journal:** {self.journal}")
        if self.doi:
            lines.append(f"**DOI:** [{self.doi}](https://doi.org/{self.doi})")
        if self.abstract:
            lines.append(f"\n**Abstract:** {self.abstract[:500]}")
        if self.full_text_snippet:
            lines.append(f"\n**Evidence Snippet:** {self.full_text_snippet[:300]}")
        if self.keywords:
            lines.append(f"\n**Keywords:** {', '.join(self.keywords)}")
        lines.append(f"\n*Source: {self.source} | Score: {self.score:.3f} | Citations: {self.citation_count}*")
        lines.append("")
        return "\n".join(lines)


@dataclass
class SearchQuery:
    """结构化的检索查询"""
    text: str                              # 自然语言查询
    material: Optional[str] = None         # 材料名（如 "MAPbI3"）
    property: Optional[str] = None         # 目标性质（如 "band gap"）
    method: Optional[str] = None           # 方法（如 "DFT", "MCTS"）
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    top_k: int = 20
    sources: List[str] = field(default_factory=lambda: ["arxiv", "scibase"])
    # 自动解析查询中的结构化意图
    parsed_entities: Dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════
# Data Source Implementations
# ═══════════════════════════════════════════════════════════════

class ArxivSearcher:
    """arXiv API 搜索器（免费，无需 API Key）

    使用 arXiv 官方 API: https://info.arxiv.org/help/api/
    限制：每请求最多返回 ~100 条，请求间隔建议 >3s
    """

    BASE_URL = "http://export.arxiv.org/api/query"

    def __init__(self, cache_dir: Optional[str] = None):
        self._session = requests.Session()
        self._last_request = 0.0
        self._cache_dir = Path(cache_dir) if cache_dir else None
        if self._cache_dir:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    def search(self, query: SearchQuery, max_results: int = 50) -> List[SearchResult]:
        # arXiv 不支持自然语言短语，拆成单词用 AND 连接
        # "MOF CO2 capture" → all:MOF AND all:CO2 AND all:capture
        def _tokenize(text: str) -> list[str]:
            # 保留引号内的短语，其余拆词
            phrases = re.findall(r'"([^"]+)"', text)
            remaining = re.sub(r'"[^"]+"', '', text)
            words = [w for w in remaining.split() if len(w) > 1]
            return phrases + words

        terms = _tokenize(query.text)
        # 去掉太短的噪声词
        noise = {'of', 'for', 'in', 'on', 'the', 'a', 'an', 'is', 'are', 'and', 'or', 'with', 'by', 'to', 'at', 'as'}
        terms = [t for t in terms if t.lower() not in noise]

        # 加上材料/性质作为额外 AND 条件
        if query.material:
            terms.append(query.material)
        if query.property:
            terms.append(query.property)

        if not terms:
            terms = [query.text]

        search_query = " AND ".join(f'all:{t}' if ' ' not in t else f'all:"{t}"'
                                    for t in terms[:10])  # 最多 10 个词，避免过于严格

        params = {
            "search_query": search_query,
            "start": 0,
            "max_results": min(max_results, 100),
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        results = self._fetch(params)
        # Re-sort by relevance to query
        for r in results:
            r.score = self._compute_score(r, query)
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:max_results]

    def _fetch(self, params: Dict) -> List[SearchResult]:
        # Rate limiting
        elapsed = time.time() - self._last_request
        if elapsed < 3.0:
            time.sleep(3.0 - elapsed)

        cache_key = None
        if self._cache_dir:
            cache_key = self._cache_dir / f"arxiv_{hashlib.md5(str(params).encode()).hexdigest()[:16]}.json"
            if cache_key.exists():
                data = json.loads(cache_key.read_text())
                return [_dict_to_result(d) for d in data]

        resp = self._session.get(self.BASE_URL, params=params, timeout=30)
        self._last_request = time.time()
        resp.raise_for_status()

        results = _parse_arxiv_xml(resp.text)

        if cache_key:
            cache_key.write_text(json.dumps([r.to_dict() for r in results], ensure_ascii=False))
        return results

    @staticmethod
    def _compute_score(result: SearchResult, query: SearchQuery) -> float:
        """基于文本匹配的相关度分数"""
        score = 0.0
        query_lower = query.text.lower()
        title_lower = result.title.lower()
        abstract_lower = result.abstract.lower()

        # Title match
        query_terms = set(query_lower.split())
        title_terms = set(title_lower.split())
        if query_terms:
            overlap = len(query_terms & title_terms) / len(query_terms)
            score += overlap * 0.5

        # Abstract match
        if query_lower in abstract_lower:
            score += 0.3
        elif any(term in abstract_lower for term in query_terms if len(term) > 3):
            score += 0.2

        # Material/Property bonus
        if query.material and query.material.lower() in abstract_lower:
            score += 0.15
        if query.property and query.property.lower() in abstract_lower:
            score += 0.15

        # Recency bonus
        if result.year and query.year_from:
            if result.year >= query.year_from:
                score += 0.05

        return min(score, 1.0)


class SciverseSearcher:
    """Sciverse API 搜索器（需 API Key）

    Sciverse 科学智能数据库：
      - 5.16 亿条学术元数据
      - 814 种语言，130 万+ 期刊/会议
      - 语义检索 + 全文证据片段定位

    REST API: https://api.sciverse.space
      - /meta-search     — 结构化元数据搜索（BM25）
      - /agentic-search  — 语义块检索（RAG）
      - /content         — 读取论文全文片段
    """

    BASE_URL = "https://api.sciverse.space"

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("SCIVERSE_API_KEY", "")
        self._session = requests.Session()
        if self.api_key:
            self._session.headers.update({
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            })

    @property
    def available(self) -> bool:
        return bool(self.api_key)

    def search(self, query: SearchQuery, max_results: int = 50) -> List[SearchResult]:
        """使用 meta-search 进行结构化文献检索。"""
        if not self.available:
            return []

        # 构建查询字符串（合并主查询 + 材料 + 性质）
        query_parts = [query.text]
        if query.material:
            query_parts.append(query.material)
        if query.property:
            query_parts.append(query.property)

        payload = {
            "query": " ".join(query_parts),
            "page_size": min(max_results, 50),
            "page": 1,
        }
        if query.year_from:
            payload["year_from"] = query.year_from
        if query.year_to:
            payload["year_to"] = query.year_to

        try:
            resp = self._session.post(
                f"{self.BASE_URL}/meta-search",
                json=payload, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            return self._parse_meta_response(data, query)
        except requests.RequestException:
            return []

    def semantic_search(self, query_text: str, top_k: int = 10,
                        mode: str = "balanced") -> List[Dict]:
        """语义块检索（用于深度 RAG 阅读）。

        Args:
            query_text: 自然语言查询
            top_k: 返回块数（最大 30）
            mode: 'fast' | 'balanced' | 'quality'

        Returns:
            [{"chunk_id": ..., "doc_id": ..., "title": ..., "chunk": ..., "score": ...}]
        """
        if not self.available:
            return []

        payload = {"query": query_text, "top_k": min(top_k, 30), "mode": mode}
        try:
            resp = self._session.post(
                f"{self.BASE_URL}/agentic-search",
                json=payload, timeout=30
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("hits", [])
        except requests.RequestException:
            return []

    def read_content(self, doc_id: str, offset: int = 0, limit: int = 4096) -> Optional[str]:
        """读取论文全文片段。"""
        if not self.available:
            return None
        try:
            resp = self._session.get(
                f"{self.BASE_URL}/content",
                params={"doc_id": doc_id, "offset": offset, "limit": min(limit, 16384)},
                timeout=30,
            )
            resp.raise_for_status()
            return resp.json().get("text", "")
        except requests.RequestException:
            return None

    def _parse_meta_response(self, data: Dict, query: SearchQuery) -> List[SearchResult]:
        """解析 /meta-search 返回的结构化元数据。"""
        results = []
        for item in data.get("results", []):
            # 提取作者列表
            authors = item.get("authors", [])
            if isinstance(authors, str):
                authors = [a.strip() for a in authors.split(",") if a.strip()]
            elif not isinstance(authors, list):
                authors = []

            # 计算相关度分数
            score = item.get("score", item.get("relevance", 0.0))
            if not score:
                score = item.get("citation_count", 0) / 1000.0  # fallback

            doi = item.get("doi", "")
            results.append(SearchResult(
                title=item.get("title", ""),
                authors=authors,
                abstract=item.get("abstract", item.get("description", "")),
                year=item.get("year") or item.get("publication_year"),
                doi=doi,
                url=item.get("url") or (f"https://doi.org/{doi}" if doi else ""),
                source="sciverse",
                score=float(score) if score else 0.5,
                citation_count=item.get("citation_count", 0),
                journal=item.get("journal") or item.get("publication_venue_name"),
                keywords=item.get("keywords", []),
                raw_metadata=item,
            ))
        return results


class SciBaseSearcher:
    """Sci-Base 数据集搜索器

    Sci-Base: HuggingFace opendatalab/Sci-Base
      - 2500万+篇论文，6000亿+ tokens
      - 覆盖含材料科学在内的10个学科
      - 支持本地索引或 HuggingFace Datasets 远程加载

    当本地无 Sci-Base 数据时，回退为关键词索引模式
    （通过 arXiv 获取论文后本地建立倒排索引）。
    """

    def __init__(self, cache_dir: Optional[str] = None):
        self._cache_dir = Path(cache_dir or "workspace/data/scibase_cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._index: Dict[str, List[str]] = {}  # term → [paper_ids]
        self._papers: Dict[str, Dict] = {}
        self._index_loaded = False

    @property
    def available(self) -> bool:
        """检查 Sci-Base 是否可用（需先下载数据集）"""
        index_file = self._cache_dir / "index.json"
        return index_file.exists()

    def search(self, query: SearchQuery, max_results: int = 50) -> List[SearchResult]:
        if not self.available:
            return []

        if not self._index_loaded:
            self._load_index()

        # 倒排索引检索
        query_terms = self._tokenize(query.text)
        if query.material:
            query_terms.extend(self._tokenize(query.material))

        paper_scores: Dict[str, float] = {}
        for term in query_terms:
            if term in self._index:
                idf = max(1.0, 1.0 / len(self._index[term]))
                for paper_id in self._index[term]:
                    paper_scores[paper_id] = paper_scores.get(paper_id, 0) + idf

        # Sort by score and convert
        sorted_papers = sorted(paper_scores.items(), key=lambda x: x[1], reverse=True)
        results = []
        for paper_id, score in sorted_papers[:max_results]:
            if paper_id in self._papers:
                paper = self._papers[paper_id]
                results.append(SearchResult(
                    title=paper.get("title", ""),
                    authors=paper.get("authors", []),
                    abstract=paper.get("abstract", ""),
                    year=paper.get("year"),
                    doi=paper.get("doi"),
                    source="scibase",
                    score=min(score / 10.0, 1.0),
                    keywords=paper.get("keywords", []),
                    raw_metadata=paper,
                ))
        return results

    def build_index_from_papers(self, papers: List[Dict]):
        """从论文列表构建本地倒排索引"""
        self._papers = {}
        self._index = {}
        for i, paper in enumerate(papers):
            pid = paper.get("doi") or paper.get("id") or f"paper_{i}"
            self._papers[pid] = paper
            text = f"{paper.get('title','')} {paper.get('abstract','')}"
            for term in set(self._tokenize(text)):
                if term not in self._index:
                    self._index[term] = []
                self._index[term].append(pid)
        self._save_index()
        self._index_loaded = True

    def _load_index(self):
        try:
            index_file = self._cache_dir / "index.json"
            papers_file = self._cache_dir / "papers.json"
            if index_file.exists():
                self._index = json.loads(index_file.read_text())
            if papers_file.exists():
                self._papers = json.loads(papers_file.read_text())
            self._index_loaded = True
        except Exception:
            self._index = {}
            self._papers = {}
            self._index_loaded = True

    def _save_index(self):
        try:
            (self._cache_dir / "index.json").write_text(json.dumps(self._index, ensure_ascii=False))
            (self._cache_dir / "papers.json").write_text(json.dumps(self._papers, ensure_ascii=False))
        except Exception:
            pass

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """简单分词 + 去停用词"""
        stopwords = {"the", "a", "an", "is", "are", "was", "were", "of", "in", "on",
                     "to", "for", "with", "and", "or", "by", "from", "at", "as", "be",
                     "this", "that", "it", "its", "we", "our", "their", "has", "have",
                     "been", "can", "may", "will", "would", "could", "should"}
        text = re.sub(r'[^\w\s-]', ' ', text.lower())
        tokens = []
        for token in text.split():
            token = token.strip()
            if len(token) > 2 and token not in stopwords:
                tokens.append(token)
        return tokens


# ═══════════════════════════════════════════════════════════════
# Unified Search Interface
# ═══════════════════════════════════════════════════════════════

class LiteratureSearcher:
    """统一文献检索入口。

    多源并发检索，自动去重合并，按相关度排序。
    搜索日志完整记录，构成可审计证据链。

    用法:
        searcher = LiteratureSearcher()
        results = searcher.search("MOF materials for CO2 capture", top_k=30)
        for r in results:
            print(r.to_markdown())
    """

    def __init__(self,
                 sciverse_api_key: Optional[str] = None,
                 cache_dir: Optional[str] = "workspace/data/literature_cache"):
        self._arxiv = ArxivSearcher(cache_dir=cache_dir)
        self._sciverse = SciverseSearcher(api_key=sciverse_api_key)
        self._scibase = SciBaseSearcher(cache_dir=cache_dir)
        self._cache_dir = Path(cache_dir or "workspace/data/literature_cache")
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._search_log: List[Dict] = []

    @property
    def available_sources(self) -> List[str]:
        sources = ["arxiv"]  # 始终可用
        if self._sciverse.available:
            sources.append("sciverse")
        if self._scibase.available:
            sources.append("scibase")
        return sources

    def search(self,
               query_text: str,
               top_k: int = 30,
               material: Optional[str] = None,
               property_name: Optional[str] = None,
               method: Optional[str] = None,
               year_from: Optional[int] = None,
               year_to: Optional[int] = None,
               sources: Optional[List[str]] = None,
               ) -> List[SearchResult]:
        """执行多源文献检索。

        Args:
            query_text: 自然语言检索查询
            top_k: 返回结果数
            material: 材料名称（可选，增强检索精度）
            property_name: 目标性质（可选）
            method: 方法名（可选）
            year_from: 起始年份
            year_to: 截止年份
            sources: 指定数据源列表，默认全部可用源

        Returns:
            去重合并后的 SearchResult 列表，按相关度降序排列
        """
        query = SearchQuery(
            text=query_text,
            material=material,
            property=property_name,
            method=method,
            year_from=year_from,
            year_to=year_to,
            top_k=top_k,
        )

        # Parse structured entities from query
        query.parsed_entities = self._parse_query_entities(query_text)

        sources = sources or self.available_sources
        t_start = time.time()

        # 并发多源检索
        all_results: List[SearchResult] = []
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {}
            if "arxiv" in sources:
                futures[executor.submit(self._arxiv.search, query, top_k)] = "arxiv"
            if "sciverse" in sources and self._sciverse.available:
                futures[executor.submit(self._sciverse.search, query, top_k)] = "sciverse"
            if "scibase" in sources and self._scibase.available:
                futures[executor.submit(self._scibase.search, query, top_k)] = "scibase"

            for future in as_completed(futures):
                source_name = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                except Exception as e:
                    # 单个源失败不阻断整体流程
                    pass

        # 去重（同 DOI 或高度相似标题）
        merged = self._deduplicate(all_results)
        merged.sort(key=lambda x: x.score, reverse=True)
        merged = merged[:top_k]

        # 记录搜索日志（审计证据链）
        self._log_search(query_text, sources, len(merged), time.time() - t_start)

        return merged

    def smart_search(self,
                     research_question: str,
                     top_k: int = 30) -> List[SearchResult]:
        """智能检索 — 自动解析研究问题中的实体并构造查询。

        Args:
            research_question: 研究问题描述
            top_k: 返回结果数

        Returns:
            搜索结果列表
        """
        entities = self._parse_query_entities(research_question)
        return self.search(
            query_text=research_question,
            top_k=top_k,
            material=entities.get("material"),
            property_name=entities.get("property"),
            method=entities.get("method"),
        )

    def search_by_paper(self,
                        title: str,
                        abstract: str = "",
                        top_k: int = 20) -> List[SearchResult]:
        """基于一篇论文检索相关工作。

        Args:
            title: 论文标题
            abstract: 论文摘要
            top_k: 返回结果数
        """
        # 从标题+摘要中提取关键实体作为查询
        combined = f"{title}. {abstract}"
        entities = self._parse_query_entities(combined)
        query_parts = [title[:100]]  # 用标题主干做精确匹配
        if entities.get("material"):
            query_parts.append(entities["material"])
        if entities.get("property"):
            query_parts.append(f"{entities['material']} {entities['property']}")
        return self.search(" ".join(query_parts), top_k=top_k,
                          material=entities.get("material"),
                          property_name=entities.get("property"))

    # ── 内部方法 ──

    def _deduplicate(self, results: List[SearchResult]) -> List[SearchResult]:
        """基于 DOI 和标题相似度的去重合并"""
        seen_dois: Dict[str, SearchResult] = {}
        seen_titles: Dict[str, SearchResult] = {}
        merged: List[SearchResult] = []

        for r in results:
            # DOI 精确匹配
            if r.doi and r.doi in seen_dois:
                existing = seen_dois[r.doi]
                existing.score = max(existing.score, r.score)
                if r.full_text_snippet and not existing.full_text_snippet:
                    existing.full_text_snippet = r.full_text_snippet
                continue

            # 标题相似度匹配（Jaccard on 3-grams）
            norm_title = self._normalize_title(r.title)
            dup_found = False
            for existing_title, existing in seen_titles.items():
                if self._title_similarity(norm_title, existing_title) > 0.8:
                    existing.score = max(existing.score, r.score)
                    dup_found = True
                    break

            if dup_found:
                continue

            seen_dois[r.doi] = r if r.doi else None
            seen_titles[norm_title] = r
            merged.append(r)

        return merged

    @staticmethod
    def _normalize_title(title: str) -> str:
        return re.sub(r'[^a-z0-9\s]', '', title.lower()).strip()

    @staticmethod
    def _title_similarity(t1: str, t2: str) -> float:
        """基于 3-gram Jaccard 的标题相似度"""
        def ngrams(s, n=3):
            return set(s[i:i+n] for i in range(len(s)-n+1))
        g1, g2 = ngrams(t1), ngrams(t2)
        if not g1 or not g2:
            return 0.0
        return len(g1 & g2) / len(g1 | g2)

    def _parse_query_entities(self, text: str) -> Dict[str, Any]:
        """从查询文本中解析材料/性质/方法实体。

        使用正则 + 关键词匹配进行初步 NER。更精确的实体识别
        由 LLM 驱动的 extractor 模块完成。
        """
        entities: Dict[str, Any] = {}

        # 常见材料模式（化学式 + 材料名）
        material_patterns = [
            r'\b[A-Z][a-z]?[0-9]*(?:[A-Z][a-z]?[0-9]*)+\b',  # 化学式如 MAPbI3, TiO2
            r'\b(?:perovskite|MOF|zeolite|graphene|carbon nanotube|'
            r'MXene|TMD|HEA|metal-organic framework|'
            r'covalent organic framework|COF|QD|quantum dot|'
            r'nanoparticle|nanowire|thin film|bulk|2D material)\b',
        ]
        materials = []
        for pat in material_patterns:
            materials.extend(re.findall(pat, text, re.IGNORECASE))
        if materials:
            entities["material"] = materials[0]  # 取第一个作为主材料

        # 常见性质模式
        property_patterns = [
            r'\b(?:band gap|conductivity|thermal conductivity|'
            r'electrical conductivity|mechanical strength|hardness|'
            r'catalytic activity|stability|efficiency|PCE|'
            r'power conversion efficiency|figure of merit|ZT|'
            r'carrier mobility|Seebeck coefficient|capacity|'
            r'energy density|power density|corrosion resistance|'
            r'adsorption capacity|selectivity|conversion rate|'
            r'yield|degradation|phase transition|magnetic)\b',
        ]
        properties = []
        for pat in property_patterns:
            properties.extend(re.findall(pat, text, re.IGNORECASE))
        if properties:
            entities["property"] = properties[0]

        # 常见方法模式
        method_patterns = [
            r'\b(?:DFT|density functional theory|molecular dynamics|MD|'
            r'Monte Carlo|MCTS|genetic algorithm|Bayesian optimization|'
            r'machine learning|deep learning|neural network|GNN|'
            r'graph neural network|transfer learning|active learning|'
            r'high-throughput|combinatorial|sol-gel|hydrothermal|'
            r'CVD|PVD|ALD|MBE|sputtering|electrodeposition|'
            r'XRD|TEM|SEM|AFM|XPS|NMR|Raman|FTIR)\b',
        ]
        methods = []
        for pat in method_patterns:
            methods.extend(re.findall(pat, text, re.IGNORECASE))
        if methods:
            entities["method"] = methods[0]

        return entities

    def _log_search(self, query: str, sources: List[str],
                    result_count: int, elapsed: float):
        """记录搜索日志（审计证据链）"""
        entry = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "query": query,
            "sources": sources,
            "result_count": result_count,
            "elapsed_seconds": round(elapsed, 2),
        }
        self._search_log.append(entry)

        # 持久化日志
        log_path = self._cache_dir / "search_log.jsonl"
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def get_search_log(self) -> List[Dict]:
        return self._search_log

    def export_results(self, results: List[SearchResult],
                       format: str = "markdown") -> str:
        """导出检索结果为 Markdown 或 JSON"""
        if format == "json":
            return json.dumps([r.to_dict() for r in results], ensure_ascii=False, indent=2)
        else:
            header = f"# Literature Search Results\n\n"
            header += f"**Query:** {self._search_log[-1]['query'] if self._search_log else 'N/A'}\n"
            header += f"**Sources:** {', '.join(self._search_log[-1]['sources']) if self._search_log else 'N/A'}\n"
            header += f"**Results:** {len(results)}\n\n---\n\n"
            return header + "\n".join(r.to_markdown() for r in results)


# ═══════════════════════════════════════════════════════════════
# arXiv XML Parser
# ═══════════════════════════════════════════════════════════════

def _parse_arxiv_xml(xml_text: str) -> List[SearchResult]:
    """解析 arXiv API 返回的 Atom XML"""
    ns = {
        'atom': 'http://www.w3.org/2005/Atom',
        'arxiv': 'http://arxiv.org/schemas/atom',
    }
    root = ET.fromstring(xml_text)
    results = []
    for entry in root.findall('atom:entry', ns):
        title = entry.find('atom:title', ns)
        title_text = title.text.strip().replace('\n', ' ') if title is not None and title.text else ""

        abstract = entry.find('atom:summary', ns)
        abstract_text = abstract.text.strip().replace('\n', ' ') if abstract is not None and abstract.text else ""

        authors = [a.find('atom:name', ns).text for a in entry.findall('atom:author', ns)
                   if a.find('atom:name', ns) is not None]

        doi = None
        for link in entry.findall('atom:link', ns):
            href = link.get('href', '')
            if 'doi.org' in href:
                doi = href.split('doi.org/')[-1]

        published = entry.find('atom:published', ns)
        year = int(published.text[:4]) if published is not None and published.text else None

        pdf_url = None
        for link in entry.findall('atom:link', ns):
            if link.get('title') == 'pdf':
                pdf_url = link.get('href')
                break

        journal = entry.find('arxiv:journal_ref', ns)
        journal_text = journal.text.strip() if journal is not None and journal.text else None

        results.append(SearchResult(
            title=title_text,
            authors=authors,
            abstract=abstract_text,
            year=year,
            doi=doi,
            url=f"https://arxiv.org/abs/{entry.find('atom:id', ns).text.split('/')[-1]}" if entry.find('atom:id', ns) is not None else None,
            source="arxiv",
            score=0.0,  # Will be set by caller
            journal=journal_text,
            pdf_url=pdf_url,
        ))
    return results


def _dict_to_result(d: Dict) -> SearchResult:
    return SearchResult(**{k: v for k, v in d.items() if k in SearchResult.__dataclass_fields__})


# ═══════════════════════════════════════════════════════════════
# Quick Test
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    searcher = LiteratureSearcher()
    print(f"Available sources: {searcher.available_sources}")

    results = searcher.search("perovskite solar cell stability", top_k=5)
    print(f"\nFound {len(results)} results:\n")
    for r in results:
        print(r.to_markdown())
        print("---")
