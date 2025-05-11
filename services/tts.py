import logging
from edge_tts import Communicate
import tempfile
import os
import asyncio
from typing import Dict
from pathlib import Path
from contextlib import asynccontextmanager
from exceptions import TTSError
from config.settings import settings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TTSService:
    def __init__(self):
        # 使用settings的TTS配置
        tts_config = settings.TTS
        
        # 从配置获取语音设置
        self.voices = tts_config['voices']
        self.rate = tts_config['rate']
        self.volume = tts_config['volume']
        self.pitch = tts_config['pitch']
        
        # 设置临时目录
        self._temp_dir = Path(tts_config['temp_dir'])
        self._temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 清理配置
        self._cleanup_max_age = tts_config['cleanup']['max_age_hours']
        self._cleanup_task = None
        
        logger.info("TTS服务初始化完成")
        logger.info(f"使用语音配置: {self.voices}")
        logger.info(f"语速: {self.rate}, 音量: {self.volume}, 音调: {self.pitch}")

    @asynccontextmanager
    async def _get_temp_file(self, suffix: str = '.mp3'):
        """创建临时文件的上下文管理器"""
        temp_path = self._temp_dir / f"{os.urandom(8).hex()}{suffix}"
        try:
            yield temp_path
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception as e:
                logger.warning(f"清理临时文件失败 {temp_path}: {e}")

    async def _cleanup_old_files(self):
        """清理旧的临时文件"""
        try:
            current_time = asyncio.get_event_loop().time()
            for file_path in self._temp_dir.glob("*"):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > self._cleanup_max_age * 3600:
                        try:
                            file_path.unlink()
                        except Exception as e:
                            logger.warning(f"清理旧文件失败 {file_path}: {e}")
        except Exception as e:
            logger.error(f"清理临时文件失败: {e}")

    def _clean_text(self, text: str) -> str:
        """Remove markdown-style asterisks from text."""
        return text.replace('*', '')

    async def synthesize(self, text: str) -> bytes:
        """合成语音的主方法"""
        if not text or not text.strip():
            raise TTSError("输入文本不能为空")

        text = self._clean_text(text)
        lang = self._detect_language(text)
        
        try:
            logger.info(f"开始合成语音: {text[:50]}...")
            logger.info(
                f"使用参数: voice={self.voices[lang]}, rate={self.rate}, volume={self.volume}, pitch={self.pitch}")

            async with self._get_temp_file() as temp_path:
                communicate = Communicate(
                    text,
                    voice=self.voices[lang],
                    rate=self.rate,
                    volume=self.volume,
                    pitch=self.pitch,
                )

                try:
                    await communicate.save(str(temp_path))
                    return await self._read_audio_file(temp_path)
                except Exception as e:
                    raise TTSError(f"语音合成失败: {str(e)}")

        except Exception as e:
            logger.error(f"语音合成失败: {str(e)}")
            raise TTSError(f"语音合成失败: {str(e)}")

    async def _read_audio_file(self, file_path: Path) -> bytes:
        """异步读取音频文件"""
        try:
            async with asyncio.Lock():
                with open(file_path, 'rb') as f:
                    return f.read()
        except Exception as e:
            raise TTSError(f"读取音频文件失败: {str(e)}")

    def _detect_language(self, text: str) -> str:
        """基于启发式规则的语言检测"""
        if not text:
            return "zh"  # 默认使用中文

        # 计算ASCII字符比例
        en_chars = sum(c.isascii() for c in text)
        total_chars = len(text)

        # 如果文本太短，使用更保守的阈值
        if total_chars < 10:
            return "en" if en_chars / total_chars > 0.8 else "zh"

        return "en" if en_chars / total_chars > 0.6 else "zh"

    def _normalize_rate(self, value: str) -> str:
        """标准化语速值"""
        return self._normalize_percentage(value, "+0%")

    def _normalize_volume(self, value: str) -> str:
        """标准化音量值"""
        return self._normalize_percentage(value, "+0%")

    def _normalize_pitch(self, value: str) -> str:
        """标准化音调值"""
        try:
            value = value.strip()
            if value.endswith('Hz'):
                if not value.startswith(('+', '-')):
                    value = '+' + value
                return value

            num_value = float(value)
            return f"{'+' if num_value >= 0 else ''}{num_value}Hz"
        except Exception as e:
            logger.error(f"标准化音调值失败: {str(e)}")
            return "+0Hz"

    def _normalize_percentage(self, value: str, default: str) -> str:
        """通用的百分比值标准化"""
        try:
            value = value.strip()
            if value.endswith('%'):
                if not value.startswith(('+', '-')):
                    value = '+' + value
                return value

            num_value = float(value)
            return f"{'+' if num_value >= 0 else ''}{num_value}%"
        except Exception as e:
            logger.error(f"标准化百分比值失败: {str(e)}")
            return default

    async def cleanup(self):
        """清理资源"""
        try:
            await self._cleanup_old_files()
        except Exception as e:
            logger.error(f"清理资源失败: {str(e)}")


if __name__ == '__main__':
    async def test_tts():
        tts = TTSService()
        try:
            audio_data = await tts.synthesize("你好，我是ChatGPT")
            print(f"合成成功，音频大小: {len(audio_data)} bytes")
        except Exception as e:
            print(f"测试失败: {e}")
        finally:
            await tts.cleanup()


    asyncio.run(test_tts())
