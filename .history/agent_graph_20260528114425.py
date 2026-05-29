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

# ══════════════════════════════════════════════════════════════════════════════
# ── 单 Agent 版本（已弃用，保留对比）─────────────────────────────────────────
# 特点：1 个 chatbot 节点 + 11 个工具，所有事情都由一个 Agent 处理
# 问题：prompt 过长，工具太多时 LLM 容易选错工具
# ══════════════════════════════════════════════════════════════════════════════

# class State(TypedDict):
#     messages: Annotated[list, add_messages]
#
# model_with_tools = model.bind_tools(TOOLS)
#
# def chatbot(state: State):
#     sys_msg = SystemMessage(content=SYSTEM_PROMPT)
#     response = model_with_tools.invoke([sys_msg] + state["messages"])
#     return {"messages": [response]}
#
# tool_node = ToolNode(TOOLS)
#
# SENSITIVE_TOOLS = {
#     "save_user_info", "delete_user_info",
#     "save_knowledge", "save_long_document",
#     "parse_and_save_document", "generate_wan_image",
# }
#
# def human_review(state: State):
#     last = state["messages"][-1]
#     tool_calls = last.tool_calls
#     decision = interrupt({
#         "question": "AI 要执行以下操作，是否允许？",
#         "tool_calls": [
#             {"name": tc["name"], "args": tc["args"]}
#             for tc in tool_calls
#         ],
#     })
#     if decision == "approve":
#         return state
#     reject_messages = [
#         ToolMessage(content="用户拒绝了此操作。", tool_call_id=tc["id"])
#         for tc in tool_calls
#     ]
#     return {"messages": reject_messages}
#
# def should_call_tool(state: State):
#     last = state["messages"][-1]
#     if hasattr(last, "tool_calls") and last.tool_calls:
#         tool_names = {tc["name"] for tc in last.tool_calls}
#         if tool_names & SENSITIVE_TOOLS:
#             return "human_review"
#         return "tools"
#     return END
#
# def after_review(state: State):
#     last = state["messages"][-1]
#     if isinstance(last, ToolMessage):
#         return "chatbot"
#     return "tools"
#
# builder = StateGraph(State)
# builder.add_node("chatbot", chatbot)
# builder.add_node("human_review", human_review)
# builder.add_node("tools", tool_node)
# builder.add_edge(START, "chatbot")
# builder.add_conditional_edges("chatbot", should_call_tool)
# builder.add_conditional_edges("human_review", after_review)
# builder.add_edge("tools", "chatbot")
# graph = builder.compile()


# ══════════════════════════════════════════════════════════════════════════════
# ── Supervisor 多 Agent 版本 ────────────────────────────────────────────────
# 特点：1 个 Supervisor（主管）+ 4 个专门的子 Agent，按职责分工
# 优势：每个 Agent 的 prompt 更短更精准，工具选择更准确，易于扩展
#
# 架构：
#   用户消息 → Supervisor（判断意图）
#     ├→ researcher（信息检索：搜索、天气）
#     ├→ memory_manager（记忆管理：用户信息增删查）
#     ├→ knowledge_manager（知识管理：文档存储和检索）
#     ├→ creator（创作：图片生成、格式化输出）
#     └→ FINISH（普通对话，Supervisor 直接回复）
# ══════════════════════════════════════════════════════════════════════════════
from pydantic import BaseModel, Field
from typing import Literal

# ── 子 Agent 定义 ────────────────────────────────────────────────────────────
# 每个子 Agent 有专门的工具集和 prompt，用 create_react_agent 创建
# create_react_agent 内部就是一个 chatbot → tools → chatbot 的循环（和单 Agent 版本结构相同）

researcher = create_agent(
    model=model,
    tools=[web_search, get_weather],
    prompt=(
        f"你是信息检索专家。当前时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}。"
        "负责搜索网络信息和查询天气。"
        "使用 web_search 搜索后，回答中必须附上信息来源的网址链接。"
    ),
    name="researcher",
)

memory_manager = create_agent(
    model=model,
    tools=[save_user_info, get_user_info, delete_user_info],
    prompt=(
        "你是用户记忆管理专家。"
        "负责保存、查询、删除用户的个人信息（姓名、城市、职业、偏好等）。"
        "不要保存密码、密钥、身份证号、银行卡号等敏感信息。"
        "直接在对话中自然地存取信息，不要告诉用户'我帮你保存了'之类的话。"
    ),
    name="memory_manager",
)

knowledge_manager = create_agent(
    model=model,
    tools=[save_knowledge, save_long_document, search_knowledge, parse_and_save_document],
    prompt=(
        "你是知识库管理专家。"
        "负责保存笔记、文档，以及检索已保存的知识。"
        "保存时 id 使用简短的中文语义命名，格式为'类型-标识'，例如'账单-2026-05'、'笔记-Python技巧'。"
        "更新已有内容时，先用 search_knowledge 找到原记录的 id，再用相同 id 覆盖。"
    ),
    name="knowledge_manager",
)

creator = create_agent(
    model=model,
    tools=[generate_wan_image, output_formatter],
    prompt=(
        "你是创作专家。"
        "负责生成图片和格式化输出。"
        "当用户要求生成、编辑图片时，使用 generate_wan_image 工具调用 wan2.7-image-pro。"
        "需要格式化输出时使用 output_formatter 工具。"
    ),
    name="creator",
)

# ── Supervisor（主管）节点 ────────────────────────────────────────────────────
# Supervisor 的职责：
# 1. 判断用户意图，决定交给哪个子 Agent
# 2. 普通对话（闲聊）自己直接回复，不转发
# 3. 子 Agent 完成后，把结果返回给用户

# 定义路由的输出结构，用 structured output 约束 LLM 只能输出这几个选项
AGENT_NAMES = ["researcher", "memory_manager", "knowledge_manager", "creator"]

class SupervisorDecision(BaseModel):
    """Supervisor 的路由决策"""
    next: Literal["researcher", "memory_manager", "knowledge_manager", "creator", "FINISH"] = Field(
        description="下一步交给哪个 Agent 处理，如果是普通对话则选 FINISH"
    )
    response: str = Field(
        default="",
        description="当 next 为 FINISH 时，Supervisor 直接回复用户的内容"
    )

SUPERVISOR_PROMPT = (
    f"你是一个智能助手团队的主管（Supervisor）。当前时间：{datetime.now().strftime('%Y年%m月%d日 %H:%M')}。\n\n"
    "你的团队有以下专家：\n"
    "- researcher：信息检索专家，负责搜索网络、查天气\n"
    "- memory_manager：记忆管理专家，负责保存/查询/删除用户个人信息\n"
    "- knowledge_manager：知识库专家，负责保存笔记/文档、检索知识\n"
    "- creator：创作专家，负责生成图片、格式化输出\n\n"
    "根据用户的消息，决定交给哪个专家处理。\n"
    "如果是普通对话（打招呼、闲聊、不需要工具的问题），选择 FINISH 并直接回复用户。\n"
    "如果用户的请求涉及多个领域，选择最主要的那个专家。"
)

# Supervisor 用 structured output 来保证输出格式
supervisor_model = model.with_structured_output(SupervisorDecision)


def supervisor_node(state):
    """主管节点：判断用户意图，决定路由到哪个子 Agent 或直接回复。"""
    sys_msg = SystemMessage(content=SUPERVISOR_PROMPT)
    decision = supervisor_model.invoke([sys_msg] + state["messages"])
    # 此时不是aimessage了，而是经过 structured output 解析后的 SupervisorDecision 对象，
    # 结构是 {"next": "researcher", "response": ""} 之类的

    if decision.next == "FINISH":
        # 普通对话，Supervisor 直接回复
        return {
            "messages": [AIMessage(content=decision.response)],
        }

    # 需要子 Agent 处理，记录路由目标
    return {"next": decision.next}


# ── 组装 Supervisor Graph ────────────────────────────────────────────────────

class SupervisorState(TypedDict):
    messages: Annotated[list, add_messages]
    next: str  # 下一个要执行的 Agent 名称


def route_after_supervisor(state: SupervisorState):
    """Supervisor 之后的路由：根据 next 字段决定走哪个子 Agent，没有 next 说明已直接回复。"""
    return state.get("next", END)


builder = StateGraph(SupervisorState)

# 添加节点
builder.add_node("supervisor", supervisor_node)
builder.add_node("researcher", researcher)
builder.add_node("memory_manager", memory_manager)
builder.add_node("knowledge_manager", knowledge_manager)
builder.add_node("creator", creator)

# 添加边
builder.add_edge(START, "supervisor")                                 # 入口 → 主管
builder.add_conditional_edges("supervisor", route_after_supervisor, {  # 主管 → 子Agent / 结束
    "researcher": "researcher",
    "memory_manager": "memory_manager",
    "knowledge_manager": "knowledge_manager",
    "creator": "creator",
    END: END,
})
# 所有子 Agent 完成后 → 结束（结果已在 messages 里）
builder.add_edge("researcher", END)
builder.add_edge("memory_manager", END)
builder.add_edge("knowledge_manager", END)
builder.add_edge("creator", END)

# 顶层暴露 graph 变量，langgraph.json 通过 "./agent_graph.py:graph" 找到它
# checkpointer 和 store 由框架根据 langgraph.json 自动注入
graph = builder.compile()
# ─────────────────────────────────────────────────────────────────────────────
