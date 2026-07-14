import urllib.request
import urllib.parse
import feedparser
import time
from datetime import datetime
import config


class ArxivFetcher:
    def __init__(self):
        self.base_url = config.ARXIV_API_URL
        self.max_results = config.ARXIV_MAX_RESULTS

    def search_papers(self, query, max_results=None, start=0):
        if max_results is None:
            max_results = self.max_results

        all_papers = []
        seen_ids = set()

        # 按日期范围分批搜索，确保覆盖不同年代
        date_ranges = self._build_date_ranges()

        per_range = max(10, max_results // len(date_ranges))

        for date_range in date_ranges:
            if len(all_papers) >= max_results:
                break

            remaining = max_results - len(all_papers)
            batch_size = min(per_range, remaining)

            papers = self._fetch_batch(query, start=0, max_results=batch_size, date_range=date_range)
            for p in papers:
                if p['id'] not in seen_ids:
                    seen_ids.add(p['id'])
                    all_papers.append(p)

            time.sleep(1)  # arXiv API rate limit

        all_papers.sort(key=lambda x: x.get('published', ''), reverse=False)
        return all_papers

    def _build_date_ranges(self):
        """构建日期范围列表，覆盖最近8年"""
        now = datetime.now()
        ranges = []

        # 最近1年
        ranges.append((now.replace(year=now.year - 1), now))
        # 1-3年前
        ranges.append((now.replace(year=now.year - 3), now.replace(year=now.year - 1)))
        # 3-5年前
        ranges.append((now.replace(year=now.year - 5), now.replace(year=now.year - 3)))
        # 5-8年前
        end_5 = now.replace(year=now.year - 5)
        start_8 = now.replace(year=now.year - 8)
        ranges.append((start_8, end_5))

        return ranges

    def _format_date_for_arxiv(self, dt):
        """格式化日期为arXiv API格式: YYYYMMDDhhmm"""
        return dt.strftime('%Y%m%d%H%M')

    def _needs_more_papers(self, papers):
        if len(papers) < 5:
            return True
        try:
            dates = []
            for p in papers:
                dt = datetime.fromisoformat(p['published'].replace('Z', '+00:00'))
                dates.append(dt)
            span_days = (max(dates) - min(dates)).days
            return span_days < 730
        except Exception:
            return True

    def _fetch_batch(self, query, start, max_results, date_range=None):
        search_query = f'all:{query}'

        if date_range:
            start_str = self._format_date_for_arxiv(date_range[0])
            end_str = self._format_date_for_arxiv(date_range[1])
            search_query = f'all:{query} AND submittedDate:[{start_str} TO {end_str}]'

        params = {
            'search_query': search_query,
            'start': start,
            'max_results': max_results,
            'sortBy': 'relevance',
            'sortOrder': 'descending'
        }

        url = f"{self.base_url}?{urllib.parse.urlencode(params)}"

        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 PaperKnowledgeGraph/1.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    data = response.read()
                feed = feedparser.parse(data)
                papers = []
                for entry in feed.entries:
                    paper = self._parse_entry(entry)
                    papers.append(paper)
                return papers
            except Exception as e:
                print(f"Batch error (attempt {attempt + 1}): {e}")
                if attempt < 2:
                    time.sleep(3)
        return []

    def _parse_entry(self, entry):
        paper_id = entry.id.split('/abs/')[-1] if '/abs/' in entry.id else entry.id
        published = datetime(*entry.published_parsed[:6]) if hasattr(entry, 'published_parsed') else datetime.now()
        updated = datetime(*entry.updated_parsed[:6]) if hasattr(entry, 'updated_parsed') else published

        authors = []
        if hasattr(entry, 'authors'):
            authors = [author.get('name', '') for author in entry.authors]

        categories = []
        if hasattr(entry, 'tags'):
            categories = [tag.get('term', '') for tag in entry.tags]

        pdf_link = ''
        for link in entry.links:
            if link.get('title', '') == 'pdf':
                pdf_link = link.href
                break
        if not pdf_link:
            pdf_link = f"https://arxiv.org/pdf/{paper_id}.pdf"

        summary = entry.summary if hasattr(entry, 'summary') else ''
        summary = summary.replace('\n', ' ').strip()

        return {
            'id': paper_id,
            'title': entry.title.replace('\n', ' ').strip(),
            'authors': authors,
            'summary': summary,
            'published': published.isoformat(),
            'updated': updated.isoformat(),
            'categories': categories,
            'pdf_url': pdf_link,
            'abs_url': entry.id,
            'doi': entry.get('arxiv_doi', ''),
            'comment': entry.get('arxiv_comment', ''),
            'journal_ref': entry.get('arxiv_journal_ref', '')
        }

    def get_paper_by_id(self, paper_id):
        params = {
            'id_list': paper_id,
            'max_results': 1
        }
        url = f"{self.base_url}?{urllib.parse.urlencode(params)}"
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read()
            feed = feedparser.parse(data)
            if feed.entries:
                return self._parse_entry(feed.entries[0])
            return None
        except Exception as e:
            print(f"Error fetching paper {paper_id}: {e}")
            return None

    def download_pdf(self, paper_id, save_path):
        pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
        try:
            import os
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            urllib.request.urlretrieve(pdf_url, save_path)
            return True
        except Exception as e:
            print(f"Error downloading PDF {paper_id}: {e}")
            return False
