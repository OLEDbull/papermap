# 论文知识图谱系统 (Paper Knowledge Graph)

一个自动化的论文搜集、总结与可视化知识图谱系统。

## ✨ 功能特性

- 🔍 **领域检索**：输入研究领域关键词，自动从arXiv搜集相关论文
- 📊 **时间排序**：按发表时间自动排序，追踪领域发展脉络
- 🤖 **AI摘要**：自动生成论文核心内容总结
- 🕸️ **知识图谱**：可拖动的节点图展示论文关系与方法演进
- 🔗 **关系分析**：自动识别论文间的引用关系、方法继承关系
- 📄 **批量下载**：支持论文PDF批量下载
- 📋 **设计文档**：自动生成论文复现的设计思路与技术方案

## 🚀 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 启动服务

```bash
python app.py
```

然后在浏览器中打开 `http://localhost:5000`

## 📁 项目结构

```
paper-knowledge-graph/
├── app.py                 # Flask主应用
├── requirements.txt       # Python依赖
├── config.py              # 配置文件
├── modules/
│   ├── arxiv_fetcher.py   # arXiv论文爬取模块
│   ├── ai_summarizer.py   # AI摘要模块
│   ├── relation_analyzer.py # 关系分析模块
│   └── paper_manager.py   # 论文管理模块
├── static/
│   ├── css/
│   └── js/
├── templates/
│   └── index.html
└── data/                  # 数据存储目录
```

## 🎯 使用说明

1. 在搜索框输入研究领域关键词（如 "transformer", "diffusion model"）
2. 点击搜索，系统自动搜集论文并生成知识图谱
3. 拖动节点查看论文关系，点击节点查看论文详情
4. 支持AI摘要、下载PDF、生成设计文档等功能
