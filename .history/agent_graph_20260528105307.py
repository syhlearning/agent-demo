import sys
import os
import warnings

sys.path.insert(0, os.path.dirname(__file__))

# ensure_postgres() 已不需要，数据库由 langgraph up 管理
# from db.postgres import ensure_postgres
# ensure_postgres()

from dotenv import load_dotenv
from langchain_core._api.deprecation import LangChainPendingDeprecationWarning
from langchain_core.load.load import Reviver

warnings.filterwarnings(
    "ignore",
    message="The default value of .*allowed_objects.* will change.*",
    category=LangChainPendingDeprecationWarning,
)

from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.serde import jsonplus
from datetime import datetime
from tools import (
    output_formatter,
    get_weather,
    web_search,
    save_user_info,
    get_user_info,
    delete_user_info,
    generate_wan_image,
    save_knowledge,
    save_long_document,
    search_knowledge,
    parse_and_save_document,
)
# 持久存储（长期记忆）- main() 命令行测试用
from langgraph.store.postgres import PostgresStore
# from db.vector_store import setup as vs_setup  ← 旧版 LangChain PGVector，已切换到 llama_store，不再需要

jsonplus.LC_REVIVER = Reviver(allowed_objects="core") 

# 自定义agent，不用langchain内置的Agent框架，因为我们需要在系统提示里明确告诉模型一些工具使用规范，内置Agent的系统提示不够灵活。
from langgraph.graph import StateGraph,START,END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.types import interrupt
from langchain_core.messages import SystemMessage, AIMessage, ToolMessage
from typing import TypedDict, Annotated

# 加载 .env 文件
load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
USER_ID = os.getenv("USER_ID", "default-user")

# 初始化聊天模型。wan2.7-image-pro 是图片模型，通过 generate_wan_image 工具调用。
model = init_chat_model(
    model="deepseek-chat",
    model_provider="openai",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
)

# ── LangGraph Server 标准格式 ──────────────────────────────────────────────
# checkpointer/store 由 langgraph.json 框架自动注入，无需手动初始化
# 向量表用的是 llama_store（perform_setup=True），首次访问时自动建表，无需手动调用

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

TOOLS = [
    output_formatter, get_weather, web_search,
    save_user_info, get_user_info, delete_user_info,
    generate_wan_image, save_knowledge, save_long_document,
    search_knowledge, parse_and_save_document,
]

# 顶层暴露 graph 变量，langgraph.json 通过 "./agent_graph.py:graph" 找到它
# checkpointer 和 store 不需要手动传，框架根据 langgraph.json 配置自动注入
# create_agent是langchain里面内置的帮我们做了很多事情的函数，帮我们把模型、工具、系统提示等组装成一个完整的智能体（agent），我们只需要把它返回给框架就行了
# graph = create_agent(
#     model=model,
#     tools=TOOLS,
#     system_prompt=SYSTEM_PROMPT,
# )

# 下面是自定义agent的版本，我们直接把 StateGraph 当成智能体，自己控制状态和工具调用，更灵活地满足我们在系统提示里对工具使用规范的要求。
class State(TypedDict):
    messages: Annotated[list, add_messages]

# 把工具绑定到模型，让 LLM 知道有哪些工具可以调用
model_with_tools = model.bind_tools(TOOLS)


# ── 节点 ──────────────────────────────────────────────────────────────────────

def chatbot(state: State):
    """聊天节点：把 system prompt + 对话历史发给 LLM，返回 AI 回复。"""
    sys_msg = SystemMessage(content=SYSTEM_PROMPT)
    response = model_with_tools.invoke([sys_msg] + state["messages"])
    return {"messages": [response]}


# 工具节点：自动执行 LLM 返回的 tool_calls，把结果作为 ToolMessage 追加到 messages
tool_node = ToolNode(TOOLS)


# 需要人工审核的敏感工具（写入、删除类操作）
SENSITIVE_TOOLS = {
    "save_user_info", "delete_user_info",
    "save_knowledge", "save_long_document",
    "parse_and_save_document", "generate_wan_image",
}


def human_review(state: State):
    """人工审核节点：对敏感工具调用暂停，等用户确认。"""
    last = state["messages"][-1]
    tool_calls = last.tool_calls

    # 把工具调用信息发给前端，暂停等待用户决定
    decision = interrupt({
        "question": "AI 要执行以下操作，是否允许？",
        "tool_calls": [
            {"name": tc["name"], "args": tc["args"]}
            for tc in tool_calls
        ],
    })

    if decision == "approve":
        # 用户同意 → 直接放行，让后续 tools 节点执行
        return state

    # 用户拒绝 → 为每个 tool_call 生成一条拒绝的 ToolMessage，
    # 这样 LLM 知道工具被拒绝了，不会报错（LLM 要求每个 tool_call 都有对应的 ToolMessage）
    reject_messages = [
        ToolMessage(content="用户拒绝了此操作。", tool_call_id=tc["id"])
        for tc in tool_calls
    ]
    return {"messages": reject_messages}


# ── 条件路由 ──────────────────────────────────────────────────────────────────

def should_call_tool(state: State):
    """判断 LLM 回复里有没有 tool_calls，有就走工具节点，没有就结束。"""
    last = state["messages"][-1]
    if hasattr(last, "tool_calls") and last.tool_calls:
        # 检查是否包含敏感工具，是的话先走人工审核
        tool_names = {tc["name"] for tc in last.tool_calls}
        if tool_names & SENSITIVE_TOOLS:
            return "human_review"
        return "tools"
    return END


def after_review(state: State):
    """审核后的路由：如果最后一条是 ToolMessage（拒绝），回 chatbot 让 LLM 回复用户；否则走 tools 执行。"""
    last = state["messages"][-1]
    if isinstance(last, ToolMessage):
        # 用户拒绝了，ToolMessage 已经添加，回 chatbot 让 LLM 基于拒绝结果回复
        return "chatbot"
    # 用户同意了，去执行工具
    return "tools"


# ── 组装 Graph ────────────────────────────────────────────────────────────────

builder = StateGraph(State)
builder.add_node("chatbot", chatbot)
builder.add_node("human_review", human_review)
builder.add_node("tools", tool_node)

builder.add_edge(START, "chatbot")                           # 入口 → chatbot
builder.add_conditional_edges("chatbot", should_call_tool)   # chatbot → 审核/工具/结束
builder.add_conditional_edges("human_review", after_review)  # 审核 → 工具(同意) or chatbot(拒绝)
builder.add_edge("tools", "chatbot")                         # 工具结果 → 回到 chatbot 继续思考

# 顶层暴露 graph 变量，langgraph.json 通过 "./agent_graph.py:graph" 找到它
# checkpointer 和 store 由框架根据 langgraph.json 自动注入
graph = builder.compile()
# ─────────────────────────────────────────────────────────────────────────────
