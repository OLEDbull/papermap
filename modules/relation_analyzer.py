import re
import logging
from datetime import datetime
from collections import defaultdict
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)


class RelationAnalyzer:
    def __init__(self) -> None:
        self.method_categories: Dict[str, List[str]] = {
            'transformer': ['transformer', 'attention', 'self-attention', 'multi-head', 'bert', 'gpt'],
            'cnn': ['cnn', 'convolution', 'resnet', 'vgg', 'inception', 'unet'],
            'rnn': ['rnn', 'lstm', 'gru', 'recurrent', 'sequence'],
            'gan': ['gan', 'generative adversarial', 'discriminator', 'generator'],
            'diffusion': ['diffusion', 'ddpm', 'ddim', 'score-based'],
            'graph': ['graph', 'gcn', 'gat', 'gnn', 'node', 'edge'],
            'reinforcement': ['reinforcement', 'policy gradient', 'q-learning', 'actor-critic'],
            'bayesian': ['bayesian', 'variational', 'mcmc', 'posterior', 'prior'],
            'optimization': ['optimization', 'gradient descent', 'adam', 'sgd', 'optimizer'],
            'self-supervised': ['self-supervised', 'contrastive', 'pretext', 'pretrain']
        }

    def analyze_relations(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        nodes: List[Dict[str, Any]] = []
        links: List[Dict[str, Any]] = []
        node_map: Dict[str, int] = {}

        sorted_papers = sorted(papers, key=lambda x: x.get('published', ''), reverse=False)

        for i, paper in enumerate(sorted_papers):
            paper_id = paper.get('id', str(i))
            node_map[paper_id] = i

            methods = self._identify_methods(paper)
            category = self._categorize_paper(paper, methods)
            year = self._extract_year(paper)

            node = {
                'id': paper_id,
                'title': paper.get('title', ''),
                'authors': paper.get('authors', []),
                'published': paper.get('published', ''),
                'year': year,
                'summary': paper.get('summary', '')[:200],
                'categories': paper.get('categories', []),
                'methods': methods,
                'category': category,
                'citation_count': 0,
                'pdf_url': paper.get('pdf_url', ''),
                'abs_url': paper.get('abs_url', ''),
                'size': 20 + len(methods) * 2
            }
            nodes.append(node)

        links = self._build_relations(nodes, node_map)
        logger.info(f"Analyzed {len(nodes)} nodes and {len(links)} links")

        return {'nodes': nodes, 'links': links}

    def _identify_methods(self, paper: Dict[str, Any]) -> List[str]:
        text = paper.get('title', '') + ' ' + paper.get('summary', '')
        text_lower = text.lower()

        found_methods = []
        for category, keywords in self.method_categories.items():
            for kw in keywords:
                if kw.lower() in text_lower:
                    found_methods.append(category)
                    break

        if not found_methods:
            found_methods = ['deep learning']

        return list(set(found_methods))

    def _categorize_paper(self, paper: Dict[str, Any], methods: List[str]) -> str:
        if methods:
            return methods[0]
        categories = paper.get('categories', [])
        if categories:
            cat = categories[0].split('.')[0]
            cat_map = {
                'cs': 'Computer Science',
                'physics': 'Physics',
                'math': 'Mathematics',
                'stat': 'Statistics',
                'q-bio': 'Biology',
                'q-fin': 'Finance',
                'eess': 'Electrical Engineering',
                'econ': 'Economics'
            }
            return cat_map.get(cat, cat)
        return 'Unknown'

    def _extract_year(self, paper: Dict[str, Any]) -> int:
        published = paper.get('published', '')
        if published:
            try:
                dt = datetime.fromisoformat(published)
                return dt.year
            except Exception:
                match = re.search(r'(\d{4})', published)
                if match:
                    return int(match.group(1))
        return 2024

    def _build_relations(self, nodes: List[Dict[str, Any]], node_map: Dict[str, int]) -> List[Dict[str, Any]]:
        links = []
        link_set = set()

        method_papers = defaultdict(list)
        for node in nodes:
            for method in node['methods']:
                method_papers[method].append(node['id'])

        for method, paper_ids in method_papers.items():
            if len(paper_ids) > 1:
                for i in range(len(paper_ids)):
                    for j in range(i + 1, len(paper_ids)):
                        source = paper_ids[i]
                        target = paper_ids[j]
                        link_key = tuple(sorted([source, target]))
                        if link_key not in link_set:
                            link_set.add(link_key)
                            links.append({
                                'source': source,
                                'target': target,
                                'type': 'method',
                                'label': method,
                                'value': 1
                            })
                        else:
                            for link in links:
                                if (link['source'] == source and link['target'] == target) or \
                                   (link['source'] == target and link['target'] == source):
                                    link['value'] += 1
                                    break

        author_papers = defaultdict(list)
        for node in nodes:
            for author in node['authors'][:3]:
                author_papers[author].append(node['id'])

        for author, paper_ids in author_papers.items():
            if len(paper_ids) > 1:
                for i in range(len(paper_ids)):
                    for j in range(i + 1, len(paper_ids)):
                        source = paper_ids[i]
                        target = paper_ids[j]
                        link_key = tuple(sorted([source, target, 'author']))
                        if link_key not in link_set:
                            link_set.add(link_key)
                            links.append({
                                'source': source,
                                'target': target,
                                'type': 'author',
                                'label': author,
                                'value': 1
                            })

        for i, node_i in enumerate(nodes):
            title_i_words = set(re.findall(r'\w+', node_i['title'].lower()))
            for j, node_j in enumerate(nodes):
                if i >= j:
                    continue
                title_j_words = set(re.findall(r'\w+', node_j['title'].lower()))
                common_words = title_i_words & title_j_words
                common_words = {w for w in common_words if len(w) > 4}
                if len(common_words) >= 2:
                    source = node_i['id']
                    target = node_j['id']
                    link_key = tuple(sorted([source, target, 'topic']))
                    if link_key not in link_set:
                        link_set.add(link_key)
                        links.append({
                            'source': source,
                            'target': target,
                            'type': 'topic',
                            'label': ', '.join(list(common_words)[:3]),
                            'value': len(common_words)
                        })

        year_papers = defaultdict(list)
        for node in nodes:
            year_papers[node['year']].append(node['id'])

        sorted_years = sorted(year_papers.keys())
        for yi in range(len(sorted_years) - 1):
            prev_year = sorted_years[yi]
            curr_year = sorted_years[yi + 1]
            for prev_id in year_papers[prev_year][:5]:
                for curr_id in year_papers[curr_year][:5]:
                    prev_node = nodes[node_map[prev_id]]
                    curr_node = nodes[node_map[curr_id]]
                    common_methods = set(prev_node['methods']) & set(curr_node['methods'])
                    if common_methods:
                        link_key = tuple(sorted([prev_id, curr_id, 'timeline']))
                        if link_key not in link_set:
                            link_set.add(link_key)
                            links.append({
                                'source': prev_id,
                                'target': curr_id,
                                'type': 'timeline',
                                'label': 'follows',
                                'value': 2
                            })

        return links

    def get_method_statistics(self, papers: List[Dict[str, Any]]) -> Dict[str, Any]:
        method_counts = defaultdict(int)
        year_method_counts = defaultdict(lambda: defaultdict(int))

        for paper in papers:
            methods = self._identify_methods(paper)
            year = self._extract_year(paper)
            for method in methods:
                method_counts[method] += 1
                year_method_counts[year][method] += 1

        return {
            'method_counts': dict(method_counts),
            'year_method_counts': {str(k): dict(v) for k, v in year_method_counts.items()}
        }
