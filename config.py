import os
from typing import Optional

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, os.getenv('DATA_DIR', 'data'))
PAPERS_DIR = os.path.join(BASE_DIR, os.getenv('PAPERS_DIR', 'data/papers'))

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(PAPERS_DIR, exist_ok=True)

LOG_DIR = os.path.join(BASE_DIR, 'logs')
os.makedirs(LOG_DIR, exist_ok=True)

DEBUG = os.getenv('FLASK_DEBUG', 'true').lower() == 'true'
FLASK_ENV = os.getenv('FLASK_ENV', 'development')
HOST = os.getenv('HOST', '0.0.0.0')
PORT = int(os.getenv('PORT', '5000'))
SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')

ARXIV_API_URL = os.getenv('ARXIV_API_URL', 'http://export.arxiv.org/api/query')
ARXIV_MAX_RESULTS = int(os.getenv('ARXIV_MAX_RESULTS', '50'))
ARXIV_SORT_BY = os.getenv('ARXIV_SORT_BY', 'submittedDate')
ARXIV_SORT_ORDER = os.getenv('ARXIV_SORT_ORDER', 'descending')

# Semantic Scholar API（覆盖期刊、顶会、综述，提供真实引用量）
S2_API_URL = os.getenv('S2_API_URL', 'https://api.semanticscholar.org/graph/v1')
S2_MAX_RESULTS = int(os.getenv('S2_MAX_RESULTS', '120'))
S2_API_KEY = os.getenv('S2_API_KEY', '')  # 可选，提升速率限制

AI_PROVIDER = os.getenv('AI_PROVIDER', 'deepseek')
AI_API_KEY = os.getenv('AI_API_KEY', '')
AI_API_URL = os.getenv('AI_API_URL', 'https://api.deepseek.com/chat/completions')
AI_MODEL = os.getenv('AI_MODEL', 'deepseek-chat')
AI_TIMEOUT = int(os.getenv('AI_TIMEOUT', '60'))
AI_MAX_TOKENS = int(os.getenv('AI_MAX_TOKENS', '2000'))
AI_TEMPERATURE = float(os.getenv('AI_TEMPERATURE', '0.7'))

REQUEST_RATE_LIMIT = int(os.getenv('REQUEST_RATE_LIMIT', '60'))
REQUEST_RATE_PERIOD = int(os.getenv('REQUEST_RATE_PERIOD', '60'))

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
LOG_FILE = os.path.join(LOG_DIR, os.getenv('LOG_FILE', 'app.log'))

assert AI_API_KEY, "AI_API_KEY must be set in .env file or environment variables"
