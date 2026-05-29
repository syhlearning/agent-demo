import sys
import os
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

load_dotenv()

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
    # llama_store 的 PGVectorStore 会自动建表（perform_setup=True）
    yield


app = FastAPI(lifespan=lifespan)

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
):
    import tempfile
    from tools import parse_and_save_document

    # 取文件扩展名（如 .pdf），让临时文件保持正确格式供 LlamaCloud 识别
    suffix = os.path.splitext(file.filename or "")[1]

    # 把上传的文件写入本地临时文件
    # delete=False：关闭后不自动删，留给 parse_and_save_document 读取
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name  # 记住路径，后面用完要手动删

    try:
        # 调用解析工具：LlamaCloud 解析文件 → LlamaIndex 分块存入向量数据库
        result = parse_and_save_document.invoke({"file_path": tmp_path, "doc_id": doc_id})
        if "失败" in result:
            return JSONResponse({"ok": False, "message": result}, status_code=500)
        return JSONResponse({"ok": True, "message": result})
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
