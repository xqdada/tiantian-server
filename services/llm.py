import json
import logging
import aiohttp
from typing import List, Dict
from config.settings import settings


# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class LLMService:
    def __init__(self):
        # 从配置管理器获取配置
        self.api_url = settings.LLM_API_BASE
        self.api_key = settings.LLM_API_KEY
        self.max_context_length = settings.LLM_MAX_CONTEXT_LENGTH
        self.temperature = settings.LLM_TEMPERATURE
        self.model = settings.LLM_MODEL
        self.conversation_history: List[Dict[str, str]] = []
        logger.info("LLM service initialized with configuration:")
        logger.info(f"API URL: {self.api_url}")
        logger.info(f"Model: {self.model}")
        logger.info(f"Max context length: {self.max_context_length}")
        logger.info(f"Temperature: {self.temperature}")

    async def get_response(self, user_input: str) -> str:
        """ 获取LLM的响应"""
        if not user_input or not user_input.strip():
            logger.warning("Empty user input received")
            return "抱歉，我没有听清楚，请重试。"

        try:
            logger.info(f"Processing user input: {user_input[:100]}...")  # 只记录前100个字符

            # 更新对话历史
            self.conversation_history.append({"role": "user", "content": user_input})
            if len(self.conversation_history) > self.max_context_length:
                self.conversation_history = self.conversation_history[-self.max_context_length:]
                logger.info(f"Conversation history trimmed to {self.max_context_length} messages")

            # 准备请求数据
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}"
            }

            data = {
                "model": self.model,
                "messages": self.conversation_history,
                "temperature": self.temperature,
            }

            logger.info("Sending request to LLM API")
            # 发送请求
            async with aiohttp.ClientSession() as session:
                async with session.post(self.api_url, headers=headers, json=data) as response:
                    if response.status == 200:
                        result = await response.json()
                        if "choices" not in result or not result["choices"]:
                            logger.error(f"Invalid response format: {result}")
                            return "抱歉，我遇到了一些问题，请重试。"
                            
                        assistant_response = result["choices"][0]["message"]["content"]
                        logger.info(f"Received response: {assistant_response[:100]}...")  # 只记录前100个字符
                        
                        # 更新对话历史
                        self.conversation_history.append({"role": "assistant", "content": assistant_response})
                        
                        return assistant_response
                    else:
                        error_text = await response.text()
                        logger.error(f"LLM API error: Status {response.status}, Response: {error_text}")
                        if response.status == 401:
                            return "抱歉，API认证失败，请检查配置。"
                        elif response.status == 429:
                            return "抱歉，请求过于频繁，请稍后再试。"
                        else:
                            return f"抱歉，我遇到了一些问题（错误码：{response.status}），请重试。"

        except aiohttp.ClientError as e:
            logger.error(f"Network error while calling LLM API: {str(e)}")
            return "抱歉，网络连接出现问题，请检查网络后重试。"
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM API response: {str(e)}")
            return "抱歉，服务器响应格式错误，请重试。"
        except Exception as e:
            logger.error(f"Unexpected error while getting LLM response: {str(e)}")
            return "抱歉，我遇到了一些意外的问题，请重试。"

    async def generate(self, text: str) -> str:
        """生成文本响应的别名方法"""
        return await self.get_response(text)

    def clear_history(self):
        """清除对话历史"""
        self.conversation_history = []
        logger.info("Conversation history cleared")