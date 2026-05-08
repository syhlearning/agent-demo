from langchain_core.tools import tool
from pydantic import BaseModel
import requests
import os
from tavily import TavilyClient


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


class WeatherQuery(BaseModel):
    city: str
@tool(
    args_schema=WeatherQuery,
)
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


tavily_client = None

class reference(BaseModel):
    url: str
@tool
def web_search(query: str) -> str:
    """使用 Tavily 搜索引擎搜索互联网上的信息。当用户询问你不确定的事实、最新新闻、实时信息时使用此工具。

    Args:
        query: 搜索查询关键词
    """
    try:
        global tavily_client
        if tavily_client is None:
            tavily_client = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
        result = tavily_client.search(query=query, max_results=3)
        output = []
        for item in result.get("results", []):
            output.append(f"标题: {item['title']}\n内容: {item['content']}\n链接: {item['url']}\n")
        return "\n---\n".join(output) if output else "未找到相关结果"
    except Exception as e:
        return f"搜索失败: {e}"
