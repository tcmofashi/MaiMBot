
import json
import uuid
import asyncio
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.common.logger import get_logger
from .payload_content.message import Message, RoleType

logger = get_logger("dataset_recorder")


class DatasetRecorder:
    """
    记录 LLM 调用的输入输出，用于构建数据集。
    """

    def __init__(self, record_dir: str = "data/record"):
        self.record_dir = Path(record_dir)
        self._ensure_dir()
        
    def _ensure_dir(self):
        """确保记录目录存在"""
        if not self.record_dir.exists():
            try:
                self.record_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"创建数据集记录目录失败: {e}")

    def _convert_message_to_dict(self, message: Message) -> Dict[str, Any]:
        """将 Message 对象转换为字典格式"""
        role_map = {
            RoleType.System: "system",
            RoleType.User: "user",
            RoleType.Assistant: "assistant",
            RoleType.Tool: "tool",
        }
        
        content = message.content
        # 如果content是列表（包含图片等），尝试转为可序列化的格式
        # 这里为了数据集简洁，我们可能需要处理一下图片，或者直接存原始结构
        # ShareGPT 格式通常处理纯文本，如果要支持多模态需要特定格式
        # 暂时保持原始结构，但在json dump时会自动处理基本类型
        
        # 处理 content 中的 bytes (图片)，转为 base64 字符串的占位符或者忽略，避免日志过大
        # 数据集通常需要图片路径或者 url，这里如果是 base64，直接存可能会导致文件极大
        # 但用户要求“完整记录”，所以我们先保留。
        # 如果是 list，遍历处理
        if isinstance(content, list):
            serializable_content = []
            for item in content:
                if isinstance(item, tuple): # (format, base64_str)
                    # 记录为特殊格式，标识这是图片
                    serializable_content.append({
                        "type": "image",
                        "format": item[0],
                        "data": item[1] # 完整记录 base64
                    })
                else:
                    serializable_content.append({"type": "text", "text": item})
            content = serializable_content

        return {
            "role": role_map.get(message.role, "unknown"),
            "content": content,
            "tool_calls": [
                {
                    "id": tc.call_id,
                    "type": "function",
                    "function": {"name": tc.func_name, "arguments": tc.args}
                }
                for tc in (message.tool_calls or [])
            ] if message.tool_calls else None,
            "tool_call_id": message.tool_call_id
        }

    def record_transaction(
        self,
        task_name: str,
        messages: List[Message],
        response_content: str,
        model_name: str,
        reasoning_content: Optional[str] = None,
        tool_calls: Optional[List[Any]] = None
    ):
        """
        记录一次 LLM 交互事务
        :param task_name: 任务类型/名称 (将用作文件名的一部分)
        :param messages: 输入的消息列表
        :param response_content: 模型生成的回复内容
        :param model_name: 模型名称
        :param reasoning_content: (可选) 推理内容
        :param tool_calls: (可选) 工具调用列表
        """
        try:
            timestamp = datetime.now().isoformat()
            
            # 构建标准化的 Conversation 格式
            # 这里参考 ShareGPT / LLaMA-Factory 的格式，但为了最大化保留信息，我们使用自定义的完整结构
            # 并确保包含 sharegpt 风格的 conversations 字段，方便转换
            
            # 转换 system prompt
            system_prompt = None
            conversation_turns = []
            
            for msg in messages:
                if msg.role == RoleType.System:
                    # 如果有多个 system，追加或者覆盖，通常只有一个
                    content_str = msg.content if isinstance(msg.content, str) else str(msg.content)
                    system_prompt = (system_prompt + "\n" + content_str) if system_prompt else content_str
                else:
                    conversation_turns.append(self._convert_message_to_dict(msg))
            
            # 添加 Assistant 的回复
            assistant_msg = {
                "role": "assistant",
                "content": response_content,
                "reasoning_content": reasoning_content,
                "tool_calls": [
                    {
                        "id": tc.call_id,
                        "type": "function",
                        "function": {"name": tc.func_name, "arguments": tc.args}
                    }
                    for tc in (tool_calls or [])
                ] if tool_calls else None
            }
            conversation_turns.append(assistant_msg)

            record_data = {
                "id": str(uuid.uuid4()),
                "timestamp": timestamp,
                "task_type": task_name,
                "model": model_name,
                "system": system_prompt,
                "messages": conversation_turns, # 完整保留原始结构
            }

            # 决定文件名： data/record/{task_name}.jsonl
            # 可以在这里加上日期后缀，防止单个文件过大: {task_name}_{date}.jsonl
            # 用户需求: "存储在data/record/下的不同的json文件中...以便后续分类取用" -> task_name 区分即可
            # 既然要求“文件”，且数据量可能大，jsonl 是最佳选择。
            
            safe_task_name = task_name.replace("/", "_").replace("\\", "_") if task_name else "default"
            file_path = self.record_dir / f"{safe_task_name}.jsonl"
            
            # 异步写入避免阻塞 (简单起见这里用同步追加，因为是在 LLM 返回后执行，影响不大)
            # 如果并发很高可以考虑放到后台队列但这里保持简单有效
            with open(file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record_data, ensure_ascii=False) + "\n")
                
        except Exception as e:
            logger.error(f"记录数据集失败: {e}")
            # 不抛出异常，以免影响主流程


# 全局单例
dataset_recorder = DatasetRecorder()
