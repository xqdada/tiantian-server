import os
import logging
import subprocess
import tempfile
from pathlib import Path
from funasr import AutoModel
from funasr.utils.postprocess_utils import rich_transcription_postprocess
from exceptions import ASRError, FFmpegError
from config.settings import settings

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FFmpegProcessor:
    """FFmpeg 音频处理类"""
    def __init__(self):
        self._check_ffmpeg()
        # 从配置管理器获取音频配置
        audio_config = settings.ASR_AUDIO
        self.target_sr = audio_config.get('target_sr', 16000)
        self.channels = audio_config.get('channels', 1)
        self.sample_width = audio_config.get('sample_width', 2)

    def _check_ffmpeg(self) -> None:
        """检查 FFmpeg 是否可用"""
        try:
            subprocess.run(
                ["ffmpeg", "-version"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            raise FFmpegError(
                "FFmpeg 未安装或未配置 PATH\n"
                "请从 https://ffmpeg.org 下载并添加到系统环境变量"
            )

    def process_audio(self, audio_data: bytes, input_format: str = "opus") -> bytes:
        """使用 FFmpeg 处理音频数据"""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # 保存输入数据
            input_path = Path(tmp_dir) / f"input.{input_format}"
            with open(input_path, "wb") as f:
                f.write(audio_data)

            # 转换为目标格式
            output_path = Path(tmp_dir) / "output.wav"
            self._convert_audio(input_path, output_path)

            # 读取处理后的数据
            return self._read_wav(output_path)

    def _convert_audio(self, input_path: Path, output_path: Path) -> None:
        """执行 FFmpeg 转换命令"""
        cmd = [
            "ffmpeg",
            "-y",  # 覆盖输出文件
            "-i", str(input_path),
            "-acodec", "pcm_s16le",  # 16-bit PCM
            "-ar", str(self.target_sr),  # 采样率
            "-ac", str(self.channels),  # 声道数
            "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",  # 音频标准化
            "-hide_banner",
            "-loglevel", "error",
            str(output_path)
        ]

        try:
            proc = subprocess.run(
                cmd,
                check=True,
                capture_output=True,
                text=True
            )
            if proc.returncode != 0:
                raise FFmpegError(f"音频转换失败: {proc.stderr}")

            logger.info(f"音频转换成功: {output_path}")

        except subprocess.CalledProcessError as e:
            raise FFmpegError(f"音频转换失败: {e.stderr}")

    def _read_wav(self, path: Path) -> bytes:
        """读取 WAV 文件数据"""
        try:
            with open(path, "rb") as f:
                return f.read()

        except Exception as e:
            raise FFmpegError(f"读取 WAV 文件失败: {str(e)}")


class ASRService:
    """语音识别服务"""
    def __init__(self):
        """初始化 ASR 服务"""
        self.ffmpeg = FFmpegProcessor()

        # 从配置管理器获取ASR配置
        asr_config = settings.ASR
        try:
            self.model = AutoModel(
                model=asr_config.get('model'),
                disable_update=True,
                vad_model=asr_config.get('vad_model'),
                vad_kwargs=asr_config.get('vad_params'),
                device=asr_config.get('device', 'cpu')
            )
            logger.info(f"ASR模型初始化成功: {asr_config.get('model')}")
        except Exception as e:
            raise ASRError(f"ASR 模型初始化失败: {str(e)}")

    async def transcribe(self, audio_data: bytes, input_format: str = "opus") -> str:
        """语音识别主流程"""
        try:
            # 1. 音频预处理
            processed_audio = self.ffmpeg.process_audio(audio_data, input_format)

            # 2. 保存临时文件
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as temp_file:
                temp_file.write(processed_audio)
                temp_path = temp_file.name

            try:
                # 3. 执行语音识别
                result = self.model.generate(
                    input=temp_path,
                    cache={},
                    hotword='甜甜',
                    use_itn=True,
                    language="auto",
                    batch_size_s=60,
                    merge_vad=True,
                    merge_length_s=15,
                )

                if not result or len(result) == 0:
                    return "未能识别到有效语音，请重试"

                # 4. 后处理文本
                text = result[0]['text']
                return self._post_process_text(text)

            finally:
                # 清理临时文件
                try:
                    logger.info(f"清理临时文件: {temp_path}")
                    Path(temp_path).unlink()
                except Exception as e:
                    logger.warning(f"清理临时文件失败: {str(e)}")

        except FFmpegError as e:
            logger.error(f"音频处理失败: {str(e)}")
            return f"音频处理失败: {str(e)}"
        except Exception as e:
            logger.error(f"语音识别失败: {str(e)}")
            return f"语音识别失败: {str(e)}"

    def _post_process_text(self, text: str) -> str:
        """文本后处理"""
        if not text:
            return ""

        # 1. 使用 FunASR 的后处理
        text = rich_transcription_postprocess(text)

        # 2. 清理非中英文字符
        # 只保留中文、英文、数字和基本标点符号
        cleaned_text = ""
        for char in text:
            # 检查是否是中文字符
            if '\u4e00' <= char <= '\u9fff':
                cleaned_text += char
            # 检查是否是英文字母
            elif char.isalpha():
                cleaned_text += char
            # 检查是否是数字
            elif char.isdigit():
                cleaned_text += char
            # 检查是否是基本标点符号
            elif char in "，。！？、：；""''（）,.!?:;\"\"''()":
                cleaned_text += char
            # 检查是否是空格
            elif char.isspace():
                cleaned_text += " "

        # 3. 标点符号规范化
        punctuation_map = {
            "，": ",", "。": ".", "！": "!", "？": "?",
            "、": ",", "：": ":", "；": ";", """: "\"",
            """: "\"", "'": "'", "'": "'", "（": "(",
            "）": ")"
        }

        for cn_punct, en_punct in punctuation_map.items():
            cleaned_text = cleaned_text.replace(cn_punct, en_punct)

        # 4. 去除多余空格
        cleaned_text = " ".join(cleaned_text.split())

        # 5. 如果清理后文本为空，返回提示信息
        if not cleaned_text.strip():
            return "未能识别到有效文本，请重试"

        return cleaned_text.strip()


if __name__ == "__main__":
    asr = ASRService()
    audio_file = "test/sample/sample-3s.wav"
    with open(audio_file, "rb") as f:
        audio_data = f.read()
    text = asr.transcribe(audio_data)

    import asyncio

    result = asyncio.run(text)
    print(result)
