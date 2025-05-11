import os
import yaml
import logging
import time
from typing import Any, Dict
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv
import threading

logger = logging.getLogger(__name__)

class ConfigManager:
    _instance = None
    _config = {}
    _last_modified = 0
    _config_dir = Path("config")
    _env_config_file = None
    _observer = None
    _debounce_timer = None
    _debounce_delay = 1.0  # seconds

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigManager, cls).__new__(cls)
            cls._instance._initialize()
        return cls._instance

    def _initialize(self):
        """初始化配置管理器"""
        # 首先加载环境变量
        self._load_env()
        # 然后加载配置文件
        self._load_config()
        # 最后设置文件监视器
        self._setup_file_watcher()

    def _load_env(self):
        """加载环境变量"""
        # 尝试多个可能的.env文件位置
        env_paths = [
            Path('.env'),  # 当前目录
            self._config_dir.parent / '.env',  # 项目根目录
            Path.home() / '.env',  # 用户主目录
        ]
        
        env_loaded = False
        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path, override=True)  # 使用override=True确保环境变量被正确覆盖
                logger.info(f"已加载环境变量文件: {env_path.absolute()}")
                env_loaded = True
                break
        
        if not env_loaded:
            logger.warning("未找到.env文件，将使用系统环境变量")
            # 打印当前环境变量状态（不显示实际值）
            api_key = os.getenv("LLM_API_KEY")
            api_url = os.getenv("LLM_API_URL")
            logger.info("环境变量状态:")
            logger.info(f"LLM_API_KEY: {'已设置' if api_key else '未设置'}")
            logger.info(f"LLM_API_URL: {'已设置' if api_url else '未设置'}")
            if not api_key or api_key == "your_api_key_here":
                logger.warning("LLM_API_KEY 未正确设置！请在.env文件中设置正确的API密钥")

    def _get_config_file(self) -> Path:
        """获取配置文件路径"""
        config_file = self._config_dir / "config.yaml"
        if not config_file.exists():
            logger.warning(f"配置文件 {config_file} 不存在")
        logger.info(f"使用配置文件: {config_file}")
        return config_file

    def _load_config(self):
        """加载配置文件"""
        try:
            # 获取配置文件
            config_file = self._get_config_file()
            
            # 加载配置
            with open(config_file, 'r', encoding='utf-8') as f:
                self._config = yaml.safe_load(f)
            
            self._last_modified = config_file.stat().st_mtime
            
            # 从环境变量覆盖配置
            self._override_from_env()
            
            logger.info("配置加载成功")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
            raise

    def _deep_merge(self, base: Dict, override: Dict) -> Dict:
        """深度合并两个字典"""
        result = base.copy()
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def _setup_file_watcher(self):
        """设置文件监视器"""
        class ConfigFileHandler(FileSystemEventHandler):
            def __init__(self, config_manager):
                self.config_manager = config_manager

            def on_modified(self, event):
                if event.src_path == str(self.config_manager._get_config_file()):
                    current_mtime = self.config_manager._get_config_file().stat().st_mtime
                    if current_mtime > self.config_manager._last_modified:
                        logger.info("检测到配置文件变更，准备重新加载配置")
                        self.config_manager._debounced_reload()

        self._observer = Observer()
        self._observer.schedule(
            ConfigFileHandler(self),
            str(self._config_dir),
            recursive=False
        )
        self._observer.start()
        logger.info("配置文件监视器已启动")

    def _debounced_reload(self):
        """Debounced reload of configuration"""
        if self._debounce_timer:
            self._debounce_timer.cancel()
        self._debounce_timer = threading.Timer(self._debounce_delay, self._load_config)
        self._debounce_timer.start()

    def _override_from_env(self):
        """从环境变量覆盖配置（优先级：环境变量 > 环境配置文件 > 基础配置文件）"""
        # LLM配置
        if os.getenv('LLM_API_KEY'):
            self._config['llm']['api_key'] = os.getenv('LLM_API_KEY')
            logger.info("已从环境变量加载 LLM_API_KEY")
        if os.getenv('LLM_API_URL'):
            self._config['llm']['api_url'] = os.getenv('LLM_API_URL')
            logger.info("已从环境变量加载 LLM_API_URL")

        # 日志配置
        if os.getenv('LOG_LEVEL'):
            self._config['logging']['level'] = os.getenv('LOG_LEVEL')
            logger.info(f"已从环境变量加载 LOG_LEVEL: {os.getenv('LOG_LEVEL')}")

    def get_env(self, key: str, default: Any = None) -> Any:
        """从环境变量获取配置，如果不存在则返回默认值"""
        value = os.getenv(key, default)
        if value == "your_api_key_here" and key == "LLM_API_KEY":
            logger.warning("LLM_API_KEY 未正确设置！请在.env文件中设置正确的API密钥")
        return value

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置项"""
        keys = key.split('.')
        value = self._config
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default

    def get_all(self) -> Dict:
        """获取所有配置"""
        return self._config.copy()

    def reload(self):
        """重新加载配置"""
        self._load_config()

    def __del__(self):
        """清理资源"""
        if self._observer:
            self._observer.stop()
            self._observer.join() 