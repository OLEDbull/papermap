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


@api_bp.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'service': 'PaperMap'}), 200


@api_bp.route('/search', methods=['GET'])
@limiter.limit("30 per minute")
def search_papers():
    """搜索论文：中文关键词自动翻译 → arXiv检索 → 时间排序 → 时间线总结"""
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
                logger.info(f"Returning cached results for query: {query}")
                return jsonify(cached)

        result = current_app.paper_manager.search_and_analyze(query, max_results)
        logger.info(f"Search completed: {len(result.get('papers', []))} papers found")
        return jsonify(result)

    except Exception as e:
        logger.error(f"Search error: {e}", exc_info=True)
        return jsonify({'error': '搜索过程中发生错误'}), 500


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
