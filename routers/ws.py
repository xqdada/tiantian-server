import asyncio
import json
import logging
from fastapi import WebSocket, APIRouter
from fastapi.websockets import WebSocketDisconnect
from services.asr import ASRService
from services.tts import TTSService
from services.llm import LLMService
from typing import Dict, List
import uuid
import time

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DialogueState:
    def __init__(self):
        self.messages: List[Dict[str, str]] = []
        self.is_speaking: bool = False
        self.last_interaction_time: float = time.time()
        self.context_window: int = 5  # 保留最近5轮对话
        self.audio_buffer: List[bytes] = []  # 用于存储音频数据
        self.processing: bool = False  # 标记是否正在处理

    def add_message(self, role: str, content: str):
        self.messages.append({"role": role, "content": content})
        self.last_interaction_time = time.time()
        # 保持上下文窗口大小
        if len(self.messages) > self.context_window * 2:
            self.messages = self.messages[-self.context_window * 2:]

    def get_context(self) -> List[Dict[str, str]]:
        return self.messages

    def add_audio_chunk(self, chunk: bytes):
        self.audio_buffer.append(chunk)
        self.last_interaction_time = time.time()

    def clear_audio_buffer(self):
        self.audio_buffer = []

    def get_audio_data(self) -> bytes:
        return b''.join(self.audio_buffer)


class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.dialogue_states: Dict[str, DialogueState] = {}
        self.asr = ASRService()
        self.tts = TTSService()
        self.llm = LLMService()
        self.task_queue = asyncio.Queue()
        self.current_task = None
        self.heartbeat_interval = 30  # 心跳间隔（秒）
        logger.info("ConnectionManager initialized")

    async def handle_websocket(self, websocket: WebSocket, client_id: str):
        try:
            logger.info(f"Accepting WebSocket connection for client: {client_id}")
            await websocket.accept()
            self.active_connections[client_id] = websocket
            self.dialogue_states[client_id] = DialogueState()
            
            # 启动心跳检测
            heartbeat_task = asyncio.create_task(self._heartbeat(websocket, client_id))
            
            logger.info(f"New connection established: {client_id}")

            while True:
                try:
                    # 等待接收消息
                    message = await websocket.receive()
                    
                    # 更新最后交互时间
                    self.dialogue_states[client_id].last_interaction_time = time.time()

                    # 根据消息类型处理
                    if "text" in message:
                        await self._handle_text_message(client_id, message["text"])
                    elif "bytes" in message:
                        await self._handle_binary_message(websocket, client_id, message["bytes"])
                    else:
                        logger.warning(f"Unknown message type received from {client_id}")

                except WebSocketDisconnect:
                    logger.info(f"WebSocket disconnected: {client_id}")
                    break
                except Exception as e:
                    logger.error(f"Error processing message from {client_id}: {str(e)}")
                    try:
                        await websocket.send_text(json.dumps({
                            "error": str(e),
                            "type": "error"
                        }))
                    except:
                        break

        except Exception as e:
            logger.error(f"WebSocket error for {client_id}: {str(e)}")
        finally:
            heartbeat_task.cancel()
            await self.cleanup_connection(client_id)

    async def _heartbeat(self, websocket: WebSocket, client_id: str):
        """心跳检测"""
        try:
            while True:
                await asyncio.sleep(self.heartbeat_interval)
                if client_id in self.active_connections:
                    try:
                        await websocket.send_text(json.dumps({"type": "ping"}))
                    except:
                        logger.warning(f"Heartbeat failed for client {client_id}")
                        await self.cleanup_connection(client_id)
                        break
        except asyncio.CancelledError:
            pass

    async def _handle_text_message(self, client_id: str, message: str):
        """处理文本消息"""
        try:
            logger.info(f"Received text message from {client_id}: {message[:100]}...")

            try:
                data = json.loads(message)
                logger.info(f"Parsed JSON data: {data}")

                # 处理心跳响应
                if data.get("type") == "pong":
                    return

                # 处理文本消息
                if data.get("type") == "text":
                    text = data.get("text", "")
                    if text:
                        logger.info(f"Processing text message: {text}")
                        await self.task_queue.put((text, client_id))
                        if not self.current_task:
                            self.current_task = asyncio.create_task(self.process_queue())
                    return

            except json.JSONDecodeError:
                # 如果不是JSON，作为普通文本处理
                if message.strip():
                    logger.info(f"Processing plain text message: {message}")
                    await self.task_queue.put((message, client_id))
                    if not self.current_task:
                        self.current_task = asyncio.create_task(self.process_queue())
                return

        except Exception as e:
            logger.error(f"Error handling text message: {str(e)}")
            raise

    async def _handle_binary_message(self, websocket: WebSocket, client_id: str, audio_data: bytes):
        """处理二进制音频数据"""
        try:
            logger.info(f"Received audio data from {client_id}: {len(audio_data)} bytes")
            
            # 将音频数据添加到缓冲区
            self.dialogue_states[client_id].add_audio_chunk(audio_data)
            
            # 如果正在处理，则跳过
            if self.dialogue_states[client_id].processing:
                return
                
            # 标记为正在处理
            self.dialogue_states[client_id].processing = True
            
            try:
                # 获取完整的音频数据
                complete_audio = self.dialogue_states[client_id].get_audio_data()
                
                # 语音识别
                text = await self.asr.transcribe(complete_audio)
                logger.info(f"Transcribed text from {client_id}: {text}")

                # 发送识别结果回前端
                await websocket.send_text(json.dumps({
                    "text": text,
                    "type": "transcription"
                }))

                # 提交处理任务
                if text and text.strip():
                    logger.info(f"Submitting transcribed text for processing: {text}")
                    await self.task_queue.put((text, client_id))
                    if not self.current_task:
                        self.current_task = asyncio.create_task(self.process_queue())
            finally:
                # 清除音频缓冲区
                self.dialogue_states[client_id].clear_audio_buffer()
                # 标记处理完成
                self.dialogue_states[client_id].processing = False

        except Exception as e:
            logger.error(f"Error handling binary message: {str(e)}")
            raise

    async def process_queue(self):
        """处理任务队列"""
        try:
            while not self.task_queue.empty():
                text, client_id = await self.task_queue.get()
                websocket = self.active_connections.get(client_id)
                if not websocket:
                    continue

                try:
                    # 检查文本是否为空
                    if not text or text.strip() == "":
                        logger.warning(f"Empty text received from {client_id}")
                        continue

                    # LLM 生成
                    logger.info(f"Generating response for text: {text}")
                    response = await self.llm.generate(text)
                    logger.info(f"LLM response for {client_id}: {response}")

                    # 发送文本响应回前端
                    await websocket.send_text(json.dumps({
                        "text": response,
                        "type": "response"
                    }))

                    # TTS 合成
                    audio = await self.tts.synthesize(response)

                    # 分块发送
                    chunk_size = 4096
                    for i in range(0, len(audio), chunk_size):
                        try:
                            await websocket.send_bytes(audio[i:i + chunk_size])
                        except WebSocketDisconnect:
                            return
                        except Exception as e:
                            logger.error(f"Error sending audio chunk to {client_id}: {str(e)}")
                            return

                except Exception as e:
                    logger.error(f"Error processing message for {client_id}: {str(e)}")
                    try:
                        await websocket.send_text(json.dumps({
                            "error": str(e),
                            "type": "error"
                        }))
                    except:
                        pass

        except Exception as e:
            logger.error(f"Error processing queue: {str(e)}")
        finally:
            self.current_task = None

    async def cleanup_connection(self, client_id: str):
        """清理连接相关的资源"""
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in self.dialogue_states:
            del self.dialogue_states[client_id]
        if self.current_task:
            self.current_task.cancel()
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
            except:
                pass
        logger.info(f"Cleaned up connection: {client_id}")


# 创建路由对象
router = APIRouter()

# 创建连接管理器实例
manager = ConnectionManager()


# 注册WebSocket路由
@router.websocket("/ws/chat")
async def websocket_endpoint(websocket: WebSocket):
    client_id = str(uuid.uuid4())
    await manager.handle_websocket(websocket, client_id)
