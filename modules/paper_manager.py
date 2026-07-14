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

    def search_and_analyze(self, query: str, max_results: Optional[int] = None) -> Dict[str, Any]:
        try:
            logger.info(f"Starting search and analysis for query: {query}")

            translated_query = self.summarizer.translate_keyword(query)
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
        """按归一化标题去重，优先保留有真实引用量/venue 的来源"""
        import re

        def _norm_title(title: str) -> str:
            t = re.sub(r'[^a-z0-9\s]', '', title.lower())
            t = re.sub(r'\s+', ' ', t).strip()
            return t

        # 按 (归一化标题, doi, arxiv_id) 去重
        seen: Dict[str, Dict[str, Any]] = {}
        for p in papers:
            key = _norm_title(p.get('title', ''))
            if not key:
                continue

            existing = seen.get(key)
            if existing is None:
                seen[key] = p
                continue

            # 已存在：合并字段，优先保留信息更丰富的记录
            # 优先级：有真实引用量 > 有venue > arxiv
            new_score = self._info_score(p)
            old_score = self._info_score(existing)
            if new_score > old_score:
                # 合并：保留更丰富的记录，但补充缺失字段
                merged = {**existing, **p}
                for k, v in existing.items():
                    if not merged.get(k):
                        merged[k] = v
                seen[key] = merged
            else:
                # 保留 existing，但补充 p 中缺失的字段
                for k, v in p.items():
                    if not existing.get(k) and v:
                        existing[k] = v

        return list(seen.values())

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
        """从论文中提取技术关键词"""
        keywords = set()

        title = paper.get('title', '').lower()
        summary = paper.get('summary', '').lower()

        stopwords = {
            'result', 'results', 'work', 'works', 'paper', 'papers', 'method', 'methods',
            'approach', 'approaches', 'algorithm', 'algorithms', 'model', 'models',
            'network', 'networks', 'framework', 'frameworks', 'technique', 'techniques',
            'system', 'systems', 'problem', 'problems', 'task', 'tasks', 'application',
            'applications', 'study', 'studies', 'research', 'investigation', 'analysis',
            'evaluation', 'experiments', 'experimental', 'performance', 'comparison',
            'baseline', 'baselines', 'dataset', 'datasets', 'data', 'datum', 'training',
            'testing', 'validation', 'evaluation', 'metric', 'metrics', 'accuracy',
            'precision', 'recall', 'f1', 'score', 'scores', 'state-of-the-art', 'sota',
            'novel', 'new', 'proposed', 'introduce', 'present', 'develop', 'design',
            'implement', 'evaluate', 'show', 'demonstrate', 'achieve', 'improve',
            'outperform', 'better', 'best', 'first', 'large', 'small', 'recent', 'previous',
            'current', 'existing', 'traditional', 'modern', 'deep', 'shallow', 'neural',
            'learning', 'machine', 'artificial', 'intelligence', 'computational',
            'based', 'using', 'via', 'with', 'for', 'on', 'in', 'of', 'and', 'or', 'we',
            'our', 'this', 'that', 'these', 'those', 'they', 'their', 'it', 'its', 'an', 'a', 'the'
        }

        tech_keywords = [
            'transformer', 'attention mechanism', 'multi-head attention', 'self-attention',
            'diffusion model', 'denoising diffusion', 'stable diffusion', 'controlnet',
            'graph neural network', 'gnn', 'graph convolutional', 'gcn', 'gat', 'graph attention',
            'reinforcement learning', 'rl', 'deep reinforcement', 'policy gradient', 'actor-critic',
            'generative adversarial', 'gan', 'stylegan', 'biggan', 'cyclegan',
            'convolutional neural', 'cnn', 'resnet', 'vgg', 'inception', 'densenet',
            'recurrent neural', 'rnn', 'lstm', 'gru', 'bidirectional',
            'bert', 'roberta', 'electra', 'albert', 'deberta',
            'gpt', 'gpt-2', 'gpt-3', 'gpt-4', 'gpt-5',
            'clip', 'contrastive language image', 'flamingo', 'blip', 'blip-2',
            'imagen', 'dall-e', 'dall-e 2', 'dall-e 3', 'stable diffusion',
            'large language model', 'llm', 'foundation model', 'multimodal model',
            'vision language model', 'vlm', 'visual language', 'vision-language',
            'pre-training', 'pretraining', 'fine-tuning', 'finetuning', 'prompt tuning',
            'instruction tuning', 'alignment', 'rlhf', 'direct preference',
            'few-shot', 'few shot', 'zero-shot', 'zero shot', 'one-shot',
            'self-supervised learning', 'contrastive learning', 'masked autoencoder',
            'meta-learning', 'maml', 'few-shot learning', 'learning to learn',
            'adversarial training', 'domain adaptation', 'transfer learning',
            'federated learning', 'privacy preserving', 'differential privacy',
            'quantization', 'model compression', 'knowledge distillation', 'pruning',
            'mixture of experts', 'moe', 'sparse model', 'adapter', 'lora', 'low-rank',
            'retrieval augmented', 'rag', 'retrieval-based', 'memory augmented',
            'agent', 'ai agent', 'planning', 'reasoning', 'chain of thought', 'cot',
            'tool use', 'tool learning', 'function calling',
            'embedding', 'text embedding', 'image embedding', 'multimodal embedding',
            'tokenization', 'byte pair', 'sentencepiece', 'wordpiece',
            'decoding', 'beam search', 'top-k', 'top-p', 'nucleus sampling',
            'scaling law', 'efficiency', 'inference speed', 'training efficiency',
            'encoder-decoder', 'decoder-only', 'encoder-only',
            'visual grounding', 'object detection', 'image segmentation', 'instance segmentation',
            'video understanding', 'action recognition', 'video generation',
            'navigation', 'vln', 'visual navigation', 'embodied ai', 'embodied learning',
            'question answering', 'visual qa', 'vqa', 'text qa',
            'summarization', 'text summarization', 'video summarization',
            'machine translation', 'neural machine', 'zero-shot translation',
            'image captioning', 'video captioning', 'image generation', 'text-to-image',
            'parsing', 'constituency parsing', 'dependency parsing', 'semantic parsing',
            'representation learning', 'feature learning', 'metric learning',
            'optimization', 'adam', 'sgd', 'learning rate', 'batch normalization',
            'regularization', 'dropout', 'weight decay', 'label smoothing',
            'benchmark', 'leaderboard', 'evaluation protocol', 'standard dataset',
            'openai', 'google', 'meta', 'microsoft', 'deepmind', 'anthropic',
            'stanford', 'mit', 'cmu', 'berkeley', 'eth zurich', 'max planck',
            'arxiv', 'iclr', 'icml', 'neurips', 'acl', 'emnlp', 'cvpr', 'eccv', 'iccv',
            'aaai', 'ijcai', 'sigir', 'kdd', 'wsdm', 'www'
        ]

        for kw in tech_keywords:
            if kw in title or kw in summary:
                keywords.add(kw)

        ai_sum = paper.get('ai_summary', {})
        methods = ai_sum.get('methods', [])
        for method in methods:
            m = method.lower().strip()
            if len(m) > 3 and len(m) < 50:
                parts = m.replace('-', ' ').replace('_', ' ').split()
                filtered = [p for p in parts if len(p) >= 3 and p not in stopwords]
                if len(filtered) >= 2:
                    keywords.add(' '.join(filtered[:3]))
                elif len(filtered) == 1 and filtered[0] not in stopwords:
                    keywords.add(filtered[0])

        for cat in paper.get('categories', []):
            if any(prefix in cat for prefix in ['cs.', 'stat.', 'q-bio.', 'q-fin.']):
                keywords.add(cat)

        keywords = {k for k in keywords if k not in stopwords}

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
