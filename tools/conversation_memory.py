import hashlib
import json
from datetime import datetime
from typing import Any

from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from db.llama_store import search as _vector_search
from db.llama_store import upsert as _vector_upsert
from tools.brand_context import get_project_scope, get_runtime_config


MEMORY_DOMAIN = "conversation_memory"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _scope(runtime: ToolRuntime) -> dict[str, str | bool]:
    return get_project_scope(get_runtime_config(runtime))


def _project_namespace(scope: dict[str, str | bool]) -> tuple[str, str, str]:
    return (
        "project_memory",
        str(scope["user_id"]),
        str(scope["brand_id"]),
    )


def _thread_namespace(scope: dict[str, str | bool]) -> tuple[str, str, str, str]:
    return (
        "thread_summary",
        str(scope["user_id"]),
        str(scope["brand_id"]),
        str(scope["project_id"]),
    )


def _memory_metadata(scope: dict[str, str | bool], memory_type: str) -> dict[str, str]:
    return {
        "memory_domain": MEMORY_DOMAIN,
        "memory_type": memory_type,
        "user_id": str(scope["user_id"]),
        "brand_id": str(scope["brand_id"]),
        "project_id": str(scope["project_id"]),
    }


def _parse_decisions(decisions: str) -> list[str]:
    items = []
    for line in decisions.splitlines():
        clean = line.strip().strip("-•* ")
        if clean:
            items.append(clean)
    return items


def _format_project_memory(memory: dict[str, Any]) -> str:
    decisions = memory.get("decisions") or []
    decision_text = "\n".join(f"- {item}" for item in decisions) if decisions else "无"
    return (
        f"项目记忆更新时间：{memory.get('updated_at', '')}\n"
        f"当前文件：{memory.get('current_file', 'index.html')}\n"
        f"项目摘要：\n{memory.get('summary', '')}\n\n"
        f"关键决策：\n{decision_text}"
    )


def _stable_hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]


@tool
def get_project_memory(runtime: ToolRuntime) -> str:
    """读取当前 user/brand/project 的结构化项目记忆。生成或修改页面前使用。"""
    if runtime.store is None:
        return "项目记忆 store 不可用。"

    scope = _scope(runtime)
    item = runtime.store.get(_project_namespace(scope), str(scope["project_id"]))
    if not item:
        return (
            f"未找到当前项目记忆。scope: "
            f"user={scope['user_id']}, brand={scope['brand_id']}, project={scope['project_id']}"
        )
    return _format_project_memory(dict(item.value))


@tool
def update_project_memory(
    summary: str,
    runtime: ToolRuntime,
    decisions: str = "",
    current_file: str = "index.html",
) -> str:
    """更新当前项目的结构化记忆。页面保存和校验后必须使用。

    Args:
        summary: 当前项目/页面的稳定摘要，记录最终状态和用户已确认的要求。
        decisions: 逐行列出关键决策，例如品牌风格、CTA、禁用项、文件约束。
        current_file: 当前主页面文件，通常是 index.html。
    """
    scope = _scope(runtime)
    memory = {
        "user_id": scope["user_id"],
        "brand_id": scope["brand_id"],
        "project_id": scope["project_id"],
        "thread_id": scope["thread_id"],
        "summary": summary.strip(),
        "decisions": _parse_decisions(decisions),
        "current_file": (current_file or "index.html").strip(),
        "updated_at": _now(),
    }

    if runtime.store is not None:
        runtime.store.put(_project_namespace(scope), str(scope["project_id"]), memory)

    vector_id = (
        f"{MEMORY_DOMAIN}:project:"
        f"{scope['user_id']}:{scope['brand_id']}:{scope['project_id']}"
    )
    vector_text = (
        f"memory_domain: {MEMORY_DOMAIN}\n"
        f"memory_type: project_memory\n"
        f"user_id: {scope['user_id']}\n"
        f"brand_id: {scope['brand_id']}\n"
        f"project_id: {scope['project_id']}\n"
        f"thread_id: {scope['thread_id']}\n\n"
        f"{_format_project_memory(memory)}"
    )
    try:
        _vector_upsert(vector_id, vector_text, metadata=_memory_metadata(scope, "project_memory"))
    except Exception as e:
        return f"项目记忆已写入 store，但写入向量记忆失败：{e}"

    return "项目记忆已更新。"


@tool
def get_thread_summary(runtime: ToolRuntime) -> str:
    """读取当前 thread 的滚动摘要。长对话或继续修改页面前使用。"""
    if runtime.store is None:
        return "thread 摘要 store 不可用。"

    scope = _scope(runtime)
    item = runtime.store.get(_thread_namespace(scope), str(scope["thread_id"]))
    if not item:
        return "当前 thread 还没有滚动摘要。"
    return json.dumps(dict(item.value), ensure_ascii=False, indent=2)


@tool
def save_conversation_summary(summary: str, runtime: ToolRuntime, topic: str = "landing_page") -> str:
    """保存当前对话片段摘要到 thread store 和 pgvector。长对话阶段性完成后使用。

    Args:
        summary: 只保存稳定事实、用户确认过的要求、页面修改结果；不要保存模型失败幻觉。
        topic: 摘要主题，例如 landing_page、revision、brand_decision。
    """
    clean_summary = summary.strip()
    if not clean_summary:
        return "摘要不能为空，未保存。"

    scope = _scope(runtime)
    payload = {
        "user_id": scope["user_id"],
        "brand_id": scope["brand_id"],
        "project_id": scope["project_id"],
        "thread_id": scope["thread_id"],
        "topic": topic,
        "summary": clean_summary,
        "updated_at": _now(),
    }

    if runtime.store is not None:
        runtime.store.put(_thread_namespace(scope), str(scope["thread_id"]), payload)

    digest = _stable_hash(f"{scope['thread_id']}:{topic}:{clean_summary}")
    vector_id = (
        f"{MEMORY_DOMAIN}:summary:"
        f"{scope['user_id']}:{scope['brand_id']}:{scope['project_id']}:"
        f"{scope['thread_id']}:{digest}"
    )
    vector_text = (
        f"memory_domain: {MEMORY_DOMAIN}\n"
        f"memory_type: conversation_summary\n"
        f"user_id: {scope['user_id']}\n"
        f"brand_id: {scope['brand_id']}\n"
        f"project_id: {scope['project_id']}\n"
        f"thread_id: {scope['thread_id']}\n"
        f"topic: {topic}\n\n"
        f"{clean_summary}"
    )

    try:
        metadata = _memory_metadata(scope, "conversation_summary")
        metadata["thread_id"] = str(scope["thread_id"])
        metadata["topic"] = topic
        _vector_upsert(vector_id, vector_text, metadata=metadata)
    except Exception as e:
        return f"thread 摘要已写入 store，但写入向量记忆失败：{e}"

    return "对话摘要已保存。"


@tool
def search_conversation_memory(query: str, runtime: ToolRuntime, top_k: int = 5) -> str:
    """检索当前 user/brand/project 下的历史对话摘要。生成或修改页面前使用。"""
    scope = _scope(runtime)
    metadata = _memory_metadata(scope, "conversation_summary")
    search_query = (
        f"user_id: {scope['user_id']} brand_id: {scope['brand_id']} "
        f"project_id: {scope['project_id']} {query}"
    )

    try:
        results = _vector_search(search_query, top_k=top_k, metadata=metadata)
    except Exception as e:
        return f"检索对话记忆失败：{e}"

    if not results:
        return "没有找到当前项目相关的历史对话摘要。"

    return "\n---\n".join(
        f"[{item['metadata'].get('memory_type')}:{item['metadata'].get('topic', '')}] "
        f"score={item['score']:.3f}\n{item['text']}"
        for item in results
    )
