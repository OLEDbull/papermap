import json
import os
import logging
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict, List, Optional, Any

import config
from modules.arxiv_fetcher import ArxivFetcher
from modules.semantic_scholar_fetcher import SemanticScholarFetcher
from modules.ai_summarizer import AISummarizer
from modules.relation_analyzer import RelationAnalyzer

logger = logging.getLogger(__name__)


class PaperManager:
    def __init__(self) -> None:
        self.fetcher: ArxivFetcher = ArxivFetcher()
        self.s2_fetcher: SemanticScholarFetcher = SemanticScholarFetcher()
        self.summarizer: AISummarizer = AISummarizer()
        self.analyzer: RelationAnalyzer = RelationAnalyzer()
        self.data_dir: str = config.DATA_DIR
        self.papers_dir: str = config.PAPERS_DIR
        self._analysis_tasks: Dict[str, bool] = {}
        self._analysis_progress: Dict[str, Dict[str, Any]] = {}
        self._translation_cache: Dict[str, str] = {}

    def _get_translated_query(self, query: str) -> str:
        """获取翻译后的查询词，带缓存"""
        cache_key = query.strip().lower()
        if cache_key in self._translation_cache:
            logger.info(f"Translation cache hit for: {query}")
            return self._translation_cache[cache_key]
        translated = self.summarizer.translate_keyword(query)
        self._translation_cache[cache_key] = translated
        return translated

    def search_fast(self, query: str, max_results: Optional[int] = None) -> Dict[str, Any]:
        """快速搜索：只获取论文列表并用启发式规则快速评分，立即返回。
        用户看到结果的时间从几十秒缩短到几秒。
        """
        try:
            logger.info(f"Fast search for query: {query}")

            translated_query = self._get_translated_query(query)
            logger.info(f"Translated query: {translated_query}")

            papers = self._fetch_multi_source(translated_query, max_results)
            if not papers:
                logger.warning(f"No papers found, using demo data for query: {translated_query}")
                papers = self._get_demo_papers(translated_query)

            papers = sorted(papers, key=lambda x: x.get('published', ''), reverse=False)
            logger.info(f"Found {len(papers)} papers (fast mode)")

            for paper in papers:
                ai_summary = self.summarizer._mock_summarize(paper)
                paper['ai_summary'] = ai_summary
                paper['novelty'] = ai_summary.get('novelty', 50)
                paper['impact_factor'] = ai_summary.get('impact_factor', 3.0)
                paper['is_breakthrough'] = ai_summary.get('is_breakthrough', False)
                real_citations = paper.get('citation_count', 0)
                if real_citations and real_citations > 0:
                    paper['estimated_citations'] = real_citations
                    paper['citation_source'] = 'semantic_scholar'
                else:
                    raw_citations = ai_summary.get('estimated_citations', 100)
                    paper['estimated_citations'] = self._adjust_citations(
                        raw_citations, paper.get('published', ''),
                        paper['is_breakthrough'], paper['impact_factor']
                    )
                    paper['citation_source'] = 'estimated'

            graph_data = self.analyzer.analyze_relations(papers)
            stats = self.analyzer.get_method_statistics(papers)
            timeline = self._build_timeline(papers)
            top_papers = self._build_top_papers(papers)
            field_overview = self._build_field_overview(papers)
            tech_evolution = self._build_tech_evolution(papers)
            researcher_graph = self._build_researcher_graph(papers)
            reading_path = self._build_reading_path(papers)
            research_gaps = self._build_research_gaps(papers)

            result = {
                'query': query,
                'translated_query': translated_query,
                'total': len(papers),
                'papers': papers,
                'graph': graph_data,
                'statistics': stats,
                'timeline': timeline,
                'top_papers': top_papers,
                'field_overview': field_overview,
                'tech_evolution': tech_evolution,
                'researcher_graph': researcher_graph,
                'reading_path': reading_path,
                'research_gaps': research_gaps,
                'analysis_phase': 'fast'
            }

            self._save_search(query, result)
            logger.info(f"Fast search completed for query: {query}")
            return result

        except Exception as e:
            logger.error(f"Fast search error: {e}", exc_info=True)
            raise

    def start_deep_analysis(self, query: str, top_n: int = 30) -> bool:
        """启动后台深度分析，对Top N篇论文进行AI深度分析。
        非阻塞：立即返回，分析在后台线程中进行。
        """
        import threading

        if query in self._analysis_tasks and self._analysis_tasks[query]:
            logger.info(f"Deep analysis already running for query: {query}")
            return False

        self._analysis_tasks[query] = True
        thread = threading.Thread(target=self._do_deep_analysis, args=(query, top_n), daemon=True)
        thread.start()
        logger.info(f"Started deep analysis thread for query: {query} (top {top_n})")
        return True

    def _do_deep_analysis(self, query: str, top_n: int = 30) -> None:
        """执行深度分析的后台线程函数。
        渐进式：每分析一小批（5篇）就保存一次，前端可以更早看到更新。
        """
        try:
            logger.info(f"Deep analysis started for query: {query}, top {top_n}")

            cached = self.load_search(query)
            if not cached:
                logger.warning(f"No cached result for deep analysis: {query}")
                return

            papers = cached.get('papers', [])
            if not papers:
                return

            sorted_papers = sorted(papers, key=lambda x: x.get('estimated_citations', 0), reverse=True)
            top_papers = sorted_papers[:top_n]
            total = len(top_papers)

            self._analysis_progress[query] = {
                'total': total,
                'completed': 0,
                'current_batch': 0
            }

            logger.info(f"Deep analyzing {total} papers (progressive mode)...")

            small_batch_size = 5
            paper_dict = {p['id']: p for p in papers}

            for batch_start in range(0, total, small_batch_size):
                batch_end = min(batch_start + small_batch_size, total)
                batch = top_papers[batch_start:batch_end]
                batch_size = len(batch)

                logger.info(f"Analyzing batch {batch_start//small_batch_size + 1}: papers {batch_start + 1}-{batch_end}/{total}")

                batch_results = self.summarizer.summarize_papers_batch(batch, batch_size=batch_size)

                for pid, ai_summary in batch_results.items():
                    if pid in paper_dict:
                        paper = paper_dict[pid]
                        paper['ai_summary'] = ai_summary
                        paper['novelty'] = ai_summary.get('novelty', paper.get('novelty', 50))
                        paper['impact_factor'] = ai_summary.get('impact_factor', paper.get('impact_factor', 3.0))
                        paper['is_breakthrough'] = ai_summary.get('is_breakthrough', paper.get('is_breakthrough', False))
                        real_citations = paper.get('citation_count', 0)
                        if not real_citations or real_citations == 0:
                            raw_citations = ai_summary.get('estimated_citations', paper.get('estimated_citations', 100))
                            paper['estimated_citations'] = self._adjust_citations(
                                raw_citations, paper.get('published', ''),
                                paper['is_breakthrough'], paper['impact_factor']
                            )
                            paper['citation_source'] = 'ai_estimated'

                self._analysis_progress[query]['completed'] = batch_end

                cached['papers'] = papers
                cached['timeline'] = self._build_timeline(papers)
                cached['top_papers'] = self._build_top_papers(papers)
                cached['analysis_phase'] = 'analyzing'

                self._save_search(query, cached)
                logger.info(f"Batch {batch_start//small_batch_size + 1} done, saved progress ({batch_end}/{total})")

            cached['analysis_phase'] = 'deep'
            self._save_search(query, cached)

            if query in self._analysis_progress:
                self._analysis_progress[query]['completed'] = total

            logger.info(f"Deep analysis completed for query: {query}")

        except Exception as e:
            logger.error(f"Deep analysis error: {e}", exc_info=True)
        finally:
            self._analysis_tasks[query] = False

    def is_deep_analysis_done(self, query: str) -> bool:
        """检查深度分析是否完成。"""
        cached = self.load_search(query)
        if cached and cached.get('analysis_phase') == 'deep':
            return True
        return False

    def get_analysis_status(self, query: str) -> Dict[str, Any]:
        """获取分析状态，包含详细进度。"""
        cached = self.load_search(query)
        if not cached:
            return {'status': 'not_found'}

        phase = cached.get('analysis_phase')
        if phase is None:
            phase = 'deep'
        is_running = self._analysis_tasks.get(query, False)

        progress = self._analysis_progress.get(query, {})
        total = progress.get('total', 0)
        completed = progress.get('completed', 0)
        percent = 0
        if total > 0:
            percent = int((completed / total) * 100)

        if phase == 'deep':
            status = 'completed'
            percent = 100
        elif phase == 'analyzing' or is_running:
            status = 'running'
        else:
            status = 'fast'

        return {
            'status': status,
            'phase': phase,
            'total': cached.get('total', 0),
            'analyzing_total': total,
            'analyzing_completed': completed,
            'percent': percent
        }

    def search_and_analyze(self, query: str, max_results: Optional[int] = None) -> Dict[str, Any]:
        try:
            logger.info(f"Starting search and analysis for query: {query}")

            translated_query = self._get_translated_query(query)
            logger.info(f"Translated query: {translated_query}")

            # 多来源聚合：Semantic Scholar（期刊/顶会/综述）+ arXiv（预印本）
            papers = self._fetch_multi_source(translated_query, max_results)
            if not papers:
                logger.warning(f"No papers found from any source, using demo data for query: {translated_query}")
                papers = self._get_demo_papers(translated_query)

            papers = sorted(papers, key=lambda x: x.get('published', ''), reverse=False)
            logger.info(f"Found and sorted {len(papers)} papers (after dedup)")

            logger.info(f"Generating summaries and impact scores for {len(papers)} papers (batch mode)...")
            batch_results = self.summarizer.summarize_papers_batch(papers, batch_size=25)

            for paper in papers:
                ai_summary = batch_results.get(paper['id'], {})
                paper['ai_summary'] = ai_summary
                paper['novelty'] = ai_summary.get('novelty', 50)
                paper['impact_factor'] = ai_summary.get('impact_factor', 3.0)
                paper['is_breakthrough'] = ai_summary.get('is_breakthrough', False)
                # 引用量：优先使用 Semantic Scholar 真实数据，否则用 AI 估算 + 后处理
                real_citations = paper.get('citation_count', 0)
                if real_citations and real_citations > 0:
                    paper['estimated_citations'] = real_citations
                    paper['citation_source'] = 'semantic_scholar'
                else:
                    raw_citations = ai_summary.get('estimated_citations', 100)
                    paper['estimated_citations'] = self._adjust_citations(
                        raw_citations, paper.get('published', ''),
                        paper['is_breakthrough'], paper['impact_factor']
                    )
                    paper['citation_source'] = 'estimated'

            graph_data = self.analyzer.analyze_relations(papers)
            stats = self.analyzer.get_method_statistics(papers)
            timeline = self._build_timeline(papers)
            top_papers = self._build_top_papers(papers)
            field_overview = self._build_field_overview(papers)
            tech_evolution = self._build_tech_evolution(papers)
            researcher_graph = self._build_researcher_graph(papers)
            reading_path = self._build_reading_path(papers)
            research_gaps = self._build_research_gaps(papers)

            result = {
                'query': query,
                'translated_query': translated_query,
                'total': len(papers),
                'papers': papers,
                'graph': graph_data,
                'statistics': stats,
                'timeline': timeline,
                'top_papers': top_papers,
                'field_overview': field_overview,
                'tech_evolution': tech_evolution,
                'researcher_graph': researcher_graph,
                'reading_path': reading_path,
                'research_gaps': research_gaps
            }

            self._save_search(query, result)
            logger.info(f"Search and analysis completed successfully")
            return result

        except Exception as e:
            logger.error(f"Search and analysis error: {e}", exc_info=True)
            raise

    def _fetch_multi_source(self, query: str, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        """并行聚合 Semantic Scholar 和 arXiv 两个来源，去重后返回"""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        all_papers: List[Dict[str, Any]] = []
        results: Dict[str, List[Dict[str, Any]]] = {}

        def _fetch_s2() -> List[Dict[str, Any]]:
            logger.info(f"[S2] Starting fetch: {query}")
            papers = self.s2_fetcher.search_papers(query, max_results=max_results)
            for p in papers:
                p.setdefault('paper_type', 'preprint')
                p.setdefault('source', 'semantic_scholar')
            logger.info(f"[S2] Got {len(papers)} papers")
            return papers

        def _fetch_arxiv() -> List[Dict[str, Any]]:
            logger.info(f"[arXiv] Starting fetch: {query}")
            papers = self.fetcher.search_papers(query, max_results=max_results)
            for p in papers:
                p.setdefault('paper_type', 'preprint')
                p.setdefault('source', 'arxiv')
                p.setdefault('venue', '')
                p.setdefault('citation_count', 0)
            logger.info(f"[arXiv] Got {len(papers)} papers")
            return papers

        # 并行获取两个数据源
        with ThreadPoolExecutor(max_workers=2) as executor:
            future_map = {
                executor.submit(_fetch_s2): 'semantic_scholar',
                executor.submit(_fetch_arxiv): 'arxiv',
            }
            for future in as_completed(future_map):
                source = future_map[future]
                try:
                    results[source] = future.result()
                except Exception as e:
                    logger.error(f"{source} fetch failed: {e}", exc_info=True)
                    results[source] = []

        all_papers.extend(results.get('semantic_scholar', []))
        all_papers.extend(results.get('arxiv', []))

        # 去重（按归一化标题）
        deduped = self._dedup_papers(all_papers)

        # 如果超过 max_results，按引用量/时间综合排序后截取
        if max_results and len(deduped) > max_results:
            deduped.sort(key=lambda p: (
                p.get('citation_count', 0),
                p.get('published', ''),
            ), reverse=True)
            deduped = deduped[:max_results]

        return deduped

    def _dedup_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """多维度去重：归一化标题 + DOI + arXiv ID + 模糊标题匹配，优先保留有真实引用量/venue 的来源"""
        import re
        from difflib import SequenceMatcher

        def _norm_title(title: str) -> str:
            t = re.sub(r'[^a-z0-9\s]', '', title.lower())
            t = re.sub(r'\s+', ' ', t).strip()
            return t

        def _get_doi(p: Dict[str, Any]) -> str:
            # 从 doi 字段或 externalIds 中获取 DOI
            doi = p.get('doi', '')
            if not doi:
                external_ids = p.get('externalIds') or {}
                doi = external_ids.get('DOI', '') or external_ids.get('doi', '')
            return (doi or '').strip().lower()

        def _get_arxiv_id(p: Dict[str, Any]) -> str:
            # 从 arxiv_id 字段或 externalIds 中获取 arXiv ID
            arxiv_id = p.get('arxiv_id', '') or p.get('arxivId', '')
            if not arxiv_id:
                external_ids = p.get('externalIds') or {}
                arxiv_id = external_ids.get('ArXiv', '') or external_ids.get('arxiv', '')
            return (arxiv_id or '').strip().lower()

        def _title_similarity(t1: str, t2: str) -> float:
            """计算两个归一化标题的相似度（0-1）"""
            if not t1 or not t2:
                return 0.0
            return SequenceMatcher(None, t1, t2).ratio()

        def _merge_into_existing(existing: Dict[str, Any], new: Dict[str, Any]) -> None:
            """将 new 合并到 existing（就地修改 existing，保持对象引用不变）
            优先级：有真实引用量 > 有venue > arxiv
            """
            new_score = self._info_score(new)
            old_score = self._info_score(existing)
            if new_score > old_score:
                # new 信息更丰富：以 new 为主，但补充 existing 中 new 缺失的字段
                merged = {**existing, **new}
                for k, v in existing.items():
                    if not merged.get(k):
                        merged[k] = v
                existing.clear()
                existing.update(merged)
            else:
                # existing 更丰富：仅补充 existing 中缺失的字段
                for k, v in new.items():
                    if not existing.get(k) and v:
                        existing[k] = v

        # 多维索引：均指向 result 中同一字典对象，便于快速查找重复
        result: List[Dict[str, Any]] = []
        norm_title_index: Dict[str, Dict[str, Any]] = {}  # 归一化标题 -> 论文
        doi_index: Dict[str, Dict[str, Any]] = {}          # DOI -> 论文
        arxiv_index: Dict[str, Dict[str, Any]] = {}        # arXiv ID -> 论文

        for p in papers:
            norm_title = _norm_title(p.get('title', ''))
            doi = _get_doi(p)
            arxiv_id = _get_arxiv_id(p)

            existing: Optional[Dict[str, Any]] = None

            # 1. 精确匹配：归一化标题
            if norm_title and norm_title in norm_title_index:
                existing = norm_title_index[norm_title]

            # 2. DOI 匹配：相同 DOI 视为重复
            if existing is None and doi and doi in doi_index:
                existing = doi_index[doi]

            # 3. arXiv ID 匹配：相同 arXiv ID 视为重复
            if existing is None and arxiv_id and arxiv_id in arxiv_index:
                existing = arxiv_index[arxiv_id]

            # 4. 模糊标题匹配：SequenceMatcher 相似度 > 0.92 视为重复
            if existing is None and norm_title:
                for seen_paper in result:
                    seen_norm = _norm_title(seen_paper.get('title', ''))
                    if seen_norm and _title_similarity(norm_title, seen_norm) > 0.92:
                        existing = seen_paper
                        break

            if existing is None:
                # 新论文：加入结果并建立索引
                result.append(p)
                if norm_title:
                    norm_title_index[norm_title] = p
                if doi:
                    doi_index[doi] = p
                if arxiv_id:
                    arxiv_index[arxiv_id] = p
            else:
                # 重复论文：合并字段（就地修改 existing，所有索引仍指向同一对象）
                _merge_into_existing(existing, p)
                # 补充索引：把 p 的 DOI/arxiv_id/标题 也指向 existing
                if norm_title:
                    norm_title_index[norm_title] = existing
                if doi:
                    doi_index[doi] = existing
                if arxiv_id:
                    arxiv_index[arxiv_id] = existing

        return result

    @staticmethod
    def _info_score(p: Dict[str, Any]) -> int:
        """评估论文记录的信息丰富度，用于去重时选择保留哪个"""
        score = 0
        if p.get('citation_count', 0) > 0:
            score += 100
        if p.get('venue'):
            score += 20
        if p.get('doi'):
            score += 10
        if p.get('summary'):
            score += 5
        if p.get('source') == 'semantic_scholar':
            score += 30
        return score

    def _adjust_citations(self, raw: int, published: str, is_breakthrough: bool, impact_factor: float) -> int:
        """对引用量做后处理：时间累积放大 + 突破性加权 + 影响力因子加权 + 下限保护"""
        try:
            pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
        except Exception:
            try:
                pub_date = datetime.strptime(published[:10], '%Y-%m-%d')
            except Exception:
                pub_date = datetime.now()

        years_since = max(0.3, (datetime.now() - pub_date).days / 365.0)

        # 1. 下限保护：高质量论文引用量至少 100
        citations = max(raw, 80 if impact_factor >= 5 else 30)

        # 2. 突破性加权：突破性论文引用量 ×2
        if is_breakthrough:
            citations = int(citations * 2.0)

        # 3. 影响力因子加权：影响力越高，引用量越高
        impact_multiplier = 1.0 + max(0, impact_factor - 3.0) * 0.25
        citations = int(citations * impact_multiplier)

        # 4. 时间累积放大：老论文引用量应更高
        # 1年: ×1.3, 2年: ×1.8, 3年: ×2.3, 5年: ×3.3, 8年: ×4.8
        time_multiplier = 1.0 + 0.5 * years_since + 0.1 * max(0, years_since - 2) ** 2
        citations = int(citations * time_multiplier)

        return max(30, min(citations, 50000))

    def _build_timeline(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not papers:
            return {'periods': []}

        periods = self._group_papers_by_period(papers)

        # 批量时段 AI 总结（一次 API 调用完成所有时段）
        batch_inputs = []
        for i, period in enumerate(periods):
            batch_inputs.append({
                'index': i,
                'label': period['label'],
                'papers': period['papers']
            })
        batch_summaries = self.summarizer.summarize_periods_batch(batch_inputs)
        summary_map = {s['index']: s for s in batch_summaries}

        timeline_periods = []
        for i, period in enumerate(periods):
            period_papers = period['papers']
            period_label = period['label']
            ai_summary = summary_map.get(i, {})

            sorted_papers = sorted(
                period_papers,
                key=lambda p: (
                    p.get('impact_factor', 0),
                    p.get('estimated_citations', 0),
                    p.get('novelty', 0)
                ),
                reverse=True
            )

            top_n = 3
            top_papers = sorted_papers[:top_n]
            more_papers = sorted_papers[top_n:]

            timeline_periods.append({
                'label': period_label,
                'start': period['start'],
                'end': period['end'],
                'paper_count': len(period_papers),
                'top_papers': [{
                    'id': p['id'],
                    'title': p['title'],
                    'authors': p.get('authors', []),
                    'published': p.get('published', ''),
                    'summary': p.get('summary', '')[:200],
                    'novelty': p.get('novelty', 50),
                    'estimated_citations': p.get('estimated_citations', 20),
                    'impact_factor': p.get('impact_factor', 3.0),
                    'is_breakthrough': p.get('is_breakthrough', False),
                    'paper_type': p.get('paper_type', 'preprint'),
                    'venue': p.get('venue', ''),
                    'citation_source': p.get('citation_source', 'estimated')
                } for p in top_papers],
                'more_papers': [{
                    'id': p['id'],
                    'title': p['title'],
                    'authors': p.get('authors', []),
                    'published': p.get('published', ''),
                    'summary': p.get('summary', '')[:200],
                    'novelty': p.get('novelty', 50),
                    'estimated_citations': p.get('estimated_citations', 20),
                    'impact_factor': p.get('impact_factor', 3.0),
                    'is_breakthrough': p.get('is_breakthrough', False),
                    'paper_type': p.get('paper_type', 'preprint'),
                    'venue': p.get('venue', ''),
                    'citation_source': p.get('citation_source', 'estimated')
                } for p in more_papers],
                'paper_ids': [p['id'] for p in sorted_papers],
                'ai_summary': ai_summary.get('summary', ''),
                'breakthroughs': ai_summary.get('breakthroughs', []),
                'trends': ai_summary.get('trends', []),
                'key_methods': ai_summary.get('key_methods', []),
                'hot_topics': ai_summary.get('hot_topics', [])
            })

        return {'periods': timeline_periods}

    def _group_papers_by_period(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not papers:
            return []

        dates = []
        for p in papers:
            try:
                dt = datetime.fromisoformat(p['published'].replace('Z', '+00:00'))
                dates.append(dt)
            except Exception:
                try:
                    dt = datetime.strptime(p['published'][:10], '%Y-%m-%d')
                    dates.append(dt)
                except Exception:
                    dates.append(datetime.now())

        min_date = min(dates)
        max_date = max(dates)
        span_days = (max_date - min_date).days

        if span_days <= 90:
            granularity = 'month'
        elif span_days <= 730:
            granularity = 'quarter'
        else:
            granularity = 'year'

        def _group(gran):
            groups = defaultdict(list)
            for paper, dt in zip(papers, dates):
                if gran == 'month':
                    key = dt.strftime('%Y-%m')
                    label = f'{dt.year}年{dt.month}月'
                    start = dt.replace(day=1)
                    if dt.month == 12:
                        end = dt.replace(day=31)
                    else:
                        next_month = dt.replace(month=dt.month + 1, day=1) - timedelta(days=1)
                        end = next_month
                elif gran == 'quarter':
                    q = (dt.month - 1) // 3 + 1
                    key = f'{dt.year}-Q{q}'
                    label = f'{dt.year}年Q{q}'
                    start = datetime(dt.year, (q - 1) * 3 + 1, 1)
                    end = datetime(dt.year + (1 if q == 4 else 0),
                                  (q % 4) * 3 + 1 if q < 4 else 1, 1) - timedelta(days=1)
                else:
                    key = str(dt.year)
                    label = f'{dt.year}年'
                    start = datetime(dt.year, 1, 1)
                    end = datetime(dt.year, 12, 31)

                groups[key].append({
                    'paper': paper,
                    'label': label,
                    'start': start.isoformat(),
                    'end': end.isoformat()
                })

            result = []
            for key in sorted(groups.keys()):
                items = groups[key]
                result.append({
                    'label': items[0]['label'],
                    'start': items[0]['start'],
                    'end': items[0]['end'],
                    'papers': [item['paper'] for item in items]
                })
            return result

        result = _group(granularity)

        if len(result) < 4 and granularity == 'year':
            result = _group('quarter')
        if len(result) < 4 and granularity != 'month':
            result = _group('month')

        if len(result) > 10 and granularity == 'month':
            result = _group('quarter')
        if len(result) > 10 and granularity == 'quarter':
            result = _group('year')

        return result

    def get_paper_summary(self, paper_id: str, paper_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        try:
            if paper_data is None:
                paper = self.fetcher.get_paper_by_id(paper_id)
            else:
                paper = paper_data
            if not paper:
                logger.warning(f"Paper not found: {paper_id}")
                return None
            summary = self.summarizer.summarize_paper(paper)
            return {'paper': paper, 'summary': summary}
        except Exception as e:
            logger.error(f"Error getting paper summary for {paper_id}: {e}", exc_info=True)
            return None

    def get_design_doc(self, paper_id: str, paper_data: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        try:
            if paper_data is None:
                paper = self.fetcher.get_paper_by_id(paper_id)
            else:
                paper = paper_data
            if not paper:
                logger.warning(f"Paper not found: {paper_id}")
                return None
            design_doc = self.summarizer.generate_design_doc(paper)
            return {'paper': paper, 'design_doc': design_doc}
        except Exception as e:
            logger.error(f"Error getting design doc for {paper_id}: {e}", exc_info=True)
            return None

    def download_paper_pdf(self, paper_id: str) -> Optional[str]:
        try:
            save_path = os.path.join(self.papers_dir, f"{paper_id}.pdf")
            if os.path.exists(save_path):
                return save_path
            success = self.fetcher.download_pdf(paper_id, save_path)
            return save_path if success else None
        except Exception as e:
            logger.error(f"Error downloading paper {paper_id}: {e}", exc_info=True)
            return None

    def answer_question(self, paper_id: str, question: str, paper_data: Optional[Dict[str, Any]] = None,
                        history: Optional[List[Dict[str, str]]] = None) -> Optional[Dict[str, Any]]:
        try:
            if paper_data is None:
                paper = self.fetcher.get_paper_by_id(paper_id)
            else:
                paper = paper_data
            if not paper:
                logger.warning(f"Paper not found for Q&A: {paper_id}")
                return None
            result = self.summarizer.answer_question(paper, question, history)
            return result
        except Exception as e:
            logger.error(f"Error answering question for paper {paper_id}: {e}", exc_info=True)
            return None

    def compare_papers(self, paper_ids: List[str], papers_data: Optional[List[Dict[str, Any]]] = None) -> Optional[Dict[str, Any]]:
        try:
            papers = []
            if papers_data:
                papers = papers_data
            else:
                for pid in paper_ids:
                    p = self.fetcher.get_paper_by_id(pid)
                    if p:
                        papers.append(p)

            if len(papers) < 2:
                return None

            if len(papers) > 2:
                papers = papers[:2]

            if self.summarizer.provider == 'deepseek' and self.summarizer.api_key:
                paper1_info = f"标题: {papers[0].get('title', '')}\n摘要: {papers[0].get('summary', '')[:500]}\n年份: {papers[0].get('published', '')[:4]}\n引用: {papers[0].get('citation_count', 0)}"
                paper2_info = f"标题: {papers[1].get('title', '')}\n摘要: {papers[1].get('summary', '')[:500]}\n年份: {papers[1].get('published', '')[:4]}\n引用: {papers[1].get('citation_count', 0)}"

                prompt = f"""请对比以下两篇论文，从学术研究角度进行深度分析。

论文1：
{paper1_info}

论文2：
{paper2_info}

请返回JSON格式：
{{
    "similarities": ["相似点1", "相似点2", "相似点3"],
    "differences": [
        {{"aspect": "研究目标", "paper1": "论文1的特点", "paper2": "论文2的特点"}},
        {{"aspect": "核心方法", "paper1": "论文1的方法", "paper2": "论文2的方法"}},
        {{"aspect": "实验结果", "paper1": "论文1的结果", "paper2": "论文2的结果"}},
        {{"aspect": "创新性", "paper1": "论文1的创新", "paper2": "论文2的创新"}}
    ],
    "verdict": "综合评价（哪篇论文更具影响力/创新性，适用场景分别是什么）",
    "use_cases": {{
        "paper1_better_for": ["场景1", "场景2"],
        "paper2_better_for": ["场景1", "场景2"]
    }}
}}

要求：
1. 分析要专业、客观，基于论文内容
2. 对比维度要全面：目标、方法、结果、创新、应用场景
3. 用中文回答
4. 每篇论文的描述控制在50字以内，简洁明了
"""

                result = self.summarizer._call_deepseek(prompt, temperature=0.4, max_tokens=1000)
                if result:
                    return {
                        'papers': [
                            {
                                'id': papers[0].get('id', ''),
                                'title': papers[0].get('title', ''),
                                'authors': papers[0].get('authors', []),
                                'published': papers[0].get('published', ''),
                                'citations': papers[0].get('citation_count', papers[0].get('estimated_citations', 0)),
                                'impact_factor': papers[0].get('impact_factor', 0),
                                'novelty': papers[0].get('novelty', 0),
                                'venue': papers[0].get('venue', ''),
                                'paper_type': papers[0].get('paper_type', 'preprint')
                            },
                            {
                                'id': papers[1].get('id', ''),
                                'title': papers[1].get('title', ''),
                                'authors': papers[1].get('authors', []),
                                'published': papers[1].get('published', ''),
                                'citations': papers[1].get('citation_count', papers[1].get('estimated_citations', 0)),
                                'impact_factor': papers[1].get('impact_factor', 0),
                                'novelty': papers[1].get('novelty', 0),
                                'venue': papers[1].get('venue', ''),
                                'paper_type': papers[1].get('paper_type', 'preprint')
                            }
                        ],
                        'ai_analysis': result
                    }

            return {
                'papers': [
                    {
                        'id': p.get('id', ''),
                        'title': p.get('title', ''),
                        'authors': p.get('authors', []),
                        'published': p.get('published', ''),
                        'citations': p.get('citation_count', p.get('estimated_citations', 0)),
                        'impact_factor': p.get('impact_factor', 0),
                        'novelty': p.get('novelty', 0),
                        'venue': p.get('venue', ''),
                        'paper_type': p.get('paper_type', 'preprint')
                    } for p in papers
                ],
                'ai_analysis': {
                    'similarities': ['两篇论文均为该领域的重要研究工作', '都在方法层面有一定创新'],
                    'differences': [
                        {'aspect': '研究目标', 'paper1': papers[0].get('title', '')[:30] + '...', 'paper2': papers[1].get('title', '')[:30] + '...'},
                        {'aspect': '核心方法', 'paper1': '需查阅原文', 'paper2': '需查阅原文'},
                        {'aspect': '实验结果', 'paper1': '需查阅原文', 'paper2': '需查阅原文'},
                        {'aspect': '创新性', 'paper1': '需查阅原文', 'paper2': '需查阅原文'}
                    ],
                    'verdict': '请连接 AI 服务以获取详细对比分析',
                    'use_cases': {
                        'paper1_better_for': ['需AI分析'],
                        'paper2_better_for': ['需AI分析']
                    }
                }
            }
        except Exception as e:
            logger.error(f"Error comparing papers: {e}", exc_info=True)
            return None

    def _save_search(self, query: str, result: Dict[str, Any]) -> None:
        try:
            safe_query = query.replace('/', '_').replace('\\', '_')
            save_path = os.path.join(self.data_dir, f"{safe_query}.json")
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error saving search: {e}")

    def load_search(self, query: str) -> Optional[Dict[str, Any]]:
        try:
            safe_query = query.replace('/', '_').replace('\\', '_')
            save_path = os.path.join(self.data_dir, f"{safe_query}.json")
            if os.path.exists(save_path):
                with open(save_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return None
        except Exception as e:
            logger.error(f"Error loading search: {e}")
            return None

    def _build_top_papers(self, papers: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """构建Top10论文榜单，确保覆盖不同时间段"""
        if not papers:
            return []

        # 按年份分组
        year_groups = defaultdict(list)
        for p in papers:
            try:
                dt = datetime.fromisoformat(p['published'].replace('Z', '+00:00'))
                year = dt.year
            except Exception:
                try:
                    year = int(p['published'][:4])
                except Exception:
                    year = 2024
            p['_year'] = year
            year_groups[year].append(p)

        # 每个年份按影响力排序，选出该年最佳
        year_best = {}
        for year, year_papers in year_groups.items():
            year_papers.sort(
                key=lambda p: (p.get('impact_factor', 0), p.get('estimated_citations', 0), p.get('novelty', 0)),
                reverse=True
            )
            year_best[year] = year_papers[0]

        # 按影响力排序各年的最佳论文
        sorted_years = sorted(year_best.keys(), key=lambda y: year_best[y].get('impact_factor', 0), reverse=True)

        top_papers = []
        used_ids = set()

        # 第一步：从不同年份中各选1篇最佳论文（保证时间多样性）
        for year in sorted_years:
            if len(top_papers) >= 10:
                break
            paper = year_best[year]
            if paper['id'] not in used_ids:
                top_papers.append(paper)
                used_ids.add(paper['id'])

        # 第二步：如果不足10篇，从各年份中补充第二好的论文
        if len(top_papers) < 10:
            for year in sorted_years:
                if len(top_papers) >= 10:
                    break
                year_papers = year_groups[year]
                for p in year_papers[1:]:  # 跳过已选的最佳
                    if p['id'] not in used_ids:
                        top_papers.append(p)
                        used_ids.add(p['id'])
                        break

        # 第三步：如果仍不足10篇，从全部论文中补充
        if len(top_papers) < 10:
            all_sorted = sorted(papers,
                key=lambda p: (p.get('impact_factor', 0), p.get('estimated_citations', 0), p.get('novelty', 0)),
                reverse=True)
            for p in all_sorted:
                if len(top_papers) >= 10:
                    break
                if p['id'] not in used_ids:
                    top_papers.append(p)
                    used_ids.add(p['id'])

        # 最终按影响力排序，分配排名
        top_papers.sort(
            key=lambda p: (p.get('impact_factor', 0), p.get('estimated_citations', 0), p.get('novelty', 0)),
            reverse=True
        )

        result = []
        for i, p in enumerate(top_papers):
            result.append({
                'rank': i + 1,
                'id': p['id'],
                'title': p['title'],
                'authors': p.get('authors', []),
                'published': p.get('published', ''),
                'year': p.get('_year', ''),
                'summary': p.get('summary', '')[:200],
                'novelty': p.get('novelty', 50),
                'estimated_citations': p.get('estimated_citations', 20),
                'impact_factor': p.get('impact_factor', 3.0),
                'is_breakthrough': p.get('is_breakthrough', False),
                'is_classic': i < 3 or p.get('impact_factor', 0) >= 7.0,
                'paper_type': p.get('paper_type', 'preprint'),
                'venue': p.get('venue', ''),
                'citation_source': p.get('citation_source', 'estimated'),
                'ai_summary': p.get('ai_summary', {})
            })
        return result

    def _build_field_overview(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not papers:
            return {}

        total = len(papers)

        years = []
        for p in papers:
            try:
                dt = datetime.fromisoformat(p['published'].replace('Z', '+00:00'))
                years.append(dt.year)
            except Exception:
                try:
                    dt = datetime.strptime(p['published'][:10], '%Y-%m-%d')
                    years.append(dt.year)
                except Exception:
                    pass

        year_range = f"{min(years)}-{max(years)}" if years else "N/A"

        top_methods = []
        method_counts = {}
        for p in papers:
            ai_sum = p.get('ai_summary', {})
            methods = ai_sum.get('methods', [])
            for m in methods:
                m_clean = m.strip()
                if len(m_clean) > 2:
                    method_counts[m_clean] = method_counts.get(m_clean, 0) + 1

        sorted_methods = sorted(method_counts.items(), key=lambda x: x[1], reverse=True)
        top_methods = [m[0] for m in sorted_methods[:8]]

        breakthrough_count = sum(1 for p in papers if p.get('is_breakthrough', False))

        avg_impact = sum(p.get('impact_factor', 0) for p in papers) / max(1, total)
        avg_novelty = sum(p.get('novelty', 0) for p in papers) / max(1, total)

        return {
            'total_papers': total,
            'year_range': year_range,
            'top_methods': top_methods,
            'breakthrough_count': breakthrough_count,
            'avg_impact_factor': round(avg_impact, 1),
            'avg_novelty': round(avg_novelty, 1),
            'active_periods': len(set(years)) if years else 0
        }

    def _extract_keywords(self, paper: Dict[str, Any]) -> List[str]:
        """从论文标题和摘要中提取技术关键词。
        策略：提取标题/摘要中的专业术语（多词短语优先），结合 AI summary 的 methods。
        """
        import re
        from collections import Counter

        title = paper.get('title', '')
        summary = paper.get('summary', '')
        text = f"{title}. {summary}".lower()

        keywords = set()

        # 1. 常见技术术语表匹配（使用词边界，避免子串误匹配）
        tech_terms = [
            'transformer', 'attention mechanism', 'self-attention', 'multi-head attention',
            'diffusion model', 'denoising diffusion', 'stable diffusion', 'score-based model',
            'controlnet', 'latent diffusion',
            'graph neural network', 'graph convolutional network', 'graph attention',
            'reinforcement learning', 'policy gradient', 'actor-critic', 'q-learning',
            'generative adversarial network', 'stylegan', 'cyclegan',
            'convolutional neural network', 'resnet', 'vgg', 'inception',
            'recurrent neural network', 'lstm', 'gru',
            'bert', 'roberta', 'electra', 'albert',
            'large language model', 'foundation model',
            'vision-language model', 'multimodal model', 'vision transformer',
            'contrastive learning', 'contrastive language-image',
            'pre-training', 'pretraining', 'fine-tuning', 'finetuning', 'prompt tuning',
            'instruction tuning', 'rlhf', 'alignment',
            'few-shot', 'zero-shot', 'one-shot', 'in-context learning',
            'self-supervised learning', 'masked autoencoder',
            'meta-learning', 'maml',
            'adversarial training', 'domain adaptation', 'transfer learning',
            'federated learning', 'differential privacy',
            'quantization', 'knowledge distillation', 'model compression', 'pruning',
            'mixture of experts', 'low-rank adaptation',
            'retrieval augmented generation',
            'chain of thought', 'tool learning',
            'image generation', 'text-to-image', 'image captioning', 'image segmentation',
            'object detection', 'semantic segmentation', 'instance segmentation',
            'video understanding', 'action recognition', 'video generation',
            'visual question answering',
            'neural machine translation', 'text summarization',
            'representation learning', 'metric learning',
            'normalizing flow', 'variational autoencoder', 'autoregressive model',
            'energy-based model', 'flow matching', 'rectified flow',
            'scaling law', 'emergent ability',
            'knowledge graph', 'named entity recognition',
            'text-to-speech', 'speech recognition', 'audio generation',
            'neural radiance field', 'nerf',
            'world model', 'embodied ai',
        ]

        for term in tech_terms:
            # 多词术语用 in 匹配，单词术语用词边界匹配避免子串误匹配
            if ' ' in term or '-' in term:
                if term in text:
                    keywords.add(term)
            else:
                if re.search(r'\b' + re.escape(term) + r'\b', text):
                    keywords.add(term)

        # 2. 从标题中提取名词短语（大写词首字母缩写和专有名词）
        # 提取标题中的缩写词（如 BERT, GPT, CLIP 等 2-5个大写字母的词）
        acronyms = re.findall(r'\b[A-Z][A-Za-z0-9]*(?:[A-Z][A-Za-z0-9]*)+\b', title)
        for acr in acronyms:
            if 2 <= len(acr) <= 15:
                keywords.add(acr.lower())

        # 3. 从 AI summary 的 methods 字段提取（仅取简洁的方法名）
        ai_sum = paper.get('ai_summary', {})
        if ai_sum and isinstance(ai_sum, dict):
            methods = ai_sum.get('methods', [])
            for method in methods:
                m = method.lower().strip()
                # 跳过中文内容、过长的句子（methods 应该是简洁的方法名，不是完整句子）
                if 3 < len(m) < 40 and not any('\u4e00' <= c <= '\u9fff' for c in m):
                    # 跳过包含句号的（说明是完整句子而非方法名）
                    if '.' not in m and len(m.split()) <= 5:
                        if m not in ('deep learning method', 'deep learning approach'):
                            keywords.add(m)

        # 4. 从摘要中提取高频专业词组（2-3词短语）
        # 提取 "adjective+noun" 或 "noun+noun" 模式的短语
        stop = {'result', 'results', 'work', 'paper', 'method', 'approach',
                'algorithm', 'model', 'network', 'framework', 'technique',
                'system', 'problem', 'task', 'application', 'study', 'research',
                'analysis', 'evaluation', 'experiment', 'performance', 'comparison',
                'baseline', 'dataset', 'data', 'training', 'testing', 'validation',
                'metric', 'accuracy', 'precision', 'recall', 'score',
                'novel', 'new', 'proposed', 'introduce', 'present', 'develop',
                'design', 'implement', 'evaluate', 'show', 'demonstrate',
                'achieve', 'improve', 'outperform', 'better', 'best', 'first',
                'large', 'small', 'recent', 'previous', 'current', 'existing',
                'traditional', 'modern', 'based', 'using', 'via', 'with', 'for',
                'on', 'in', 'of', 'and', 'or', 'we', 'our', 'this', 'that',
                'these', 'those', 'they', 'their', 'it', 'its', 'an', 'a', 'the',
                'paper', 'propose', 'proposed', 'method', 'methods', 'approach',
                'approaches', 'learning', 'neural', 'deep', 'machine',
                # 常见无意义动词/介词/代词
                'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has',
                'had', 'do', 'does', 'did', 'will', 'would', 'can', 'could',
                'should', 'may', 'might', 'must', 'shall', 'not', 'no', 'nor',
                'but', 'however', 'while', 'when', 'where', 'which', 'what',
                'who', 'whom', 'how', 'why', 'if', 'then', 'else', 'also',
                'than', 'too', 'very', 'more', 'most', 'less', 'least',
                'some', 'any', 'all', 'each', 'every', 'both', 'few', 'many',
                'such', 'same', 'other', 'another', 'only', 'just', 'even',
                'there', 'here', 'now', 'thus', 'hence', 'therefore',
                'between', 'through', 'during', 'before', 'after', 'above',
                'below', 'from', 'into', 'onto', 'upon', 'over', 'under',
                'two', 'three', 'one', 'four', 'five', 'high', 'low',
                'well', 'still', 'often', 'always', 'never', 'ever'}

        # 简单的 n-gram 提取（仅从英文摘要中提取）
        words = re.findall(r'[a-z][a-z0-9-]+', summary.lower())
        bigrams = []
        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i + 1]
            if w1 not in stop and w2 not in stop and len(w1) > 2 and len(w2) > 2:
                bigrams.append(f"{w1} {w2}")

        # 取出现次数 >= 2 的高频 bigram
        bg_counts = Counter(bigrams)
        for bg, count in bg_counts.most_common(5):
            if count >= 2:
                keywords.add(bg)

        # 5. 过滤和限制
        # 去掉纯数字、过短/过长的关键词
        keywords = {k for k in keywords if 3 <= len(k) <= 50 and not k.isdigit()}

        return list(keywords)[:8]

    def _build_tech_evolution(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """构建技术演进路线图"""
        if not papers:
            return {'timeline': {}}

        year_keywords = defaultdict(lambda: defaultdict(lambda: {'count': 0, 'impact_sum': 0, 'papers': []}))

        for p in papers:
            pub_date = p.get('published', '')
            impact = p.get('impact_factor', 0)

            try:
                year = datetime.fromisoformat(pub_date.replace('Z', '+00:00')).year
            except Exception:
                try:
                    year = int(pub_date[:4])
                except Exception:
                    continue

            keywords = self._extract_keywords(p)
            for kw in keywords:
                year_keywords[year][kw]['count'] += 1
                year_keywords[year][kw]['impact_sum'] += impact
                if len(year_keywords[year][kw]['papers']) < 2:
                    year_keywords[year][kw]['papers'].append({
                        'id': p['id'],
                        'title': p['title'][:50],
                        'impact': impact
                    })

        years = []
        for year in year_keywords:
            years.append(year)

        if not years:
            return {'timeline': {}}

        min_year = min(years)
        max_year = max(years)

        all_keywords = defaultdict(int)
        for year in year_keywords:
            for kw in year_keywords[year]:
                all_keywords[kw] += year_keywords[year][kw]['count']

        total_papers = sum(
            sum(year_keywords[year][kw]['count'] for kw in year_keywords[year])
            for year in year_keywords
        )

        common_keywords = set()
        for kw, total_count in all_keywords.items():
            if total_count > total_papers * 0.8:
                common_keywords.add(kw)

        timeline = {}
        for year in range(min_year, max_year + 1):
            if year in year_keywords:
                keywords = []
                for kw, data in year_keywords[year].items():
                    avg_impact = data['impact_sum'] / max(1, data['count'])
                    if len(kw) < 3 or len(kw) > 40:
                        continue
                    if data['count'] < 2 and avg_impact < 5:
                        continue
                    if kw in common_keywords:
                        continue
                    keywords.append({
                        'keyword': kw.replace('-', ' '),
                        'count': data['count'],
                        'avg_impact': round(avg_impact, 1),
                        'papers': data['papers']
                    })
                keywords.sort(key=lambda x: (-x['avg_impact'], -x['count']))
                timeline[str(year)] = keywords[:8]
            else:
                timeline[str(year)] = []

        return {'timeline': timeline}

    def _build_researcher_graph(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """构建核心研究者图谱"""
        author_stats = defaultdict(lambda: {
            'papers': [],
            'total_citations': 0,
            'avg_impact': 0,
            'total_impact': 0,
            'breakthroughs': 0
        })

        for p in papers:
            authors = p.get('authors', [])
            citations = p.get('estimated_citations', 0)
            impact = p.get('impact_factor', 0)
            is_bt = p.get('is_breakthrough', False)

            try:
                year = datetime.fromisoformat(p['published'].replace('Z', '+00:00')).year
            except Exception:
                try:
                    year = int(p['published'][:4])
                except Exception:
                    year = 2024

            for author in authors:
                author = author.strip()
                if author and len(author) > 2:
                    author_stats[author]['papers'].append({
                        'id': p['id'],
                        'title': p['title'],
                        'year': year,
                        'impact': impact,
                        'is_breakthrough': is_bt
                    })
                    author_stats[author]['total_citations'] += citations
                    author_stats[author]['total_impact'] += impact
                    if is_bt:
                        author_stats[author]['breakthroughs'] += 1

        researchers = []
        for author, data in author_stats.items():
            if len(data['papers']) >= 2 or data['total_impact'] > 10:
                avg_impact = data['total_impact'] / len(data['papers'])
                researchers.append({
                    'name': author,
                    'paper_count': len(data['papers']),
                    'total_citations': data['total_citations'],
                    'avg_impact': round(avg_impact, 1),
                    'breakthroughs': data['breakthroughs'],
                    'papers': sorted(data['papers'], key=lambda x: x['impact'], reverse=True)[:5],
                    'tier': 'top' if avg_impact > 6 else 'major' if avg_impact > 4 else 'active'
                })

        researchers.sort(key=lambda x: (x['avg_impact'], x['paper_count']), reverse=True)

        return {
            'researchers': researchers[:30],
            'total_unique_authors': len(author_stats),
            'top_researchers': researchers[:10]
        }

    def _build_reading_path(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """构建入门阅读路径"""
        if not papers:
            return {'path': [], 'total': 0}

        scored_papers = []
        for p in papers:
            impact = p.get('impact_factor', 0)
            novelty = p.get('novelty', 0)
            citations = p.get('estimated_citations', 0)
            is_bt = p.get('is_breakthrough', False)

            foundational_score = (impact * 0.5 + citations * 0.01 + novelty * 0.3)
            if is_bt:
                foundational_score += 5

            try:
                year = datetime.fromisoformat(p['published'].replace('Z', '+00:00')).year
            except Exception:
                try:
                    year = int(p['published'][:4])
                except Exception:
                    year = 2024

            scored_papers.append({
                'id': p['id'],
                'title': p['title'],
                'year': year,
                'impact': impact,
                'novelty': novelty,
                'citations': citations,
                'is_breakthrough': is_bt,
                'foundational_score': round(foundational_score, 1)
            })

        scored_papers.sort(key=lambda x: x['foundational_score'], reverse=True)

        top_3 = scored_papers[:3]
        remaining = scored_papers[3:15]

        path = []

        path.append({
            'stage': '入门必读',
            'description': '了解领域核心概念和基础方法',
            'papers': top_3,
            'order': 1
        })

        if len(remaining) > 0:
            mid = remaining[:len(remaining)//2]
            path.append({
                'stage': '进阶深入',
                'description': '掌握主流方法和技术细节',
                'papers': mid,
                'order': 2
            })

            late = remaining[len(remaining)//2:]
            if late:
                path.append({
                    'stage': '前沿拓展',
                    'description': '了解最新研究动态和未来方向',
                    'papers': late,
                    'order': 3
                })

        return {
            'path': path,
            'total_papers': len(scored_papers)
        }

    def _build_research_gaps(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        """分析研究空白和潜在方向"""
        if not papers:
            return {'gaps': [], 'suggestions': []}

        method_years = defaultdict(set)
        all_methods = set()
        method_combinations = defaultdict(int)

        for p in papers:
            ai_sum = p.get('ai_summary', {})
            methods = ai_sum.get('methods', [])

            try:
                year = datetime.fromisoformat(p['published'].replace('Z', '+00:00')).year
            except Exception:
                try:
                    year = int(p['published'][:4])
                except Exception:
                    year = 2024

            for m in methods:
                m = m.strip()
                if len(m) > 3:
                    method_years[m].add(year)
                    all_methods.add(m)

            for i, m1 in enumerate(methods):
                for m2 in methods[i+1:]:
                    m1, m2 = sorted([m1.strip(), m2.strip()])
                    if len(m1) > 3 and len(m2) > 3:
                        method_combinations[(m1, m2)] += 1

        gaps = []

        top_methods = sorted(method_years.keys(), key=lambda x: len(method_years[x]), reverse=True)[:20]
        for i, m1 in enumerate(top_methods):
            for m2 in top_methods[i+1:]:
                combo_key = tuple(sorted([m1, m2]))
                if combo_key not in method_combinations or method_combinations[combo_key] < 2:
                    if len(method_years[m1]) >= 3 and len(method_years[m2]) >= 3:
                        gaps.append({
                            'type': 'cross_method',
                            'description': f'{m1} 与 {m2} 的结合应用',
                            'methods': [m1, m2],
                            'potential': 'high'
                        })

        declining_methods = []
        current_year = datetime.now().year
        for method, years in method_years.items():
            if len(years) >= 3:
                recent = [y for y in years if y >= current_year - 2]
                older = [y for y in years if y < current_year - 2]
                if len(older) > len(recent) * 2:
                    declining_methods.append(method)

        if declining_methods:
            gaps.append({
                'type': 'revival',
                'description': f'重新探索经典方法：{", ".join(declining_methods[:3])}',
                'methods': declining_methods[:3],
                'potential': 'medium'
            })

        gaps = gaps[:8]

        suggestions = [
            '关注跨领域方法融合，可能产生创新性突破',
            '分析经典方法的现代应用场景',
            '探索未充分研究的子方向'
        ]

        return {
            'gaps': gaps,
            'suggestions': suggestions,
            'total_methods': len(all_methods)
        }

    def _get_demo_papers(self, query: str) -> List[Dict[str, Any]]:
        import random
        demo_papers = []
        methods_pool = [
            ['transformer', 'self-supervised'],
            ['diffusion', 'gan'],
            ['cnn', 'transformer'],
            ['graph', 'reinforcement'],
            ['transformer', 'diffusion'],
            ['rnn', 'bayesian'],
            ['cnn', 'gan'],
            ['graph', 'transformer'],
            ['diffusion', 'self-supervised'],
            ['reinforcement', 'transformer'],
        ]

        titles = [
            f"A Novel Transformer-Based Approach for {query.title()} Understanding",
            f"Diffusion Models Meet GANs: A Hybrid Framework for {query.title()}",
            f"Convolutional Neural Networks with Attention for {query.title()}",
            f"Graph Neural Networks for {query.title()} Representation Learning",
            f"Scaling Laws in {query.title()}: A Comprehensive Study",
            f"Bayesian Recurrent Networks for Sequential {query.title()}",
            f"Generative Adversarial Pretraining for {query.title()}",
            f"Graph-Based Knowledge Distillation in {query.title()}",
            f"Self-Supervised Diffusion for {query.title()} Generation",
            f"Reinforcement Learning with Transformer Policies for {query.title()}",
            f"Multi-Modal {query.title()} with Unified Representations",
            f"Efficient {query.title()} via Sparse Attention Mechanisms",
            f"Federated Learning for {query.title()} Privacy Preservation",
            f"Adversarial Robustness in {query.title()} Models",
            f"Continual Learning Strategies for {query.title()}",
            f"Emerging Paradigms in {query.title()}: A Survey",
            f"Pretrained Foundation Models for {query.title()}",
            f"Contrastive Learning for {query.title()} Understanding",
            f"Sparse Mixture of Experts for {query.title()}",
            f"Energy-Based Models for {query.title()} Generation",
        ]

        for i in range(min(20, len(titles))):
            current_year = datetime.now().year
            year = current_year - (i // 5)
            month = (i % 12) + 1
            paper_id = f"{year % 100:02d}{month:02d}.{i + 1:05d}"
            methods = methods_pool[i % len(methods_pool)]
            summary = self._generate_demo_summary(query, titles[i], methods)
            paper = {
                'id': paper_id,
                'title': titles[i],
                'authors': [
                    f"Author {chr(65 + i % 8)}",
                    f"Author {chr(66 + i % 7)}",
                    f"Author {chr(67 + i % 6)}"
                ],
                'summary': summary,
                'published': f"{year}-{month:02d}-{(15 + i) % 28 + 1:02d}T00:00:00",
                'updated': f"{year}-{month:02d}-{(15 + i) % 28 + 1:02d}T00:00:00",
                'categories': [f"cs.{('CL', 'CV', 'LG', 'AI', 'IR')[i % 5]}"],
                'pdf_url': f"https://arxiv.org/pdf/{paper_id}.pdf",
                'abs_url': f"https://arxiv.org/abs/{paper_id}",
                'doi': '',
                'comment': f'{10 + i} pages, {3 + i % 4} figures',
                'journal_ref': ''
            }
            demo_papers.append(paper)

        return demo_papers

    def _generate_demo_summary(self, query: str, title: str, methods: List[str]) -> str:
        method_str = ' and '.join(methods)
        return (
            f"We present a novel approach to {query} based on {method_str}. "
            f"Our method achieves state-of-the-art performance on multiple benchmarks. "
            f"Through extensive experiments, we demonstrate significant improvements over existing baselines. "
            f"The proposed framework introduces several key innovations including a novel attention mechanism "
            f"and an efficient training strategy. We provide comprehensive ablation studies and analysis "
            f"to validate the effectiveness of each component."
        )
