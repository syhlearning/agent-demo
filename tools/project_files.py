# ── 项目文件管理工具 ──────────────────────────────────────────────────────────
# 当前实现：本地文件系统（projects/{user_id}/{thread_id}/）
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
from langchain_core.tools import tool
from langchain.tools import ToolRuntime

PROJECTS_ROOT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects")


def _get_base_dir(runtime: ToolRuntime) -> str:
    """获取当前用户/线程的项目根目录。"""
    configurable = (runtime.config or {}).get("configurable", {})
    user_id = str(configurable.get("user_id") or "default-user")
    thread_id = str(configurable.get("thread_id") or "default-thread")
    return os.path.join(PROJECTS_ROOT, user_id, thread_id)


def _safe_path(base_dir: str, file_path: str) -> Path:
    """防止路径穿越：确保最终路径在 base_dir 内。"""
    base = Path(base_dir).resolve()
    target = (base / file_path).resolve()
    target.relative_to(base)  # 不在 base 内会抛 ValueError
    return target


@tool
def write_project_file(file_path: str, content: str, runtime: ToolRuntime) -> str:
    """将文件写入当前项目目录。用于保存生成的 HTML/CSS/JS 代码文件。

    Args:
        file_path: 文件相对路径，如 "index.html"、"css/style.css"
        content: 文件内容
    """
    base_dir = _get_base_dir(runtime)
    full_path = _safe_path(base_dir, file_path)

    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")

    # 返回可访问的 URL 路径
    configurable = (runtime.config or {}).get("configurable", {})
    user_id = str(configurable.get("user_id") or "default-user")
    thread_id = str(configurable.get("thread_id") or "default-thread")
    return f"文件已保存：/projects/{user_id}/{thread_id}/{file_path}"


@tool
def read_project_file(file_path: str, runtime: ToolRuntime) -> str:
    """读取当前项目目录中的文件内容。

    Args:
        file_path: 文件相对路径，如 "index.html"
    """
    base_dir = _get_base_dir(runtime)
    full_path = _safe_path(base_dir, file_path)

    if not full_path.exists():
        return f"文件不存在：{file_path}"
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
