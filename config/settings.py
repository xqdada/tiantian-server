import os
from pathlib import Path
from .config_manager import ConfigManager

# 获取配置管理器实例
config_manager = ConfigManager()

class Settings:
    def __init__(self):
        config = config_manager.get_all()

        # TTS设置（包含Edge TTS设置）
        tts = config['tts']
        self.EDGE_DEFAULT_VOICE = tts['voices']['zh']  # 默认使用中文语音
        self.EDGE_DEFAULT_RATE = tts['rate']
        self.EDGE_DEFAULT_VOLUME = tts['volume']
        self.EDGE_DEFAULT_PITCH = tts['pitch']
        self.TTS_VOICES = tts['voices']
        self.TTS_CACHE_DIR = tts['temp_dir']
        self.TTS_CLEANUP_MAX_AGE = tts['cleanup']['max_age_hours']

        # ASR设置
        asr = config['asr']
        # 保存完整的ASR配置
        self.ASR = asr
        # 具体的ASR配置项
        self.ASR_MODEL = asr['model']
        self.ASR_MODEL_DIR = asr.get('model_dir', 'models/asr')
        self.ASR_DEVICE = os.getenv('ASR_DEVICE', asr['device'])
        self.ASR_SAMPLE_RATE = int(asr['audio']['target_sr'])
        self.ASR_CHUNK_SIZE = int(asr.get('chunk_size', 1024))
        self.ASR_CHUNK_STRIDE = int(asr.get('chunk_stride', 512))
        self.ASR_AUDIO = asr['audio']
        self.ASR_VAD_MODEL = asr['vad_model']
        self.ASR_VAD_PARAMS = asr['vad_params']

        # LLM设置
        llm = config['llm']
        # 保存完整的LLM配置
        self.LLM = llm
        # 具体的LLM配置项
        self.LLM_MODEL = llm['model']
        self.LLM_MODEL_DIR = llm.get('model_dir', 'models/llm')
        self.LLM_DEVICE = os.getenv('LLM_DEVICE', llm.get('device', 'cpu'))
        self.LLM_MAX_LENGTH = int(llm.get('max_length', 2048))
        self.LLM_TEMPERATURE = float(llm['temperature'])
        self.LLM_TOP_P = float(llm.get('top_p', 0.7))
        self.LLM_API_BASE = os.getenv('LLM_API_URL', llm['api_url'])
        self.LLM_API_KEY = os.getenv('LLM_API_KEY', llm.get('api_key', ''))
        self.LLM_MAX_CONTEXT_LENGTH = int(llm['max_context_length'])

        # TTS设置
        self.TTS = tts  # 保存完整的TTS配置

        # 服务器设置
        server = config.get('server', {})
        self.SERVER = server  # 保存完整的服务器配置
        self.HOST = os.getenv('HOST', server.get('host', '0.0.0.0'))
        self.PORT = int(os.getenv('PORT', server.get('port', 8000)))
        self.DEBUG = os.getenv('DEBUG', str(server.get('debug', False))).lower() == 'true'

        # WebSocket设置
        websocket = config.get('websocket', {})  # 添加默认值
        self.WEBSOCKET = websocket  # 保存完整的WebSocket配置
        self.WS_PING_INTERVAL = int(os.getenv('WS_PING_INTERVAL', websocket.get('ping_interval', 20)))
        self.WS_PING_TIMEOUT = int(os.getenv('WS_PING_TIMEOUT', websocket.get('ping_timeout', 20)))
        self.WS_CLOSE_TIMEOUT = int(os.getenv('WS_CLOSE_TIMEOUT', websocket.get('close_timeout', 20)))

        # 日志设置
        logging_config = config['logging']
        self.LOGGING = logging_config  # 保存完整的日志配置
        self.LOG_LEVEL = os.getenv('LOG_LEVEL', logging_config['level'])
        self.LOG_FORMAT = logging_config['format']


settings = Settings()
