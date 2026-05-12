from langchain_core.tools import tool
from langchain.tools import ToolRuntime
from pydantic import BaseModel, Field
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


class WanImageQuery(BaseModel):
    prompt: str = Field(..., description="图片生成或编辑提示词")
    image_urls: list[str] = Field(
        default_factory=list,
        description="可选的参考图 URL 列表；用于图像编辑、多图参考生成等场景",
    )
    size: str = Field(
        default="2K",
        description='输出尺寸。常用值："1K"、"2K"、"4K"；图像编辑和组图生成最高通常为 "2K"',
    )
    n: int = Field(default=1, ge=1, le=4, description="生成图片数量，通常 1 到 4 张")
    watermark: bool = Field(default=False, description="是否添加水印")


def _dashscope_image_endpoint() -> str:
    # 如果显式配置了图片接口完整地址，就优先使用它，方便临时切换或调试。
    endpoint = os.getenv("DASHSCOPE_IMAGE_ENDPOINT")
    if endpoint:
        return endpoint.rstrip("/")

    # DASHSCOPE_BASE_URL 可能配置成原生 DashScope 前缀：
    # https://dashscope.aliyuncs.com/api/v1
    # 也可能配置成 OpenAI 兼容模式前缀：
    # https://dashscope.aliyuncs.com/compatible-mode/v1
    base_url = os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/api/v1").rstrip("/")
    if "/services/aigc/" in base_url:
        return base_url

    # wan2.7-image-pro 是图片模型，不能走 compatible-mode/v1/chat/completions。
    # 如果传入的是 OpenAI 兼容模式地址，这里转换回 DashScope 原生 API 前缀。
    if base_url.endswith("/compatible-mode/v1"):
        base_url = base_url[: -len("/compatible-mode/v1")] + "/api/v1"
    elif not base_url.endswith("/api/v1"):
        base_url = f"{base_url}/api/v1"

    # 万相图片生成/编辑的实际调用地址。
    # https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation这个才是真正的调用地址，前面只是兼容不同用户可能配置的地址格式。
    return f"{base_url}/services/aigc/multimodal-generation/generation"


@tool(args_schema=WanImageQuery)
def generate_wan_image(
    prompt: str,
    image_urls: list[str] | None = None,
    size: str = "2K",
    n: int = 1,
    watermark: bool = False,
) -> str:
    """调用阿里云 DashScope 万相 wan2.7-image-pro 生成或编辑图片。

    Args:
        prompt: 图片生成或编辑提示词
        image_urls: 可选参考图 URL 列表；传入图片时用于图像编辑或参考生成
        size: 输出尺寸，例如 "1K"、"2K"、"4K"
        n: 生成图片数量
        watermark: 是否添加水印
    """
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        return "调用失败：缺少 DASHSCOPE_API_KEY 环境变量。"

    content = [{"image": url} for url in image_urls or [] if url]
    content.append({"text": prompt})
    payload = {
        "model": os.getenv("DASHSCOPE_IMAGE_MODEL", "wan2.7-image-pro"),
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": {
            "size": size,
            "n": n,
            "watermark": watermark,
        },
    }

    try:
        resp = requests.post(
            _dashscope_image_endpoint(),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=180,
        )
        data = resp.json()
    except requests.Timeout:
        return "调用失败：DashScope 图片生成请求超时。"
    except requests.RequestException as e:
        return f"调用失败：DashScope 图片生成请求异常：{e}"
    except ValueError:
        return f"调用失败：DashScope 返回了非 JSON 响应，HTTP {resp.status_code}：{resp.text[:500]}"

    dashscope_status = data.get("status_code")
    dashscope_code = data.get("code")
    if (
        resp.status_code != 200
        or (dashscope_status is not None and dashscope_status != 200)
        or bool(dashscope_code)
    ):
        message = data.get("message") or data.get("code") or resp.text[:500]
        return f"调用失败：HTTP {resp.status_code}，DashScope 返回：{message}"

    image_results = []
    for choice in data.get("output", {}).get("choices", []):
        for item in choice.get("message", {}).get("content", []):
            image_url = item.get("image")
            if image_url:
                image_results.append(image_url)

    if not image_results:
        return "调用成功，但响应里没有找到图片 URL：" + json.dumps(data, ensure_ascii=False)

    return json.dumps(
        {
            "model": payload["model"],
            "images": image_results,
            "request_id": data.get("request_id"),
            "note": "图片 URL 通常有有效期，请及时保存。",
        },
        ensure_ascii=False,
    )


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
