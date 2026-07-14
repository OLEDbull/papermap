import os
import sys
import logging
from logging.handlers import RotatingFileHandler

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from flask import Flask, render_template, jsonify
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

import config
from modules.paper_manager import PaperManager
from api import api_bp


def create_app(config_obj=None):
    app = Flask(__name__,
                static_folder='static',
                template_folder='templates')

    app.config['SECRET_KEY'] = config.SECRET_KEY

    if config_obj:
        app.config.from_object(config_obj)

    _setup_logging(app)
    _setup_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_global_objects(app)

    try:
        from whitenoise import WhiteNoise
        app.wsgi_app = WhiteNoise(app.wsgi_app, root='static/', prefix='static/')
    except ImportError:
        pass

    return app


def _setup_logging(app):
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, config.LOG_LEVEL))

    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s'
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    file_handler = RotatingFileHandler(
        config.LOG_FILE,
        maxBytes=1024 * 1024 * 10,
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    app.logger.info(f"Application initialized with {config.FLASK_ENV} environment")


def _setup_extensions(app):
    CORS(app, resources={r'/api/*': {'origins': '*'}})

    Limiter(
        app=app,
        key_func=get_remote_address,
        default_limits=[f"{config.REQUEST_RATE_LIMIT} per {config.REQUEST_RATE_PERIOD} seconds"]
    )


def _register_blueprints(app):
    app.register_blueprint(api_bp, url_prefix='/api')


def _register_error_handlers(app):
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({'error': '请求参数错误'}), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({'error': '资源未找到'}), 404

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        return jsonify({'error': '请求过于频繁，请稍后重试'}), 429

    @app.errorhandler(500)
    def internal_error(error):
        app.logger.error(f"Internal error: {error}")
        return jsonify({'error': '服务器内部错误'}), 500


def _register_global_objects(app):
    app.paper_manager = PaperManager()

    @app.route('/')
    def index():
        return render_template('index.html')


app = create_app()

if __name__ == '__main__':
    print("=" * 60)
    print("  论文知识图谱系统 (DeepSeek AI 驱动)")
    print(f"  访问地址: http://localhost:{config.PORT}")
    print(f"  AI模型: {config.AI_MODEL}")
    print(f"  环境: {config.FLASK_ENV}")
    print("=" * 60)

    app.run(
        host=config.HOST,
        port=config.PORT,
        debug=config.DEBUG
    )
