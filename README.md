# PaperMap - 论文知识图谱系统

一个基于 Flask 和 DeepSeek AI 的自动化论文搜集、总结与可视化知识图谱系统。

## ✨ 功能特性

- 🔍 **多源检索**：支持 arXiv 和 Semantic Scholar 双数据源，覆盖期刊、顶会、综述
- 📊 **时间线可视化**：水平时间线展示论文演进脉络，支持左右滚动
- 🤖 **AI 摘要**：基于 DeepSeek 大模型自动生成论文核心内容总结
- 🌐 **智能翻译**：集成 Argos Translate 实现离线翻译，支持中英文互译
- 🕸️ **知识图谱**：可拖动的节点图展示论文关系与方法演进
- 🔗 **关系分析**：自动识别论文间的引用关系、方法继承关系
- 📄 **批量下载**：支持论文 PDF 批量下载
- 📋 **设计文档**：自动生成论文复现的设计思路与技术方案
- ⚡ **请求限流**：内置 Flask-Limiter 防止 API 滥用
- 💾 **搜索缓存**：自动缓存搜索结果，提升响应速度

## 🚀 快速开始

### 环境要求

- Python 3.11+
- DeepSeek API Key（用于 AI 摘要和翻译）

### 安装步骤

```bash
# 1. 创建虚拟环境
python -m venv .venv

# 2. 激活虚拟环境（Windows）
.venv\Scripts\activate

# 3. 安装依赖（使用清华大学镜像源）
.venv\Scripts\python.exe -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 配置环境变量

复制 `.env.example` 为 `.env` 并配置：

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的 DeepSeek API Key：

```env
AI_API_KEY=your-deepseek-api-key-here
```

获取 API Key：https://platform.deepseek.com/

### 启动服务

```bash
python app.py
```

然后在浏览器中打开 `http://localhost:5000`

## 📁 项目结构

```
paper-knowledge-graph/
├── app.py                 # Flask 主应用
├── api.py                 # REST API 路由
├── config.py              # 配置文件
├── requirements.txt       # Python 依赖
├── wsgi.py                # WSGI 入口（生产环境）
├── Dockerfile             # Docker 配置
├── .env.example           # 环境变量模板
├── modules/
│   ├── paper_manager.py   # 论文管理核心模块
│   ├── arxiv_fetcher.py   # arXiv 论文爬取
│   ├── semantic_scholar_fetcher.py  # Semantic Scholar 爬取
│   ├── ai_summarizer.py   # AI 摘要生成
│   ├── relation_analyzer.py # 关系分析
│   └── free_translator.py # 离线翻译（Argos Translate）
├── static/
│   ├── css/style.css      # 样式文件
│   └── js/
│       ├── app.js         # 前端主逻辑
│       └── graph.js       # 知识图谱渲染
├── templates/
│   └── index.html         # HTML 模板
├── argos_packages/        # Argos Translate 离线翻译模型
├── data/                  # 数据存储目录
└── logs/                  # 日志文件目录
```

## 📡 API 接口

| 接口 | 方法 | 描述 | 限流 |
|------|------|------|------|
| `/api/search?q=<keyword>` | GET | 搜索论文 | 30/min |
| `/api/timeline?q=<keyword>` | GET | 获取时间线数据 | 30/min |
| `/api/graph?q=<keyword>` | GET | 获取知识图谱数据 | 30/min |
| `/api/paper/<id>/summary` | GET | 获取论文 AI 摘要 | 60/min |
| `/api/paper/<id>/design` | GET | 获取论文复现设计文档 | 30/min |
| `/api/paper/<id>/download` | GET | 下载论文 PDF | 20/min |
| `/api/translate?q=<keyword>` | GET | 翻译关键词 | 60/min |
| `/api/translate_text` | POST | 翻译文本 | 60/min |
| `/api/statistics?q=<keyword>` | GET | 获取统计数据 | 30/min |

### 翻译接口示例

```bash
# 翻译关键词
GET /api/translate?q=深度学习

# 翻译文本（POST）
POST /api/translate_text
Content-Type: application/json

{
    "text": "Deep learning is a subset of machine learning.",
    "source_lang": "en",
    "target_lang": "zh",
    "use_ai": false
}
```

## 🎯 使用说明

1. 在搜索框输入研究领域关键词（如 "transformer", "diffusion model"）
2. 点击搜索，系统自动搜集论文并生成时间线和知识图谱
3. 水平时间线支持左右滚动，点击论文节点查看详情
4. 知识图谱支持节点拖动，展示论文间的引用和方法继承关系
5. 支持 AI 摘要、PDF 下载、生成设计文档等功能
6. 搜索结果自动缓存，重复搜索无需重新请求

## 🔧 配置说明

### 环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `FLASK_ENV` | development | 运行环境 |
| `FLASK_DEBUG` | true | 调试模式 |
| `HOST` | 0.0.0.0 | 监听地址 |
| `PORT` | 5000 | 监听端口 |
| `AI_API_KEY` | - | DeepSeek API Key（必填） |
| `AI_MODEL` | deepseek-chat | AI 模型 |
| `ARXIV_MAX_RESULTS` | 200 | arXiv 最大返回数 |
| `S2_MAX_RESULTS` | 120 | Semantic Scholar 最大返回数 |
| `REQUEST_RATE_LIMIT` | 60 | 请求速率限制 |

## 🐳 Docker 部署

```bash
# 构建镜像
docker build -t papermap .

# 运行容器
docker run -p 5000:5000 \
  -e AI_API_KEY=your-api-key \
  papermap
```

## 📝 技术栈

- **后端**：Flask 3.1 + Flask-CORS + Flask-Limiter
- **前端**：HTML5 + CSS3 + JavaScript (原生)
- **AI**：DeepSeek Chat API
- **翻译**：Argos Translate（离线）+ Deep Translator
- **数据来源**：arXiv API + Semantic Scholar API
- **部署**：Gunicorn + Docker

## 📄 许可证

MIT License