import sys
import os
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

from api.auth.router import router as auth_router
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
from langchain_core.load.load import Reviver
from langgraph.checkpoint.serde import jsonplus

warnings.filterwarnings(
    "ignore",
    message="The default value of .*allowed_objects.* will change.*",
    category=LangChainPendingDeprecationWarning,
)
jsonplus.LC_REVIVER = Reviver(allowed_objects="core")

# ensure_postgres() 已不需要，数据库由 langgraph up 管理
# 如需本地单独启动旧容器，取消下面注释：
# from db.postgres import ensure_postgres
# ensure_postgres()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from db.init_db import init_auth_db

        await init_auth_db()
        print("[auth db] users and refresh_tokens ready")
    except Exception as e:
        print(f"[auth db] skipped: {e}")

    # llama_store 的 PGVectorStore 会自动建表（perform_setup=True）
    try:
        from db.checkpoint_cleanup import auto_cleanup_enabled, cleanup_old_checkpoints

        if auto_cleanup_enabled():
            result = cleanup_old_checkpoints()
            print(f"[checkpoint cleanup] {result}")
    except Exception as e:
        print(f"[checkpoint cleanup] skipped: {e}")
    yield


app = FastAPI(lifespan=lifespan)
app.include_router(auth_router)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
PROJECTS_DIR = os.path.join(BASE_DIR, "projects")
os.makedirs(PROJECTS_DIR, exist_ok=True)

app.mount("/projects", StaticFiles(directory=PROJECTS_DIR, html=True), name="projects")
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


@app.get("/")
async def index():
    with open(os.path.join(BASE_DIR, "static", "index.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.post("/upload")
async def upload(
    file: UploadFile = File(...),   # 前端上传的文件（multipart）
    doc_id: str = Form(...),        # 前端表单里的文档 ID
    org_id: str = Form("starlinke"),
    user_id: str = Form("default-user"),
    brand_id: str = Form("default-brand"),
    project_id: str = Form(""),
    doc_type: str = Form("knowledge"),
):
    import tempfile
    from tools import parse_document_to_text, save_document_text
    from tools.brand_context import _safe_segment, save_brand_document_text

    # 取文件扩展名（如 .pdf），让临时文件保持正确格式供 LlamaCloud 识别
    suffix = os.path.splitext(file.filename or "")[1]

    # 把上传的文件写入本地临时文件
    # delete=False：关闭后不自动删，留给 parse_and_save_document 读取
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name  # 记住路径，后面用完要手动删

    try:
        # LlamaCloud/文本解析 → LlamaIndex 分块存入向量数据库
        full_text = parse_document_to_text(tmp_path)
        safe_org_id = _safe_segment(org_id, "starlinke")
        safe_user_id = _safe_segment(user_id, "default-user")
        safe_brand_id = _safe_segment(brand_id, "default-brand")
        safe_project_id = _safe_segment(project_id, "default-project") if project_id else ""
        safe_doc_id = _safe_segment(doc_id, "document")
        scoped_doc_id = f"{safe_org_id}:{safe_brand_id}:{doc_type}:{safe_doc_id}"
        chunks = save_document_text(
            scoped_doc_id,
            full_text,
            metadata={
                "org_id": safe_org_id,
                "brand_id": safe_brand_id,
                "user_id": safe_user_id,
                "project_id": safe_project_id,
                "doc_type": doc_type,
                "scope": "brand_document" if doc_type in {"brand_skill", "landing_page_rule", "product_doc", "reference"} else "knowledge",
            },
        )

        brand_saved = False
        if doc_type in {"brand_skill", "landing_page_rule", "product_doc", "reference"}:
            save_brand_document_text(
                org_id=safe_org_id,
                brand_id=safe_brand_id,
                doc_id=doc_id,
                doc_type=doc_type,
                text=full_text,
                source_filename=file.filename or "",
            )
            brand_saved = True

        message = f"已解析并保存文档「{doc_id}」，自动分成 {chunks} 块"
        if brand_saved:
            message += f"，并已写入公司「{safe_org_id}」品牌「{safe_brand_id}」的 {doc_type} 资料"
        if safe_project_id:
            message += f"，当前项目：{safe_project_id}"
        return JSONResponse({"ok": True, "message": message, "brandSaved": brand_saved})
    except Exception as e:
        # 捕获所有异常，统一返回 JSON，避免前端收到空响应报错
        return JSONResponse({"ok": False, "message": str(e)}, status_code=500)
    finally:
        # 无论成功还是失败都删掉临时文件，防止磁盘堆积
        os.unlink(tmp_path)


@app.get("/api/conversations/{user_id}")
async def list_conversations(user_id: str):
    """扫描 /projects/{user_id}/ 子目录，返回 thread_id 列表。"""
    user_dir = os.path.join(PROJECTS_DIR, user_id)
    if not os.path.isdir(user_dir):
        return JSONResponse([])
    threads = []
    for name in sorted(os.listdir(user_dir), reverse=True):
        full = os.path.join(user_dir, name)
        if os.path.isdir(full):
            threads.append({
                "threadId": name,
                "createdAt": int(os.path.getctime(full) * 1000),
            })
    return JSONResponse(threads)


@app.get("/api/checkpoint-cleanup/stats")
async def checkpoint_cleanup_preview(days: int = Query(30, ge=1, le=3650)):
    """查看超过保留期的 LangGraph checkpoint 数量，不删除。"""
    from db.checkpoint_cleanup import checkpoint_cleanup_stats

    return JSONResponse(checkpoint_cleanup_stats(days))


@app.post("/api/checkpoint-cleanup")
async def checkpoint_cleanup(
    days: int = Query(30, ge=1, le=3650),
    dry_run: bool = Query(False),
):
    """清理超过保留期的 LangGraph 对话 checkpoint；不删除页面项目和品牌资料。"""
    from db.checkpoint_cleanup import cleanup_old_checkpoints

    return JSONResponse(cleanup_old_checkpoints(days=days, dry_run=dry_run))
