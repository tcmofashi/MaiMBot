from typing import Optional, Dict, List
from openai import OpenAI
from .message import Message
import jieba
from nonebot import get_driver
from .config import global_config
from ..models.utils_model import LLM_request

driver = get_driver()
config = driver.config  

class TopicIdentifier:
    def __init__(self):
        self.llm_topic_judge = LLM_request(model=global_config.llm_topic_judge)

    async def identify_topic_llm(self, text: str) -> Optional[List[str]]:
        """识别消息主题，返回主题列表"""

        prompt = f"""判断这条消息的主题，如果没有明显主题请回复"无主题"，要求：
1. 主题通常2-4个字，最好2个字，必须简短，要求精准概括，要求具体一点，例如是文本中的某个名词。
2. 建议给出多个主题，之间用英文逗号分割。只输出主题本身就好，不要有前后缀。

消息内容：{text}"""

        # 使用 LLM_request 类进行请求
        topic, _ = await self.llm_topic_judge.generate_response(prompt)
        
        if not topic:
            print(f"\033[1;31m[错误]\033[0m LLM API 返回为空")
            return None
            
        # 直接在这里处理主题解析
        if not topic or topic == "无主题":
            return None
            
        # 解析主题字符串为列表
        topic_list = [t.strip() for t in topic.split(",") if t.strip()]
        
        print(f"\033[1;32m[主题识别]\033[0m 主题: {topic_list}")
        return topic_list if topic_list else None

topic_identifier = TopicIdentifier()