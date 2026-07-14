import re
import json
import logging
from typing import Dict, List, Optional, Any

import requests
import config

logger = logging.getLogger(__name__)


class AISummarizer:
    def __init__(self) -> None:
        self.provider: str = config.AI_PROVIDER
        self.api_key: str = config.AI_API_KEY
        self.api_url: str = config.AI_API_URL
        self.model: str = config.AI_MODEL
        self.timeout: int = config.AI_TIMEOUT
        self.max_tokens: int = config.AI_MAX_TOKENS
        self.temperature: float = config.AI_TEMPERATURE

    def _call_deepseek(self, prompt: str, temperature: float = None, max_tokens: int = None) -> Optional[Dict[str, Any]]:
        if not self.api_key:
            logger.warning("DeepSeek API key not configured, skipping API call")
            return None
            
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            data = {
                'model': self.model,
                'messages': [{'role': 'user', 'content': prompt}],
                'temperature': temperature or self.temperature,
                'max_tokens': max_tokens or self.max_tokens,
                'response_format': {'type': 'json_object'}
            }
            response = requests.post(
                self.api_url,
                headers=headers,
                json=data,
                timeout=self.timeout
            )
            
            if response.status_code == 429:
                logger.warning("DeepSeek API rate limited")
                return None
                
            response.raise_for_status()
            result = response.json()
            
            if 'choices' not in result or not result['choices']:
                logger.error("DeepSeek API returned empty choices")
                return None
                
            content = result['choices'][0]['message']['content']
            
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                logger.warning("DeepSeek returned non-JSON content, trying to parse")
                cleaned = content.strip()
                if cleaned.startswith('```json'):
                    cleaned = cleaned[7:-3].strip()
                try:
                    return json.loads(cleaned)
                except:
                    logger.error(f"Failed to parse DeepSeek response: {content[:200]}")
                    return None
                    
        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API request error: {e}")
            return None
        except Exception as e:
            logger.error(f"DeepSeek API unknown error: {e}", exc_info=True)
            return None

    def translate_keyword(self, keyword: str) -> str:
        if self._is_english(keyword):
            return keyword

        if self.provider == 'deepseek' and self.api_key:
            try:
                prompt = f"""你是一个科研领域的专业翻译。请将以下中文关键词翻译为英文科研专业术语，用于在arXiv等学术数据库中检索相关论文。

要求：
1. 返回最常用的学术英文表达
2. 如果输入已经是英文，直接返回
3. 可以返回多个相关术语，用空格连接

输入关键词：{keyword}

请返回JSON格式：{{"translated": "英文术语", "alternatives": ["备选术语1", "备选术语2"]}}"""

                result = self._call_deepseek(prompt, temperature=0.3, max_tokens=200)
                if result and 'translated' in result:
                    logger.info(f"Translated '{keyword}' to '{result['translated']}'")
                    return result['translated']
            except Exception as e:
                logger.warning(f"AI translation failed, using local translation: {e}")

        return self._local_translate(keyword)

    def _local_translate(self, keyword: str) -> str:
        local_map = {
            '大语言模型': 'large language model',
            '大模型': 'large language model',
            '图像生成': 'image generation',
            '强化学习': 'reinforcement learning',
            '深度学习': 'deep learning',
            '机器学习': 'machine learning',
            '自然语言处理': 'natural language processing',
            '计算机视觉': 'computer vision',
            '目标检测': 'object detection',
            '图像分割': 'image segmentation',
            '图神经网络': 'graph neural network',
            '知识图谱': 'knowledge graph',
            '联邦学习': 'federated learning',
            '迁移学习': 'transfer learning',
            '对抗学习': 'adversarial learning',
            '注意力机制': 'attention mechanism',
            '扩散模型': 'diffusion model',
            '生成对抗网络': 'generative adversarial network',
            '多模态': 'multimodal',
            '预训练': 'pretraining',
            '微调': 'fine-tuning',
            '提示学习': 'prompt learning',
            '元学习': 'meta learning',
            '自监督学习': 'self-supervised learning',
            '语音识别': 'speech recognition',
            '文本生成': 'text generation',
            '问答系统': 'question answering',
            '推荐系统': 'recommendation system',
            '异常检测': 'anomaly detection',
            '时间序列': 'time series',
            '因果推断': 'causal inference',
        }
        return local_map.get(keyword.strip(), keyword)

    def _is_english(self, text: str) -> bool:
        return bool(re.match(r'^[a-zA-Z0-9\s\-\._]+$', text))

    def summarize_paper(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        if self.provider == 'deepseek' and self.api_key:
            return self._deepseek_summarize_paper(paper)
        return self._mock_summarize(paper)

    def summarize_papers_batch(self, papers: List[Dict[str, Any]], batch_size: int = 20) -> Dict[str, Dict[str, Any]]:
        """批量分析多篇论文，返回 {paper_id: summary_dict} 字典。
        比逐篇调用快 10-20 倍。
        """
        results: Dict[str, Dict[str, Any]] = {}

        if self.provider == 'deepseek' and self.api_key:
            for i in range(0, len(papers), batch_size):
                batch = papers[i:i + batch_size]
                batch_results = self._deepseek_summarize_batch(batch)
                results.update(batch_results)
                logger.info(f"Batch summarized {min(i + batch_size, len(papers))}/{len(papers)} papers")
        else:
            for p in papers:
                results[p['id']] = self._mock_summarize(p)

        return results

    def _deepseek_summarize_batch(self, papers: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """批量分析一组论文（一次 API 调用）。"""
        paper_list = []
        for i, p in enumerate(papers):
            title = p.get('title', '')
            abstract = p.get('summary', '')[:300]
            authors = ', '.join(p.get('authors', [])[:3]) or 'Unknown'
            year = p.get('year', '') or (p.get('published', '')[:4] if p.get('published') else '')
            citations = p.get('citation_count', 0)
            venue = p.get('venue', '')
            paper_list.append(
                f"[{i + 1}] 标题: {title}\n"
                f"    年份: {year} | 引用: {citations} | 来源: {venue}\n"
                f"    摘要: {abstract}"
            )

        papers_text = '\n\n'.join(paper_list)
        n = len(papers)

        prompt = f"""请对以下 {n} 篇学术论文进行批量分析，返回JSON格式。

{papers_text}

请返回JSON格式，顶层键为 papers，是一个长度为 {n} 的数组，按输入顺序排列。每篇论文包含：
{{
    "papers": [
        {{
            "index": 1,
            "brief": "一句话中文总结（30-50字）",
            "methods": ["方法1", "方法2", "方法3"],
            "contributions": ["贡献1", "贡献2"],
            "datasets": ["数据集"],
            "field": "研究领域",
            "novelty": 创新性评分(0-100整数),
            "estimated_citations": 估算引用量(整数),
            "impact_factor": 影响力因子(0-10浮点数),
            "is_breakthrough": true/false,
            "breakthrough_reason": "原因或空字符串"
        }}
    ]
}}

评估标准：
- novelty: 真正有重大创新的给80+，增量创新给50-70，普通工作给40以下
- estimated_citations: 必须结合论文发表时间和影响力综合估算。革命性/奠基性工作3000-10000+；重要突破/SOTA工作800-3000；有价值的方法改进300-1500；普通方法论文100-500；发表超过2年的论文引用量应明显更高（时间累积效应）。切勿给出低于100的引用量。
- impact_factor: 革命性方法9-10，重要进展6-8，普通工作3-5
- 注意：如果论文已有真实引用量（citation_count），可参考但不要被局限（老论文引用量天然高，应结合质量评估）"""

        result = self._call_deepseek(prompt, temperature=0.5, max_tokens=3000)
        output: Dict[str, Dict[str, Any]] = {}

        if result and 'papers' in result:
            for i, item in enumerate(result['papers']):
                if i < len(papers):
                    paper_id = papers[i]['id']
                    output[paper_id] = item
        else:
            logger.warning(f"Batch summary returned unexpected format, falling back to individual")
            for p in papers:
                output[p['id']] = self._mock_summarize(p)

        return output

    def _deepseek_summarize_paper(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        title = paper.get('title', '')
        abstract = paper.get('summary', '')
        authors = paper.get('authors', [])
        categories = paper.get('categories', [])
        published = paper.get('published', '')

        prompt = f"""请对以下学术论文进行深度分析总结，返回JSON格式。

标题：{title}
摘要：{abstract}
作者：{', '.join(authors[:5]) if authors else 'Unknown'}
分类：{', '.join(categories)}
发表时间：{published}

请返回以下JSON字段：
{{
    "brief": "一句话中文总结论文核心内容（30-50字）",
    "methods": ["核心方法1", "核心方法2", "核心方法3"],
    "contributions": ["主要贡献1", "主要贡献2"],
    "datasets": ["使用的数据集"],
    "field": "研究领域",
    "novelty": 创新性评分(0-100的整数，根据方法创新性、技术突破程度、贡献大小综合评估),
    "estimated_citations": 估算引用量(整数，根据论文质量、发表时间、领域热度估算),
    "impact_factor": 影响力因子(0-10的浮点数，根据论文潜在影响力、方法重要性估算),
    "is_breakthrough": true或false(是否为突破性工作),
    "breakthrough_reason": "如果是突破性工作，说明原因；否则为空字符串"
}}

评估标准：
- novelty: 真正有重大创新的给80+，增量创新给50-70，普通工作给40以下
- estimated_citations: 必须结合论文发表时间和影响力综合估算。革命性/奠基性工作（如提出Transformer、GAN、BERT等）3000-10000+；重要突破/SOTA工作800-3000；有价值的方法改进300-1500；普通方法论文100-500；发表超过2年的论文引用量应明显更高（时间累积效应），发表超过5年的高质量论文通常1000+。切勿给出低于100的引用量，除非论文质量极差。
- impact_factor: 革命性方法9-10，重要进展6-8，普通工作3-5"""

        result = self._call_deepseek(prompt, temperature=0.5, max_tokens=1000)
        if result:
            return result
        return self._mock_summarize(paper)

    def summarize_time_period(self, papers: List[Dict[str, Any]], period_label: str) -> Dict[str, Any]:
        if not papers:
            return {
                'summary': '该时段暂无论文',
                'breakthroughs': [],
                'trends': []
            }

        if self.provider == 'deepseek' and self.api_key:
            return self._deepseek_summarize_period(papers, period_label)
        return self._mock_summarize_period(papers, period_label)

    def summarize_periods_batch(self, periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """批量分析多个时间段，一次 API 调用完成。
        periods: [{'label': '2024年', 'papers': [...], 'index': 0}, ...]
        返回按 index 排序的结果列表
        """
        if not periods:
            return []

        if not (self.provider == 'deepseek' and self.api_key):
            results = []
            for p in periods:
                results.append({
                    'index': p['index'],
                    **self._mock_summarize_period(p['papers'], p['label'])
                })
            results.sort(key=lambda x: x['index'])
            return results

        # 构建批量 prompt
        period_texts = []
        for p in periods:
            idx = p['index']
            label = p['label']
            papers = p['papers'][:15]
            paper_list = []
            for i, pp in enumerate(papers):
                paper_list.append(f"  [{i + 1}] {pp.get('title', '')}")
            period_texts.append(
                f"## 时段 {idx + 1}: {label}（共{len(p['papers'])}篇）\n"
                + '\n'.join(paper_list)
            )

        all_text = '\n\n'.join(period_texts)
        n = len(periods)

        prompt = f"""请对以下 {n} 个时间段的论文分别进行总结分析，返回JSON格式。

{all_text}

请返回JSON格式，顶层键为 periods，是一个长度为 {n} 的数组，按输入顺序排列。每个时段包含：
{{
    "periods": [
        {{
            "index": 1,
            "summary": "该时段研究进展的中文总结（150-300字），包括主流方向、技术趋势和整体发展态势",
            "breakthroughs": [
                {{
                    "paper_index": 论文序号(从1开始),
                    "method_name": "突破性方法名称",
                    "description": "为什么是突破性的（50-80字）",
                    "impact": "high/medium/low"
                }}
            ],
            "trends": ["研究趋势1", "趋势2", "趋势3"],
            "key_methods": ["主要方法1", "方法2"],
            "hot_topics": ["热点1", "热点2"]
        }}
    ]
}}

注意：
- 每个时段独立分析，不要混淆
- breakthroughs 只包含真正具有创新性的工作，每时段最多2-3个
- 如果没有明显突破性工作，breakthroughs 为空数组
- 总结要用中文"""

        result = self._call_deepseek(prompt, temperature=0.5, max_tokens=4000)

        if result and 'periods' in result:
            output = []
            for i, item in enumerate(result['periods']):
                if i < len(periods):
                    period_info = periods[i]
                    # 回填 paper_id 和 paper_title
                    for bt in item.get('breakthroughs', []):
                        idx = bt.get('paper_index', 0) - 1
                        if 0 <= idx < len(period_info['papers']):
                            bt['paper_id'] = period_info['papers'][idx].get('id', '')
                            bt['paper_title'] = period_info['papers'][idx].get('title', '')
                    output.append({
                        'index': period_info['index'],
                        **item
                    })
            output.sort(key=lambda x: x['index'])
            return output

        # fallback：逐时段分析
        logger.warning("Batch period summary failed, falling back to individual")
        results = []
        for p in periods:
            results.append({
                'index': p['index'],
                **self._mock_summarize_period(p['papers'], p['label'])
            })
        results.sort(key=lambda x: x['index'])
        return results

    def _deepseek_summarize_period(self, papers: List[Dict[str, Any]], period_label: str) -> Dict[str, Any]:
        paper_list = []
        for i, p in enumerate(papers[:20]):
            paper_list.append(f"{i+1}. 标题: {p.get('title', '')}\n   摘要: {p.get('summary', '')[:200]}")

        papers_text = '\n'.join(paper_list)
        prompt = f"""你是一个科研领域的资深分析专家。请分析以下{period_label}期间发表的{len(papers)}篇论文，给出该时段的科研总结。

论文列表：
{papers_text}

请返回以下JSON格式：
{{
    "summary": "该时段研究进展的中文总结（200-400字），包括主流方向、技术趋势和整体发展态势",
    "breakthroughs": [
        {{
            "paper_index": 论文序号(从1开始),
            "method_name": "突破性方法名称",
            "description": "为什么是突破性的（中文，50-100字）",
            "impact": "high/medium/low"
        }}
    ],
    "trends": ["研究趋势1", "研究趋势2", "研究趋势3"],
    "key_methods": ["该时段主要使用的方法1", "方法2"],
    "hot_topics": ["热点话题1", "热点话题2"]
}}

注意：
- breakthroughs只包含真正具有创新性和突破性的工作，最多3-5个
- 如果没有明显突破性工作，breakthroughs为空数组
- 总结要用中文"""

        result = self._call_deepseek(prompt, temperature=0.5, max_tokens=1500)
        if result:
            for bt in result.get('breakthroughs', []):
                idx = bt.get('paper_index', 0) - 1
                if 0 <= idx < len(papers):
                    bt['paper_id'] = papers[idx].get('id', '')
                    bt['paper_title'] = papers[idx].get('title', '')
            return result

        return self._mock_summarize_period(papers, period_label)

    def generate_design_doc(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        if self.provider == 'deepseek' and self.api_key:
            return self._deepseek_design_doc(paper)
        return self._mock_design_doc(paper)

    def _deepseek_design_doc(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        title = paper.get('title', '')
        abstract = paper.get('summary', '')
        prompt = f"""请为以下论文生成一份详细的复现设计文档，返回JSON格式。

标题：{title}
摘要：{abstract}

请返回以下JSON字段：
{{
    "title": "复现设计文档标题",
    "overview": "项目概述（中文，100-200字）",
    "core_idea": "核心思想（中文）",
    "architecture": ["架构组件1", "架构组件2", "架构组件3"],
    "implementation_steps": ["实现步骤1", "实现步骤2", ...],
    "key_challenges": ["关键挑战1", "关键挑战2"],
    "evaluation_metrics": ["评估指标1", "评估指标2"],
    "estimated_workload": "预估工作量",
    "tech_stack": ["推荐技术栈1", "推荐技术栈2"]
}}"""

        result = self._call_deepseek(prompt, temperature=0.7, max_tokens=1200)
        if result:
            return result
        return self._mock_design_doc(paper)

    def _mock_summarize(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        title = paper.get('title', '')
        summary = paper.get('summary', '')
        categories = paper.get('categories', [])
        published = paper.get('published', '')
        sentences = re.split(r'(?<=[.!?])\s+', summary)
        key_points = sentences[:3] if len(sentences) > 3 else sentences
        methods = self._extract_methods(summary)
        novelty = self._assess_novelty(title, summary)
        citations = self._estimate_citations(title, summary, published)
        impact = self._calculate_impact_factor(novelty, citations)
        return {
            'brief': ' '.join(key_points) if key_points else summary[:300],
            'methods': methods,
            'contributions': self._extract_contributions(summary),
            'datasets': self._extract_datasets(summary),
            'field': categories[0] if categories else 'Unknown',
            'novelty': novelty,
            'estimated_citations': citations,
            'impact_factor': impact,
            'is_breakthrough': novelty > 80,
            'breakthrough_reason': '该论文在方法上具有显著创新性，提出了新的研究范式' if novelty > 80 else ''
        }

    def _mock_summarize_period(self, papers: List[Dict[str, Any]], period_label: str) -> Dict[str, Any]:
        all_methods = []
        for p in papers:
            all_methods.extend(self._extract_methods(p.get('summary', '')))
        from collections import Counter
        method_counts = Counter(all_methods).most_common(5)

        return {
            'summary': f'{period_label}期间共发表{len(papers)}篇相关论文。'
                      f'主要研究方向集中在{", ".join([m[0] for m in method_counts[:3]])}等领域。'
                      f'整体来看，该时段研究活跃度{"较高" if len(papers) > 5 else "一般"}，'
                      f'出现了若干值得关注的方法创新。',
            'breakthroughs': [],
            'trends': [m[0] for m in method_counts[:3]],
            'key_methods': [m[0] for m in method_counts],
            'hot_topics': []
        }

    def _mock_design_doc(self, paper: Dict[str, Any]) -> Dict[str, Any]:
        title = paper.get('title', '')
        summary = paper.get('summary', '')
        methods = self._extract_methods(summary)
        return {
            'title': f'复现设计：{title}',
            'overview': summary[:500] + '...' if len(summary) > 500 else summary,
            'core_idea': self._extract_core_idea(summary),
            'architecture': self._generate_architecture(methods),
            'implementation_steps': [
                '搭建基础环境与依赖',
                '数据预处理与加载模块',
                '核心模型架构实现',
                '训练循环与损失函数设计',
                '评估指标与验证方法',
                '实验对比与消融研究'
            ],
            'key_challenges': self._identify_challenges(summary),
            'evaluation_metrics': self._extract_metrics(summary),
            'estimated_workload': '约2-4周（根据复杂度调整）',
            'tech_stack': ['Python', 'PyTorch', 'NumPy', 'Matplotlib']
        }

    def _extract_methods(self, summary: str) -> List[str]:
        method_keywords = ['method', 'approach', 'algorithm', 'framework', 'model', 'network',
                          'propose', 'introduce', 'present', 'design', 'develop']
        methods = []
        sentences = re.split(r'(?<=[.!?])\s+', summary)
        for sent in sentences:
            for kw in method_keywords:
                if kw.lower() in sent.lower():
                    if 30 < len(sent) < 200:
                        methods.append(sent.strip())
                    break
        return list(set(methods))[:5] if methods else ['基于深度学习的方法']

    def _extract_contributions(self, summary: str) -> List[str]:
        contrib_keywords = ['contribution', 'novel', 'first time', 'state-of-the-art', 'outperform',
                           'improve', 'advance', 'achieve']
        contributions = []
        sentences = re.split(r'(?<=[.!?])\s+', summary)
        for sent in sentences:
            for kw in contrib_keywords:
                if kw.lower() in sent.lower():
                    if 30 < len(sent) < 200:
                        contributions.append(sent.strip())
                    break
        return list(set(contributions))[:4] if contributions else ['提出了一种新的方法']

    def _extract_datasets(self, summary: str) -> List[str]:
        dataset_patterns = [r'([A-Z][a-z0-9]+(?:-[A-Za-z0-9]+)*\s+(?:dataset|benchmark))',
                           r'(?:dataset|benchmark)\s+(?:of|like|such as|including)\s+([A-Z][a-zA-Z0-9]+)']
        datasets = []
        for pattern in dataset_patterns:
            matches = re.findall(pattern, summary, re.IGNORECASE)
            datasets.extend(matches)
        return list(set(datasets))[:5] if datasets else ['标准公开数据集']

    def _extract_core_idea(self, summary: str) -> str:
        sentences = re.split(r'(?<=[.!?])\s+', summary)
        return sentences[0].strip() if sentences else summary[:200]

    def _generate_architecture(self, methods: List[str]) -> List[str]:
        archs = []
        for method in methods:
            if any(kw in method.lower() for kw in ['transformer', 'attention']):
                archs.append('Transformer架构 + 多头注意力机制')
            if any(kw in method.lower() for kw in ['cnn', 'convolution']):
                archs.append('卷积神经网络骨干')
            if any(kw in method.lower() for kw in ['gan', 'generative']):
                archs.append('生成对抗网络')
            if any(kw in method.lower() for kw in ['diffusion']):
                archs.append('扩散模型架构')
            if any(kw in method.lower() for kw in ['graph', 'gcn']):
                archs.append('图神经网络架构')
        return archs if archs else ['深度神经网络架构']

    def _identify_challenges(self, summary: str) -> List[str]:
        challenge_keywords = ['challenge', 'difficult', 'problem', 'issue', 'limitation',
                             'expensive', 'computationally', 'complex']
        challenges = []
        sentences = re.split(r'(?<=[.!?])\s+', summary)
        for sent in sentences:
            for kw in challenge_keywords:
                if kw.lower() in sent.lower():
                    if 30 < len(sent) < 150:
                        challenges.append(sent.strip())
                    break
        return list(set(challenges))[:3] if challenges else ['大规模数据处理', '模型训练效率']

    def _extract_metrics(self, summary: str) -> List[str]:
        metric_keywords = ['accuracy', 'precision', 'recall', 'f1', 'auc', 'mse', 'mae',
                          'bleu', 'rouge', 'psnr', 'ssim', 'perplexity']
        metrics = []
        for kw in metric_keywords:
            if kw.lower() in summary.lower():
                metrics.append(kw.upper())
        return metrics if metrics else ['准确率', '召回率', 'F1分数']

    def _assess_novelty(self, title: str, summary: str) -> int:
        import random
        text = (title + ' ' + summary).lower()

        base_score = 30
        score = base_score

        high_impact_keywords = [
            ('first time', 12), ('pioneering', 10), ('breakthrough', 10),
            ('state-of-the-art', 5), ('outperform', 6), ('surpass', 6),
            ('significant improvement', 4), ('novel', 5),
            ('we propose', 3), ('we introduce', 3), ('we present', 2),
            ('new paradigm', 10), ('revolutionary', 12),
            ('transformer', 3), ('attention', 2), ('diffusion', 4),
            ('graph neural', 3), ('reinforcement', 3), ('generative', 4),
            ('large language model', 5), ('foundation model', 6),
        ]

        for kw, points in high_impact_keywords:
            if kw in text:
                score += points

        method_diversity = len(set(re.findall(r'\b(match|framework|model|network|algorithm|approach|method|system)\b', text)))
        score += min(method_diversity * 2, 10)

        random.seed(hash(title) & 0xffffffff)
        noise = random.randint(-8, 8)
        score += noise

        return max(15, min(95, score))

    def _estimate_citations(self, title: str, summary: str, published: str) -> int:
        import random
        from datetime import datetime

        text = (title + ' ' + summary).lower()

        base_citations = 50

        tier1_keywords = ['breakthrough', 'first time', 'pioneering', 'revolutionary',
                          'new paradigm', 'we introduce', 'foundational']
        tier2_keywords = ['state-of-the-art', 'outperform', 'surpass', 'significant improvement',
                          'best results', 'superior', 'dominates']
        tier3_keywords = ['novel', 'we propose', 'new method', 'new approach',
                          'we present', 'innovative']
        tier4_keywords = ['transformer', 'attention mechanism', 'diffusion model',
                          'graph neural', 'reinforcement learning', 'generative',
                          'large language model', 'foundation model', 'contrastive',
                          'pre-training', 'self-supervised', 'meta-learning']

        tier1_count = sum(1 for kw in tier1_keywords if kw in text)
        tier2_count = sum(1 for kw in tier2_keywords if kw in text)
        tier3_count = sum(1 for kw in tier3_keywords if kw in text)
        tier4_count = sum(1 for kw in tier4_keywords if kw in text)

        base_citations += tier1_count * 500
        base_citations += tier2_count * 200
        base_citations += tier3_count * 80
        base_citations += tier4_count * 60

        if len(summary) > 500:
            base_citations += 30
        if len(summary) > 1000:
            base_citations += 50

        try:
            pub_date = datetime.fromisoformat(published.replace('Z', '+00:00'))
        except Exception:
            try:
                pub_date = datetime.strptime(published[:10], '%Y-%m-%d')
            except Exception:
                pub_date = datetime.now()

        years_since = max(0.5, (datetime.now() - pub_date).days / 365.0)
        # 老论文引用累积效应：每年乘以增长因子
        base_citations = int(base_citations * (0.4 + 0.6 * min(years_since / 2, 1)) * (1 + 0.3 * years_since))

        random.seed(hash(title + 'citations') & 0xffffffff)
        noise = random.randint(int(-base_citations * 0.2), int(base_citations * 0.3))
        base_citations += noise

        return max(10, base_citations)

    def _calculate_impact_factor(self, novelty: int, citations: int) -> float:
        novelty_score = novelty / 100.0
        citation_score = min(citations / 1000.0, 1.0)
        impact = 1.5 + novelty_score * 5.0 + citation_score * 3.5
        return round(min(10.0, max(1.0, impact)), 1)
