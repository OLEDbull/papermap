from flask import Blueprint, request, jsonify, send_from_directory, current_app
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import os
import logging

api_bp = Blueprint('api', __name__)
logger = logging.getLogger(__name__)

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60 per 60 seconds"],
    storage_uri="memory://"
)


@api_bp.route('/search', methods=['GET'])
@limiter.limit("30 per minute")
def search_papers():
    """搜索论文：快速返回（启发式评分）+ 后台深度AI分析"""
    query = request.args.get('q', '').strip()
    max_results = request.args.get('max', type=int)

    if not query:
        return jsonify({'error': '请输入搜索关键词'}), 400

    logger.info(f"Searching papers for query: {query}")

    try:
        use_cache = request.args.get('cache', 'true').lower() == 'true'
        if use_cache:
            cached = current_app.paper_manager.load_search(query)
            if cached:
                phase = cached.get('analysis_phase')
                if phase is None:
                    phase = 'deep'
                is_running = current_app.paper_manager._analysis_tasks.get(query, False)
                if (phase == 'fast' or phase == 'analyzing') and not is_running and phase != 'deep':
                    current_app.paper_manager.start_deep_analysis(query, top_n=30)
                logger.info(f"Returning cached results for query: {query} (phase: {phase})")
                return jsonify(cached)

        result = current_app.paper_manager.search_fast(query, max_results)
        current_app.paper_manager.start_deep_analysis(query, top_n=30)
        logger.info(f"Fast search completed: {len(result.get('papers', []))} papers found")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return jsonify({'error': '搜索过程中发生错误'}), 500


@api_bp.route('/search/status', methods=['GET'])
@limiter.limit("60 per minute")
def search_status():
    """查询搜索分析状态"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': '请输入搜索关键词'}), 400

    try:
        status = current_app.paper_manager.get_analysis_status(query)
        return jsonify(status)
    except Exception as e:
        logger.error(f"Status check error: {e}", exc_info=True)
        return jsonify({'error': '状态查询失败'}), 500


@api_bp.route('/search/refresh', methods=['GET'])
@limiter.limit("30 per minute")
def search_refresh():
    """获取最新的搜索结果（用于深度分析完成后刷新）"""
    query = request.args.get('q', '').strip()
    if not query:
        return jsonify({'error': '请输入搜索关键词'}), 400

    try:
        cached = current_app.paper_manager.load_search(query)
        if cached:
            return jsonify(cached)
        return jsonify({'error': '无搜索结果'}), 404
    except Exception as e:
        logger.error(f"Refresh error: {e}", exc_info=True)
        return jsonify({'error': '刷新失败'}), 500


@api_bp.route('/translate', methods=['GET'])
@limiter.limit("60 per minute")
def translate_keyword():
    """翻译中文关键词为英文科研术语"""
    keyword = request.args.get('q', '').strip()
    if not keyword:
        return jsonify({'error': '请输入关键词'}), 400

    try:
        translated = current_app.paper_manager.summarizer.translate_keyword(keyword)
        return jsonify({'original': keyword, 'translated': translated})
    except Exception as e:
        logger.error(f"Translation error: {e}", exc_info=True)
        return jsonify({'error': '翻译过程中发生错误'}), 500


@api_bp.route('/timeline', methods=['GET'])
@limiter.limit("30 per minute")
def get_timeline():
    """获取时间线数据"""
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': '请输入关键词'}), 400

    try:
        cached = current_app.paper_manager.load_search(query)
        if cached and 'timeline' in cached:
            return jsonify(cached['timeline'])

        result = current_app.paper_manager.search_and_analyze(query)
        return jsonify(result.get('timeline', {}))

    except Exception as e:
        logger.error(f"Timeline error: {e}", exc_info=True)
        return jsonify({'error': '获取时间线数据时发生错误'}), 500


@api_bp.route('/paper/<paper_id>/summary', methods=['GET'])
@limiter.limit("60 per minute")
def get_summary(paper_id):
    """获取论文AI摘要"""
    paper_data = None
    query = request.args.get('q', '')

    try:
        if query:
            cached = current_app.paper_manager.load_search(query)
            if cached:
                for p in cached.get('papers', []):
                    if p.get('id') == paper_id:
                        paper_data = p
                        break

        result = current_app.paper_manager.get_paper_summary(paper_id, paper_data)
        if not result:
            return jsonify({'error': '论文未找到'}), 404
        return jsonify(result)

    except Exception as e:
        logger.error(f"Summary error for paper {paper_id}: {e}", exc_info=True)
        return jsonify({'error': '获取摘要时发生错误'}), 500


@api_bp.route('/paper/<paper_id>/design', methods=['GET'])
@limiter.limit("30 per minute")
def get_design_doc(paper_id):
    """获取论文复现设计文档"""
    paper_data = None
    query = request.args.get('q', '')

    try:
        if query:
            cached = current_app.paper_manager.load_search(query)
            if cached:
                for p in cached.get('papers', []):
                    if p.get('id') == paper_id:
                        paper_data = p
                        break

        result = current_app.paper_manager.get_design_doc(paper_id, paper_data)
        if not result:
            return jsonify({'error': '论文未找到'}), 404
        return jsonify(result)

    except Exception as e:
        logger.error(f"Design doc error for paper {paper_id}: {e}", exc_info=True)
        return jsonify({'error': '获取设计文档时发生错误'}), 500


@api_bp.route('/paper/<paper_id>/download', methods=['GET'])
@limiter.limit("20 per minute")
def download_paper(paper_id):
    """下载论文PDF"""
    try:
        pdf_path = current_app.paper_manager.download_paper_pdf(paper_id)
        if pdf_path and os.path.exists(pdf_path):
            directory = os.path.dirname(pdf_path)
            filename = os.path.basename(pdf_path)
            return send_from_directory(directory, filename, as_attachment=True)
        else:
            pdf_url = f"https://arxiv.org/pdf/{paper_id}.pdf"
            return jsonify({'redirect': pdf_url}), 302

    except Exception as e:
        logger.error(f"Download error for paper {paper_id}: {e}", exc_info=True)
        return jsonify({'error': '下载论文时发生错误'}), 500


@api_bp.route('/translate_text', methods=['POST'])
@limiter.limit("60 per minute")
def translate_text():
    """翻译论文标题和摘要：英文 → 中文

    默认使用免费的 Argos Translate（离线），
    传入 use_ai=true 可使用 DeepSeek AI 高质量翻译（消耗 token）。
    """
    data = request.get_json() or {}
    text = data.get('text', '').strip()
    source_lang = data.get('source_lang', 'en')
    target_lang = data.get('target_lang', 'zh')
    use_ai = data.get('use_ai', False)

    if not text:
        return jsonify({'error': '请提供需要翻译的文本'}), 400

    try:
        translated = current_app.paper_manager.summarizer.translate_text(
            text, source_lang, target_lang, use_ai=use_ai
        )
        return jsonify({
            'original': text,
            'translated': translated,
            'source_lang': source_lang,
            'target_lang': target_lang,
            'engine': 'deepseek' if use_ai else 'free'
        })
    except Exception as e:
        logger.error(f"Translation error: {e}", exc_info=True)
        return jsonify({'error': '翻译过程中发生错误'}), 500


@api_bp.route('/translate_batch', methods=['POST'])
@limiter.limit("10 per minute")
def translate_batch():
    """批量翻译多篇论文文本：英文 → 中文（免费翻译）

    最多支持 50 条文本，逐条调用免费翻译器，避免单次请求过大或超时。
    返回每条文本的原文与译文，前端可用于替换摘要展示。
    """
    data = request.get_json() or {}
    texts = data.get('texts', [])
    source_lang = data.get('source_lang', 'en')
    target_lang = data.get('target_lang', 'zh')

    if not isinstance(texts, list) or not texts:
        return jsonify({'error': '请提供需要翻译的文本列表'}), 400

    # 限制最多 50 条，防止滥用
    if len(texts) > 50:
        return jsonify({'error': '单次最多翻译 50 条文本'}), 400

    try:
        results = []
        for text in texts:
            original = (text or '').strip()
            if not original:
                results.append({'original': '', 'translated': ''})
                continue
            translated = current_app.paper_manager.summarizer.translate_text(
                original, source_lang, target_lang, use_ai=False
            )
            results.append({'original': original, 'translated': translated})

        return jsonify({
            'results': results,
            'engine': 'free'
        })
    except Exception as e:
        logger.error(f"Batch translation error: {e}", exc_info=True)
        return jsonify({'error': '批量翻译过程中发生错误'}), 500


@api_bp.route('/statistics', methods=['GET'])
@limiter.limit("30 per minute")
def get_statistics():
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': '请输入关键词'}), 400

    try:
        cached = current_app.paper_manager.load_search(query)
        if cached and 'statistics' in cached:
            return jsonify(cached['statistics'])

        result = current_app.paper_manager.search_and_analyze(query)
        return jsonify(result.get('statistics', {}))

    except Exception as e:
        logger.error(f"Statistics error: {e}", exc_info=True)
        return jsonify({'error': '获取统计数据时发生错误'}), 500


@api_bp.route('/graph', methods=['GET'])
@limiter.limit("30 per minute")
def get_graph():
    query = request.args.get('q', '')
    if not query:
        return jsonify({'error': '请输入关键词'}), 400

    try:
        cached = current_app.paper_manager.load_search(query)
        if cached and 'graph' in cached:
            return jsonify(cached['graph'])

        result = current_app.paper_manager.search_and_analyze(query)
        return jsonify(result.get('graph', {}))

    except Exception as e:
        logger.error(f"Graph error: {e}", exc_info=True)
        return jsonify({'error': '获取关系图数据时发生错误'}), 500


@api_bp.route('/paper/<paper_id>/qa', methods=['POST'])
@limiter.limit("15 per minute")
def paper_qa(paper_id):
    """针对某篇论文进行问答"""
    data = request.get_json() or {}
    question = data.get('question', '').strip()
    history = data.get('history', [])
    query = data.get('q', '')

    if not question:
        return jsonify({'error': '请输入问题'}), 400

    try:
        paper_data = None
        if query:
            cached = current_app.paper_manager.load_search(query)
            if cached:
                for p in cached.get('papers', []):
                    if p.get('id') == paper_id:
                        paper_data = p
                        break

        result = current_app.paper_manager.answer_question(paper_id, question, paper_data, history)
        if not result:
            return jsonify({'error': '论文未找到'}), 404

        return jsonify(result)

    except Exception as e:
        logger.error(f"Q&A error for paper {paper_id}: {e}", exc_info=True)
        return jsonify({'error': '问答过程中发生错误'}), 500


@api_bp.route('/compare', methods=['POST'])
@limiter.limit("10 per minute")
def compare_papers():
    """对比两篇论文"""
    data = request.get_json() or {}
    paper_ids = data.get('paper_ids', [])
    query = data.get('q', '')

    if len(paper_ids) < 2:
        return jsonify({'error': '请选择至少两篇论文进行对比'}), 400

    try:
        papers_data = []
        if query:
            cached = current_app.paper_manager.load_search(query)
            if cached:
                for pid in paper_ids:
                    for p in cached.get('papers', []):
                        if p.get('id') == pid:
                            papers_data.append(p)
                            break

        result = current_app.paper_manager.compare_papers(paper_ids, papers_data if len(papers_data) >= 2 else None)
        if not result:
            return jsonify({'error': '对比失败，无法获取论文数据'}), 500

        return jsonify(result)

    except Exception as e:
        logger.error(f"Compare error: {e}", exc_info=True)
        return jsonify({'error': '对比过程中发生错误'}), 500
