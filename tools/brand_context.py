import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from langchain.tools import ToolRuntime
from langchain_core.tools import tool


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = BASE_DIR / "projects"
BRAND_DATA_ROOT = BASE_DIR / "brand_data"
DEFAULT_ORG_ID = "starlinke"

BRAND_DOC_TYPES = {
    "brand_skill",
    "landing_page_rule",
    "product_doc",
    "reference",
    "knowledge",
}


SAFE_SEGMENT_RE = re.compile(r"^[0-9A-Za-z._-]+$")
FNV_OFFSET_BASIS = 2166136261
FNV_PRIME = 16777619


def _stable_hash(text: str) -> str:
    value = FNV_OFFSET_BASIS
    for byte in text.encode("utf-8"):
        value ^= byte
        value = (value * FNV_PRIME) & 0xFFFFFFFF
    return f"{value:08x}"


def _segment_prefix(default: str) -> str:
    clean = re.sub(r"[^0-9A-Za-z]+", "-", default or "item").strip("-").lower()
    if clean.startswith("default-"):
        clean = clean.removeprefix("default-")
    return clean or "item"


def _safe_segment(value: str | None, default: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return default

    text = raw.strip(".-")
    if text and SAFE_SEGMENT_RE.fullmatch(text):
        return text

    return f"{_segment_prefix(default)}-{_stable_hash(raw)}"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def get_runtime_config(runtime: ToolRuntime) -> dict[str, Any]:
    return (runtime.config or {}).get("configurable", {})


def get_project_scope(configurable: dict[str, Any]) -> dict[str, str | bool]:
    org_id = _safe_segment(str(configurable.get("org_id") or DEFAULT_ORG_ID), DEFAULT_ORG_ID)
    user_id = _safe_segment(
        str(configurable.get("user_id") or configurable.get("thread_id") or "default-user"),
        "default-user",
    )
    thread_id = _safe_segment(str(configurable.get("thread_id") or "default-thread"), "default-thread")
    has_project_scope = bool(configurable.get("brand_id") or configurable.get("project_id"))
    brand_id = _safe_segment(str(configurable.get("brand_id") or "default-brand"), "default-brand")
    project_id = _safe_segment(str(configurable.get("project_id") or thread_id), "default-project")
    return {
        "org_id": org_id,
        "user_id": user_id,
        "thread_id": thread_id,
        "brand_id": brand_id,
        "project_id": project_id,
        "has_project_scope": has_project_scope,
    }


def project_base_dir_from_config(configurable: dict[str, Any]) -> Path:
    scope = get_project_scope(configurable)
    if scope["has_project_scope"]:
        return PROJECTS_ROOT / str(scope["user_id"]) / str(scope["brand_id"]) / str(scope["project_id"])
    return PROJECTS_ROOT / str(scope["user_id"]) / str(scope["thread_id"])


def project_url_from_config(configurable: dict[str, Any], file_path: str) -> str:
    scope = get_project_scope(configurable)
    clean_file_path = file_path.strip().lstrip("/")
    if scope["has_project_scope"]:
        return (
            f"/projects/{scope['user_id']}/{scope['brand_id']}/"
            f"{scope['project_id']}/{clean_file_path}"
        )
    return f"/projects/{scope['user_id']}/{scope['thread_id']}/{clean_file_path}"


def safe_project_path(configurable: dict[str, Any], file_path: str) -> Path:
    base = project_base_dir_from_config(configurable).resolve()
    normalized = _normalize_project_file_path(base, file_path)
    target = (base / normalized).resolve()
    target.relative_to(base)
    return target


def _normalize_project_file_path(base: Path, file_path: str) -> str:
    raw = (file_path or "").strip()
    if not raw:
        raise ValueError("文件路径不能为空")

    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        raw = parsed.path
    raw = unquote(raw.split("#", 1)[0].split("?", 1)[0]).strip()

    projects_root = PROJECTS_ROOT.resolve()
    if raw.startswith("/projects/"):
        return str((projects_root / raw.removeprefix("/projects/")).resolve().relative_to(base))
    if raw.startswith("projects/"):
        return str((projects_root / raw.removeprefix("projects/")).resolve().relative_to(base))

    path = Path(raw)
    if path.is_absolute():
        return str(path.resolve().relative_to(base))
    return raw


def brand_dir(org_id: str, brand_id: str) -> Path:
    return BRAND_DATA_ROOT / _safe_segment(str(org_id), DEFAULT_ORG_ID) / _safe_segment(brand_id, "default-brand")


def _doc_path(org_id: str, brand_id: str, doc_type: str, doc_id: str) -> Path:
    clean_type = doc_type if doc_type in BRAND_DOC_TYPES else "knowledge"
    clean_id = _safe_segment(doc_id, "document")
    return brand_dir(org_id, brand_id) / "documents" / clean_type / f"{clean_id}.json"


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def _profile_path(org_id: str, brand_id: str) -> Path:
    return brand_dir(org_id, brand_id) / "profile.json"


def _iter_brand_docs(org_id: str, brand_id: str, doc_types: set[str] | None = None) -> list[dict[str, Any]]:
    root = brand_dir(org_id, brand_id) / "documents"
    if not root.exists():
        return []

    docs: list[dict[str, Any]] = []
    for path in sorted(root.glob("*/*.json")):
        data = _read_json(path, None)
        if not isinstance(data, dict):
            continue
        if doc_types and data.get("doc_type") not in doc_types:
            continue
        docs.append(data)
    return docs


def _extract_profile_fields(docs: list[dict[str, Any]]) -> dict[str, Any]:
    text = "\n".join(str(doc.get("text", "")) for doc in docs)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    colors = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b", text)))
    required = [
        line for line in lines
        if any(word in line for word in ("必须", "需要", "包含", "required", "must"))
    ][:30]
    forbidden = [
        line for line in lines
        if any(word in line for word in ("禁止", "不要", "不能", "避免", "forbidden", "avoid"))
    ][:30]
    tone = [
        line for line in lines
        if any(word in line for word in ("语气", "调性", "风格", "tone", "voice"))
    ][:20]
    return {
        "colors": colors,
        "required_rules": required,
        "forbidden_rules": forbidden,
        "tone_rules": tone,
    }


def rebuild_brand_profile(org_id: str, brand_id: str) -> dict[str, Any]:
    docs = _iter_brand_docs(org_id, brand_id)
    hard_docs = [
        doc for doc in docs
        if doc.get("doc_type") in {"brand_skill", "landing_page_rule"}
    ]
    profile = {
        "org_id": _safe_segment(str(org_id), DEFAULT_ORG_ID),
        "brand_id": _safe_segment(brand_id, "default-brand"),
        "updated_at": _now(),
        "documents": [
            {
                "doc_id": doc.get("doc_id"),
                "doc_type": doc.get("doc_type"),
                "source_filename": doc.get("source_filename"),
                "updated_at": doc.get("updated_at"),
            }
            for doc in docs
        ],
        "fields": _extract_profile_fields(hard_docs or docs),
    }
    path = _profile_path(org_id, brand_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def save_brand_document_text(
    org_id: str,
    brand_id: str,
    doc_id: str,
    doc_type: str,
    text: str,
    source_filename: str = "",
) -> dict[str, Any]:
    clean_type = doc_type if doc_type in BRAND_DOC_TYPES else "knowledge"
    path = _doc_path(org_id, brand_id, clean_type, doc_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "org_id": _safe_segment(str(org_id), DEFAULT_ORG_ID),
        "brand_id": _safe_segment(brand_id, "default-brand"),
        "doc_id": _safe_segment(doc_id, "document"),
        "doc_type": clean_type,
        "source_filename": source_filename,
        "updated_at": _now(),
        "text": text,
    }
    path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    profile = rebuild_brand_profile(org_id, brand_id)
    return {"document": document, "profile": profile}


def get_brand_profile_text(org_id: str, brand_id: str, max_chars: int = 12000) -> str:
    profile = _read_json(_profile_path(org_id, brand_id), {})
    docs = _iter_brand_docs(org_id, brand_id, {"brand_skill", "landing_page_rule", "product_doc"})
    if not docs:
        return f"未找到公司 {org_id} 下品牌 {brand_id} 的 skill 或资料。"

    parts = [
        f"公司 ID：{_safe_segment(org_id, DEFAULT_ORG_ID)}",
        f"品牌 ID：{_safe_segment(brand_id, 'default-brand')}",
        "结构化规则：",
        json.dumps(profile.get("fields", {}), ensure_ascii=False, indent=2),
        "原始 skill / 资料摘录：",
    ]
    remaining = max_chars - sum(len(part) for part in parts)
    for doc in docs:
        if remaining <= 0:
            break
        header = f"\n\n[{doc.get('doc_type')}] {doc.get('doc_id')}\n"
        text = str(doc.get("text", ""))
        excerpt = text[: max(0, min(len(text), remaining - len(header)))]
        parts.append(header + excerpt)
        remaining -= len(header) + len(excerpt)
    return "\n".join(parts)


def search_brand_documents(org_id: str, brand_id: str, query: str, top_k: int = 5) -> list[dict[str, Any]]:
    docs = _iter_brand_docs(org_id, brand_id)
    if not docs:
        return []

    terms = [term.lower() for term in re.findall(r"[0-9A-Za-z_\-#]+|[\u4e00-\u9fff]{2,}", query)]
    candidates: list[dict[str, Any]] = []
    for doc in docs:
        text = str(doc.get("text", ""))
        chunks = _chunk_text(text)
        for index, chunk in enumerate(chunks):
            lower = chunk.lower()
            score = 0
            for term in terms:
                if term and term in lower:
                    score += 2
            if query and query in chunk:
                score += 5
            if score == 0 and doc.get("doc_type") in {"brand_skill", "landing_page_rule"}:
                score = 1
            if score:
                candidates.append({
                    "doc_id": doc.get("doc_id"),
                    "doc_type": doc.get("doc_type"),
                    "chunk_index": index,
                    "score": score,
                    "text": chunk,
                })
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:top_k]


def _chunk_text(text: str, chunk_size: int = 1400, overlap: int = 160) -> list[str]:
    clean = text.strip()
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end])
        if end == len(clean):
            break
        start = max(0, end - overlap)
    return chunks


def validate_landing_page_file(configurable: dict[str, Any], file_path: str = "index.html") -> dict[str, Any]:
    scope = get_project_scope(configurable)
    try:
        path = safe_project_path(configurable, file_path)
    except ValueError as exc:
        return {
            "ok": False,
            "issues": [f"文件路径非法：{exc}。请使用当前项目内的相对路径，例如 index.html。"],
            "warnings": [],
            "preview_url": "",
        }
    issues: list[str] = []
    warnings: list[str] = []
    if not path.exists():
        return {"ok": False, "issues": [f"文件不存在：{file_path}"], "warnings": [], "preview_url": ""}

    html = path.read_text(encoding="utf-8")
    if len(html.strip()) < 500:
        issues.append("页面内容过短，可能不是完整落地页。")
    if "<!doctype html" not in html.lower():
        issues.append("缺少 <!DOCTYPE html>。")
    if "<style" not in html.lower():
        issues.append("缺少内联 <style>，不符合 Shadow DOM 兼容要求。")
    if "root-container" not in html:
        warnings.append("没有发现 root-container 根容器，嵌入主站时可能不够稳定。")
    if any(name in file_path for name in ("patch", "tail")):
        issues.append("当前文件像补丁文件；落地页最终结果必须写回 index.html。")

    profile = _read_json(_profile_path(str(scope["org_id"]), str(scope["brand_id"])), {})
    colors = profile.get("fields", {}).get("colors", [])
    if colors and not any(color.lower() in html.lower() for color in colors):
        warnings.append("品牌 skill 中出现了品牌色，但页面 HTML 中未检测到这些色值。")

    forbidden_rules = profile.get("fields", {}).get("forbidden_rules", [])
    for rule in forbidden_rules[:8]:
        if _rule_literal_hit(str(rule), html):
            warnings.append(f"可能违反禁止项：{rule}")

    return {
        "ok": not issues,
        "issues": issues,
        "warnings": warnings,
        "preview_url": project_url_from_config(configurable, file_path),
    }


def _rule_literal_hit(rule: str, html: str) -> bool:
    quoted = re.findall(r"[“\"']([^“\"']{2,40})[”\"']", rule)
    haystack = html.lower()
    return any(item.lower() in haystack for item in quoted)


@tool
def get_brand_profile(runtime: ToolRuntime) -> str:
    """读取当前品牌的结构化规范和 skill 摘录。生成或修改落地页前必须先使用。"""
    config = get_runtime_config(runtime)
    scope = get_project_scope(config)
    return get_brand_profile_text(str(scope["org_id"]), str(scope["brand_id"]))


@tool
def search_brand_skills(query: str, runtime: ToolRuntime, top_k: int = 5) -> str:
    """在当前品牌上传的 skill、落地页规则、产品资料中检索相关片段。"""
    config = get_runtime_config(runtime)
    scope = get_project_scope(config)
    results = search_brand_documents(str(scope["org_id"]), str(scope["brand_id"]), query, top_k=top_k)
    if not results:
        return "没有找到当前品牌的相关 skill 或资料。"
    return "\n---\n".join(
        f"[{item['doc_type']}:{item['doc_id']}#{item['chunk_index']}] score={item['score']}\n{item['text']}"
        for item in results
    )


@tool
def validate_landing_page(file_path: str, runtime: ToolRuntime) -> str:
    """校验当前项目中的落地页文件是否满足基础结构和品牌规范。保存 index.html 后必须使用。"""
    config = get_runtime_config(runtime)
    result = validate_landing_page_file(config, file_path or "index.html")
    return json.dumps(result, ensure_ascii=False, indent=2)
