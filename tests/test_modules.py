import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.ai_summarizer import AISummarizer
from modules.relation_analyzer import RelationAnalyzer


class TestAISummarizer:
    def setup_method(self):
        self.summarizer = AISummarizer()

    def test_is_english(self):
        assert self.summarizer._is_english("transformer") is True
        assert self.summarizer._is_english("diffusion model") is True
        assert self.summarizer._is_english("大语言模型") is False
        assert self.summarizer._is_english("machine learning") is True

    def test_local_translate(self):
        assert self.summarizer._local_translate("大语言模型") == "large language model"
        assert self.summarizer._local_translate("扩散模型") == "diffusion model"
        assert self.summarizer._local_translate("transformer") == "transformer"
        assert self.summarizer._local_translate("unknown") == "unknown"

    def test_extract_methods(self):
        summary = "We propose a novel transformer-based approach with self-attention mechanism."
        methods = self.summarizer._extract_methods(summary)
        assert len(methods) > 0

    def test_summarize_paper_mock(self):
        paper = {
            'title': 'Test Paper',
            'summary': 'This is a test paper summary.',
            'categories': ['cs.CL']
        }
        result = self.summarizer.summarize_paper(paper)
        assert 'brief' in result
        assert 'methods' in result
        assert 'contributions' in result


class TestRelationAnalyzer:
    def setup_method(self):
        self.analyzer = RelationAnalyzer()

    def test_identify_methods(self):
        paper = {
            'title': 'Transformer-based Image Generation',
            'summary': 'Using transformer architecture for image generation tasks.'
        }
        methods = self.analyzer._identify_methods(paper)
        assert 'transformer' in methods

    def test_categorize_paper(self):
        paper = {'categories': ['cs.CL']}
        category = self.analyzer._categorize_paper(paper, [])
        assert category == 'Computer Science'

    def test_extract_year(self):
        paper = {'published': '2024-05-15T00:00:00'}
        year = self.analyzer._extract_year(paper)
        assert year == 2024

    def test_analyze_relations(self):
        papers = [
            {
                'id': '1',
                'title': 'Transformer Paper',
                'summary': 'Transformer-based approach.',
                'authors': ['Author A'],
                'published': '2024-01-01',
                'categories': ['cs.CL']
            },
            {
                'id': '2',
                'title': 'Another Transformer Paper',
                'summary': 'Another transformer method.',
                'authors': ['Author A'],
                'published': '2024-02-01',
                'categories': ['cs.CL']
            }
        ]
        result = self.analyzer.analyze_relations(papers)
        assert 'nodes' in result
        assert 'links' in result
        assert len(result['nodes']) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
