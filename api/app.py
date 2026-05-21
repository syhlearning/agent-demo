import sys
import os
import asyncio
import warnings
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from contextlib import asynccontextmanager
from datetime import datetime
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

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

from db.postgres import ensure_postgres
ensure_postgres()

from db.vector_store import setup as vs_setup
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.store.postgres import PostgresStore
from tools import (
    output_formatter, get_weather, web_search,
    save_user_info, get_user_info, delete_user_info,
    generate_wan_image, save_knowledge, save_long_document,
    search_knowledge, parse_and_save_document,
)

DB_URL = os.getenv("DATABASE_URL")

model = init_chat_model(
    model="deepseek-chat",
    model_provider="openai",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)

TOOLS = [
    output_formatter, get_weather, web_search,
    save_user_info, get_user_info, delete_user_info,
    generate_wan_image, save_knowledge, save_long_document,
    search_knowledge, parse_and_save_document,
]

SYSTEM_PROMPT = (
    f"你是一个有帮助的AI助手。当前日期和时间:{datetime.now().strftime('%Y年%m月%d日 %A %H:%M')}。"
    "在需要格式化输出时可以使用 output_formatter 工具，但普通对话直接回复即可。"
    "当使用 web_search 工具搜索信息后，回答中必须附上信息来源的网址链接。"
    "当用户要求生成图片、编辑图片、根据参考图生成图片时，使用 generate_wan_image 工具调用 wan2.7-image-pro。"
    "当用户主动告诉你稳定的个人信息（例如姓名、所在城市、职业、长期偏好、沟通习惯）时，"
    "使用 save_user_info 工具长期保存。不要保存密码、密钥、身份证号、银行卡号等敏感信息。"
    "当回答需要个性化信息，或用户问你是否记得某个信息时，先使用 get_user_info 工具读取长期记忆。"
    "当用户要求忘记或删除某项个人信息时，使用 delete_user_info 工具。"
    "不要显示的告诉我要查看你的信息或者我可以帮你存储你的信息，而是直接在对话中使用工具来存储和读取信息，来让对话更自然流畅。只需要回答用户的问题就行。"
    "当用户要求记住一段简短的知识、笔记时，使用 save_knowledge 工具保存。"
    "当用户要求保存较长的文档、报告、账单等内容时，使用 save_long_document 工具，它会自动分块存储。"
    "保存知识时，id 使用简短的中文语义命名，格式为'类型-标识'，例如'账单-2026-05'、'会议记录-项目启动'、'笔记-Python技巧'。"
    "用户要求更新已有内容时，先用 search_knowledge 找到原来的记录，search_knowledge 返回格式为 [id] 内容，取出方括号里的 id，再用相同 id 调用 save_knowledge 或 save_long_document 覆盖，不要新建。"
    "当用户询问之前保存的知识，或问题需要从历史笔记中检索时，使用 search_knowledge 工具。"
    "当用户提供本地文件路径并要求解析保存时，使用 parse_and_save_document 工具。"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with (
        PostgresSaver.from_conn_string(DB_URL) as checkpointer,
        PostgresStore.from_conn_string(DB_URL) as store,
    ):
        checkpointer.setup()
        store.setup()
        vs_setup()
        app.state.agent = create_agent(
            model=model,
            tools=TOOLS,
            system_prompt=SYSTEM_PROMPT,
            checkpointer=checkpointer,
            store=store,
        )
        yield


app = FastAPI(lifespan=lifespan)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")


_DEFAULT_USER_ID = os.getenv("USER_ID", "default-user")

class ChatRequest(BaseModel):
    message: str
    thread_id: str = f"chat-{_DEFAULT_USER_ID}"
    user_id: str = _DEFAULT_USER_ID


@app.get("/")
async def index():
    with open(os.path.join(BASE_DIR, "static", "index.html"), encoding="utf-8") as f:
        return HTMLResponse(f.read())


@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    agent = request.app.state.agent
    config = {
        "configurable": {
            "thread_id": req.thread_id,
            "user_id": req.user_id,
        }
    }

    async def generate():
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def run_stream():
            try:
                for chunk in agent.stream(
                    {"messages": [{"role": "user", "content": req.message}]},
                    config=config,
                    stream_mode="messages",
                ):
                    msg, metadata = chunk
                    if msg.content and metadata.get("langgraph_node") == "model":
                        loop.call_soon_threadsafe(queue.put_nowait, msg.content)
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        loop.run_in_executor(_executor, run_stream)

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item

    return StreamingResponse(generate(), media_type="text/plain; charset=utf-8")
