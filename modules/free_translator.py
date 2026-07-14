import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class FreeTranslator:
    """免费翻译器：使用 Argos Translate（离线）或 LibreTranslate（在线免费 API）

    优先使用 Argos Translate（完全离线，不消耗任何 API token），
    如果 Argos 不可用，则尝试 LibreTranslate 公共 API。
    """

    def __init__(self) -> None:
        self._argos_available: bool = False
        self._argos_translate = None
        self._installed_packages: list = []
        self._init_argos()

    def _init_argos(self) -> None:
        """初始化 Argos Translate，下载必要的语言包"""
        try:
            import argostranslate.package
            import argostranslate.translate
            import argostranslate.settings

            # 将语言包缓存到项目目录内，避免系统目录权限问题
            project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            package_dir = os.path.join(project_dir, 'argos_packages')
            os.makedirs(package_dir, exist_ok=True)
            argostranslate.settings.package_data_dir = package_dir

            self._argos_translate = argostranslate.translate
            installed = argostranslate.package.get_installed_packages()

            # 检查是否已安装 en->zh 和 zh->en
            has_en_zh = any(p.from_code == 'en' and p.to_code == 'zh' for p in installed)
            has_zh_en = any(p.from_code == 'zh' and p.to_code == 'en' for p in installed)

            if not has_en_zh or not has_zh_en:
                logger.info("Downloading Argos Translate language packages...")
                argostranslate.package.update_package_index()
                available = argostranslate.package.get_available_packages()

                # 手动下载到项目目录，避免系统缓存目录权限问题
                download_dir = os.path.join(package_dir, 'downloads')
                os.makedirs(download_dir, exist_ok=True)

                if not has_en_zh:
                    pkg = next((p for p in available if p.from_code == 'en' and p.to_code == 'zh'), None)
                    if pkg:
                        model_path = os.path.join(download_dir, 'translate-en_zh.argosmodel')
                        self._download_file(pkg.links[0], model_path)
                        argostranslate.package.install_from_path(model_path)
                        logger.info("Installed en->zh language package")

                if not has_zh_en:
                    pkg = next((p for p in available if p.from_code == 'zh' and p.to_code == 'en'), None)
                    if pkg:
                        model_path = os.path.join(download_dir, 'translate-zh_en.argosmodel')
                        self._download_file(pkg.links[0], model_path)
                        argostranslate.package.install_from_path(model_path)
                        logger.info("Installed zh->en language package")

            self._installed_packages = argostranslate.package.get_installed_packages()
            self._argos_available = len(self._installed_packages) > 0

            if self._argos_available:
                logger.info(f"Argos Translate ready with {len(self._installed_packages)} language packages")

        except Exception as e:
            logger.warning(f"Argos Translate initialization failed: {e}")
            self._argos_available = False

    def translate(self, text: str, source_lang: str = 'en', target_lang: str = 'zh') -> str:
        """翻译文本，优先使用 Argos Translate"""
        if not text or not text.strip():
            return ''

        # 1. 尝试 Argos Translate（离线，完全免费）
        if self._argos_available and self._argos_translate:
            try:
                result = self._argos_translate.translate(text, source_lang, target_lang)
                if result and result != text:
                    return result.strip()
            except Exception as e:
                logger.warning(f"Argos Translate failed: {e}")

        # 2. 尝试 LibreTranslate 公共 API（在线免费）
        try:
            return self._libre_translate(text, source_lang, target_lang)
        except Exception as e:
            logger.warning(f"LibreTranslate failed: {e}")

        # 3. 全部失败，返回原文
        logger.warning("All free translators failed, returning original text")
        return text

    def _libre_translate(self, text: str, source: str, target: str) -> str:
        """使用 LibreTranslate 公共 API（有免费额度限制）"""
        import requests

        # 公共免费实例列表（可能会变更）
        endpoints = [
            "https://libretranslate.de/translate",
            "https://libretranslate.pussthecat.org/translate",
            "https://translate.argosopentech.com/translate",
        ]

        payload = {
            "q": text,
            "source": source,
            "target": target,
            "format": "text"
        }

        for url in endpoints:
            try:
                response = requests.post(url, data=payload, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    translated = data.get("translatedText", "")
                    if translated:
                        return translated.strip()
                elif response.status_code == 429:
                    logger.debug(f"LibreTranslate rate limited: {url}")
                    continue
            except Exception as e:
                logger.debug(f"LibreTranslate endpoint failed {url}: {e}")
                continue

        raise Exception("All LibreTranslate endpoints failed")

    def _download_file(self, url: str, dest: str) -> None:
        """手动下载文件，避免 Argos 默认缓存目录权限问题"""
        import requests
        import shutil
        response = requests.get(url, stream=True, timeout=60)
        response.raise_for_status()
        with open(dest, 'wb') as f:
            shutil.copyfileobj(response.raw, f)

    def is_available(self) -> bool:
        """检查是否有可用的免费翻译器"""
        return self._argos_available
