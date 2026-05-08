from langchain_core.tools import tool
from pydantic import BaseModel
import requests


@tool
def output_formatter(answer: str, source: str = "", confidence: float = 1.0) -> dict:
    """将答案格式化为 JSON 格式输出。仅在用户明确要求结构化输出时使用。

    Args:
        answer: 回答用户问题的最终答案
        source: 答案的来源或依据（可选）
        confidence: 对答案的置信度，0-1之间（可选）
    """
    return {
        "answer": answer,
        "source": source,
        "confidence": confidence,
    }


@tool()
def get_weather(city: str) -> str:
    """查询指定城市的当前天气信息。当用户问天气相关问题时使用此工具。

    Args:
        city: 城市名称，如 "北京"、"上海"、"London"
    """
    try:
        # 使用 wttr.in 免费天气 API（无需 API key）
        url = f"https://wttr.in/{city}?format=%l:+%C+%t+%h+%w&lang=zh"
        resp = requests.get(url, timeout=10)
        # 如果响应状态码不是 200，就抛出异常，进入 except 块返回 "天气服务暂时不可用"
        resp.raise_for_status()
        return resp.text.strip()
    except requests.RequestException:
        return "天气服务暂时不可用"
