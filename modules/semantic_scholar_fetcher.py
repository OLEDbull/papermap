"""Semantic Scholar 论文获取模块

覆盖期刊、顶会、综述等正式发表论文，提供真实引用量、venue、论文类型等数据。
与 arXiv（预印本）互补，实现综合排序展示。
"""
import time
import logging
import urllib.request
import urllib.parse
import json
from datetime import datetime
from typing import List, Dict, Any, Optional

import config

logger = logging.getLogger(__name__)


class SemanticScholarFetcher:
    """从 Semantic Scholar 获取期刊/会议/综述论文"""

    def __init__(self) -> None:
        self.base_url: str = config.S2_API_URL
        self.max_results: int = config.S2_MAX_RESULTS
        self.api_key: str = config.S2_API_KEY

    def search_papers(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        if max_results is None:
            max_results = self.max_results

        # 字段：标题、摘要、作者、年份、venue、引用量、论文类型、外部ID、PDF
        fields = (
            'paperId,title,abstract,authors,year,venue,publicationVenue,'
            'citationCount,influentialCitationCount,publicationTypes,'
            'externalIds,openAccessPdf,fieldsOfStudy,tldr'
        )

        all_papers: List[Dict[str, Any]] = []
        seen_ids = set()

        # 两轮搜索：① 高引用经典论文（期刊/顶会） ② 最新论文
        searches = [
            {'sort': 'citationCount:desc', 'limit': min(60, max_results), 'label': '高引用经典'},
            {'sort': 'publicationDate:desc', 'limit': min(60, max_results), 'label': '最新发表'},
        ]

        for s in searches:
            if len(all_papers) >= max_results:
                break
            remaining = max_results - len(all_papers)
            limit = min(s['limit'], remaining)
            papers = self._fetch_batch(query, fields, limit=limit, sort=s['sort'])
            for p in papers:
                pid = p.get('id', '')
                if pid and pid not in seen_ids:
                    seen_ids.add(pid)
                    all_papers.append(p)
            time.sleep(1.5)  # 无key时速率限制：100请求/5分钟

        all_papers.sort(key=lambda x: x.get('published', ''), reverse=False)
        logger.info(f"Semantic Scholar fetched {len(all_papers)} papers for '{query}'")
        return all_papers

    def _fetch_batch(self, query: str, fields: str, limit: int = 50,
                     sort: str = 'citationCount:desc',
                     year: Optional[str] = None) -> List[Dict[str, Any]]:
        params = {
            'query': query,
            'fields': fields,
            'limit': min(limit, 100),
            'sort': sort,
        }
        if year:
            params['year'] = year

        url = f"{self.base_url}/paper/search?{urllib.parse.urlencode(params)}"

        headers = {'User-Agent': 'PaperKnowledgeGraph/1.0'}
        if self.api_key:
            headers['x-api-key'] = self.api_key

        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=15) as response:
                    data = json.loads(response.read().decode('utf-8'))
                raw_papers = data.get('data', [])
                return [self._parse_paper(p) for p in raw_papers]
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"S2 rate limited, waiting {wait}s...")
                    time.sleep(wait)
                else:
                    logger.error(f"S2 HTTP {e.code}: {e.reason}")
                    if attempt < 2:
                        time.sleep(3)
            except Exception as e:
                logger.error(f"S2 fetch error (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep(3)
        return []

    def _parse_paper(self, raw: Dict[str, Any]) -> Dict[str, Any]:
        paper_id = raw.get('paperId', '')

        # 作者
        authors = []
        for a in raw.get('authors', []) or []:
            name = a.get('name', '')
            if name:
                authors.append(name)

        # 年份 → ISO 日期
        year = raw.get('year')
        published = ''
        if year:
            try:
                published = datetime(int(year), 1, 1).isoformat()
            except (ValueError, TypeError):
                published = ''

        # venue 信息
        venue = raw.get('venue', '') or ''
        pub_venue = raw.get('publicationVenue') or {}
        venue_name = venue or pub_venue.get('name', '')
        venue_type = pub_venue.get('type', '')  # conference / journal

        # 论文类型：JournalArticle / Conference / Review
        pub_types = raw.get('publicationTypes') or []
        paper_type = self._classify_type(pub_types, venue_type)

        # 真实引用量
        citation_count = raw.get('citationCount', 0) or 0
        influential_citations = raw.get('influentialCitationCount', 0) or 0

        # 摘要：优先 abstract，其次 tldr
        abstract = raw.get('abstract', '') or ''
        if not abstract:
            tldr = raw.get('tldr')
            if tldr and isinstance(tldr, dict):
                abstract = tldr.get('text', '')

        # 外部ID
        external_ids = raw.get('externalIds') or {}
        doi = external_ids.get('DOI', '')
        arxiv_id = external_ids.get('ArXiv', '')

        # PDF
        pdf_url = ''
        oa_pdf = raw.get('openAccessPdf')
        if oa_pdf and isinstance(oa_pdf, dict):
            pdf_url = oa_pdf.get('url', '')

        # 研究领域
        fields_of_study = raw.get('fieldsOfStudy') or []
        categories = [f for f in fields_of_study if f]

        # 综一 ID：优先 DOI，其次 ArXiv，最后 paperId
        unified_id = doi or arxiv_id or paper_id
        if doi:
            unified_id = f"doi-{doi}"
        elif arxiv_id:
            unified_id = arxiv_id
        else:
            unified_id = f"s2-{paper_id}"

        return {
            'id': unified_id,
            'title': raw.get('title', '').strip(),
            'authors': authors,
            'summary': abstract.replace('\n', ' ').strip(),
            'published': published,
            'year': year,
            'categories': categories,
            'pdf_url': pdf_url,
            'abs_url': f"https://www.semanticscholar.org/paper/{paper_id}" if paper_id else '',
            'doi': doi,
            'arxiv_id': arxiv_id,
            'venue': venue_name,
            'venue_type': venue_type,
            'paper_type': paper_type,  # journal / conference / review / preprint
            'citation_count': citation_count,  # 真实引用量
            'influential_citations': influential_citations,
            'source': 'semantic_scholar',
        }

    def _classify_type(self, pub_types: List[str], venue_type: str) -> str:
        """根据 publicationTypes 和 venue type 分类论文类型"""
        pub_types_lower = [t.lower() for t in pub_types]

        if any('review' in t for t in pub_types_lower):
            return 'review'
        if any('journal' in t for t in pub_types_lower) or venue_type == 'journal':
            return 'journal'
        if any('conference' in t for t in pub_types_lower) or venue_type == 'conference':
            return 'conference'
        if pub_types_lower:
            return pub_types_lower[0]
        return 'preprint'
