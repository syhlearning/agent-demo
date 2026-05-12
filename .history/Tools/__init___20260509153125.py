from langchain_core.tools import tool
from langchain.tools import ToolRuntime
from pydantic import BaseModel
import requests
import os
import json
from tavily import TavilyClient
from datetime import datetime


def _get_user_id(runtime: ToolRuntime) -> str:
    configurable = (runtime.config or {}).get("configurable", {})
    return str(configurable.get("user_id") or configurable.get("thread_id") or "default-user")


def _get_user_profile(runtime: ToolRuntime) -> dict:
    if runtime.store is None:
        return {}

    item = runtime.store.get(("users", _get_user_id(runtime)), "profile")
    return dict(item.value) if item else {}


def _visible_user_profile(profile: dict) -> dict:
    return {key: value for key, value in profile.items() if key != "updated_at"}


@tool
def save_user_info(key: str, value: str, runtime: ToolRuntime) -> str:
    """长期保存或更新用户信息。当用户告诉你姓名、城市、偏好、职业、常用需求等稳定信息时使用。

    Args:
        key: 信息字段名，例如 name、city、job、food_preference、communication_style等等
        value: 要保存的字段值
    """
    if runtime.store is None:
        return "长期记忆数据库不可用，未保存用户信息。"

    normalized_key = key.strip().lower().replace(" ", "_")
    normalized_value = value.strip()
    if not normalized_key or not normalized_value:
        return "字段名和值不能为空，未保存用户信息。"

    profile = _get_user_profile(runtime)
    profile[normalized_key] = normalized_value
    profile["updated_at"] = datetime.now().isoformat(timespec="seconds")

    runtime.store.put(("users", _get_user_id(runtime)), "profile", profile)
    return f"已长期保存用户信息：{normalized_key} = {normalized_value}"


@tool
def get_user_info(runtime: ToolRuntime, key: str = "") -> str:
    """读取长期保存的用户信息。当需要个性化回答，或用户问你是否记得某个信息时使用。

    Args:
        key: 可选字段名。为空时返回全部已保存用户信息。
    """
    if runtime.store is None:
        return "长期记忆数据库不可用。"

    profile = _get_user_profile(runtime)
    visible_profile = _visible_user_profile(profile)
    if not visible_profile:
        return "还没有长期保存的用户信息。"

    normalized_key = key.strip().lower().replace(" ", "_")
    if normalized_key:
        value = profile.get(normalized_key)
        return str(value) if value is not None else f"没有找到字段：{normalized_key}"

    return json.dumps(visible_profile, ensure_ascii=False)


@tool
def delete_user_info(key: str, runtime: ToolRuntime) -> str:
    """删除长期保存的某个用户信息字段。当用户要求忘记或删除某项个人信息时使用。

    Args:
        key: 要删除的信息字段名
    """
    if runtime.store is None:
        return "长期记忆数据库不可用，未删除用户信息。"

    normalized_key = key.strip().lower().replace(" ", "_")
    if not normalized_key:
        return "字段名不能为空，未删除用户信息。"

    profile = _get_user_profile(runtime)
    if normalized_key not in _visible_user_profile(profile):
        return f"没有找到字段：{normalized_key}"

    profile.pop(normalized_key)
    if _visible_user_profile(profile):
        profile["updated_at"] = datetime.now().isoformat(timespec="seconds")
        runtime.store.put(("users", _get_user_id(runtime)), "profile", profile)
    else:
        runtime.store.delete(("users", _get_user_id(runtime)), "profile")
    return f"已删除用户信息字段：{normalized_key}"


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
