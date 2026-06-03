# ── 项目文件管理工具 ──────────────────────────────────────────────────────────
# 当前实现：本地文件系统。
# 新版优先使用 projects/{user_id}/{brand_id}/{project_id}/；
# 如果请求里没有 brand_id/project_id，则兼容旧目录 projects/{user_id}/{thread_id}/。
#
# 切换阿里云 OSS：
#   import oss2
#   bucket = oss2.Bucket(oss2.Auth(ak, sk), endpoint, bucket_name)
#   把 open(path, "w").write(content) 换成 bucket.put_object(key, content)
#   把 open(path).read()             换成 bucket.get_object(key).read()
#   把 os.listdir()                  换成 oss2.ObjectIterator(bucket, prefix=...)
# ─────────────────────────────────────────────────────────────────────────────

import os
from pathlib import Path
from urllib.parse import unquote, urlparse
from langchain_core.tools import tool
from langchain.tools import ToolRuntime
from tools.brand_context import (
    project_base_dir_from_config,
    project_url_from_config,
)

PROJECTS_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects")


def _get_base_dir(runtime: ToolRuntime) -> str:
    """获取当前用户/线程的项目根目录。"""
    configurable = (runtime.config or {}).get("configurable", {})
    return str(project_base_dir_from_config(configurable))


def _resolve_safe_path(base_dir: str, file_path: str) -> tuple[Path, str]:
    """防止路径穿越，并兼容模型误传的 /projects/... 预览路径。"""
    base = Path(base_dir).resolve()
    normalized = _normalize_file_path(base, file_path)
    target = (base / normalized).resolve()
    try:
        rel_path = target.relative_to(base)
    except ValueError as exc:
        raise ValueError("路径不在当前项目目录内") from exc
    return target, str(rel_path)


def _normalize_file_path(base: Path, file_path: str) -> str:
    raw = (file_path or "").strip()
    if not raw:
        raise ValueError("文件路径不能为空")

    parsed = urlparse(raw)
    if parsed.scheme and parsed.netloc:
        raw = parsed.path

    raw = unquote(raw.split("#", 1)[0].split("?", 1)[0]).strip()
    projects_root = Path(PROJECTS_ROOT).resolve()

    if raw.startswith("/projects/"):
        target = (projects_root / raw.removeprefix("/projects/")).resolve()
        try:
            return str(target.relative_to(base))
        except ValueError as exc:
            raise ValueError("预览路径不属于当前项目") from exc

    if raw.startswith("projects/"):
        target = (projects_root / raw.removeprefix("projects/")).resolve()
        try:
            return str(target.relative_to(base))
        except ValueError as exc:
            raise ValueError("项目路径不属于当前项目") from exc

    path = Path(raw)
    if path.is_absolute():
        try:
            return str(path.resolve().relative_to(base))
        except ValueError as exc:
            raise ValueError("绝对路径不属于当前项目") from exc

    return raw


def _path_error(error: ValueError) -> str:
    return f"文件路径非法：{error}。请传当前项目内的相对路径，例如 index.html。"


@tool
def write_project_file(file_path: str, content: str, runtime: ToolRuntime) -> str:
    """将文件写入当前项目目录。用于保存生成的 HTML/CSS/JS 代码文件。

    Args:
        file_path: 文件相对路径，如 "index.html"、"css/style.css"
        content: 文件内容
    """
    base_dir = _get_base_dir(runtime)
    try:
        full_path, normalized_path = _resolve_safe_path(base_dir, file_path)
    except ValueError as e:
        return _path_error(e)

    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")

    # 返回可访问的 URL 路径
    configurable = (runtime.config or {}).get("configurable", {})
    preview_url = project_url_from_config(configurable, normalized_path)
    return f"文件已保存：{preview_url}\n[PREVIEW:{preview_url}]"


@tool
def read_project_file(file_path: str, runtime: ToolRuntime) -> str:
    """读取当前项目目录中的文件内容。

    Args:
        file_path: 文件相对路径，如 "index.html"
    """
    base_dir = _get_base_dir(runtime)
    try:
        full_path, normalized_path = _resolve_safe_path(base_dir, file_path)
    except ValueError as e:
        return _path_error(e)

    if not full_path.exists():
        return f"文件不存在：{normalized_path}"
    return full_path.read_text(encoding="utf-8")


@tool
def list_project_files(runtime: ToolRuntime) -> str:
    """列出当前项目目录中的所有文件。"""
    base_dir = _get_base_dir(runtime)
    if not os.path.exists(base_dir):
        return "项目目录为空，还没有生成任何文件。"

    files = []
    for root, _, filenames in os.walk(base_dir):
        for fname in filenames:
            rel = os.path.relpath(os.path.join(root, fname), base_dir)
            files.append(rel)

    if not files:
        return "项目目录为空，还没有生成任何文件。"
    return "\n".join(sorted(files))
