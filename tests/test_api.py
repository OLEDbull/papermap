import os
import sys
import pytest
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app


class TestAPI:
    def setup_method(self):
        self.app = create_app()
        self.client = self.app.test_client()

    def test_index_page(self):
        response = self.client.get('/')
        assert response.status_code == 200

    def test_search_without_query(self):
        response = self.client.get('/api/search')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_translate_without_query(self):
        response = self.client.get('/api/translate')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_timeline_without_query(self):
        response = self.client.get('/api/timeline')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_graph_without_query(self):
        response = self.client.get('/api/graph')
        assert response.status_code == 400
        data = response.get_json()
        assert 'error' in data

    def test_search_success(self):
        response = self.client.get('/api/search?q=test&max=5')
        assert response.status_code == 200
        data = response.get_json()
        assert 'papers' in data
        assert 'timeline' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
