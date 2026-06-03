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
from datetime import datetime, timezone, timedelta

# 北京时区
_BJT = timezone(timedelta(hours=8))

def _now_str():
    """每次调用时获取当前北京时间字符串。"""
    return datetime.now(_BJT).strftime('%Y年%m月%d日 %A %H:%M')
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
from tools.project_files import write_project_file, read_project_file, list_project_files
from tools.brand_context import get_brand_profile, search_brand_skills, validate_landing_page
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

# model = init_chat_model(
#     model="deepseek-chat",
#     model_provider="openai",
#     api_key=os.getenv("DEEPSEEK_API_KEY"),
#     base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
# )
model = init_chat_model(
    model="deepseek-v3",
    model_provider="openai",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# Supervisor 专用模型（Qwen 支持 structured output，DeepSeek 该功能不稳定）
supervisor_llm = init_chat_model(
    model="qwen-turbo",
    model_provider="openai",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
)

# ── LangGraph Server 标准格式 ──────────────────────────────────────────────
# checkpointer/store 由 langgraph.json 框架自动注入，无需手动初始化
# 向量表用的是 llama_store（perform_setup=True），首次访问时自动建表，无需手动调用

SYSTEM_PROMPT = (
     f"你是一个有帮助的AI助手。当前日期和时间:{_now_str()}。"
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
    get_brand_profile, search_brand_skills, validate_landing_page,
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
    system_prompt=(
        f"你是信息检索专家。当前时间：{_now_str()}。"
        "负责搜索网络信息和查询天气。"
        "使用 web_search 搜索后，回答中必须附上信息来源的网址链接。"
    ),
    name="researcher",
)

memory_manager = create_agent(
    model=model,
    tools=[save_user_info, get_user_info, delete_user_info],
    system_prompt=(
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
    system_prompt=(
        "你是知识库管理专家。"
        "负责保存笔记、文档，以及检索已保存的知识。"
        "保存时 id 使用简短的中文语义命名，格式为'类型-标识'，例如'账单-2026-05'、'笔记-Python技巧'。"
        "更新已有内容时，先用 search_knowledge 找到原记录的 id，再用相同 id 覆盖。"
        "\n\n检索策略（Agentic RAG）：\n"
        "1. 如果用户的查询很模糊（比如'上次那个东西'、'之前的记录'），先根据对话上下文推测用户想找什么，改写成具体的检索词再搜索。\n"
        "2. 调用 search_knowledge 后，检查返回结果的相关性分数（score）和内容：\n"
        "   - 如果最高分低于 0.5，或内容明显与用户问题不相关，换一组关键词（同义词、更具体或更宽泛的描述）重新检索。\n"
        "   - 最多重试 2 次。\n"
        "3. 多次检索仍无相关结果，如实告诉用户没有找到相关知识。"
    ),
    name="knowledge_manager",
)

creator = create_agent(
    model=model,
    tools=[generate_wan_image, output_formatter],
    system_prompt=(
        "你是创作专家。"
        "负责生成图片和格式化输出。"
        "当用户要求生成、编辑图片时，使用 generate_wan_image 工具调用 wan2.7-image-pro。"
        "需要格式化输出时使用 output_formatter 工具。"
    ),
    name="creator",
)

code_generator = create_agent(
    model=model,
    tools=[
        get_brand_profile,
        search_brand_skills,
        write_project_file,
        read_project_file,
        list_project_files,
        validate_landing_page,
    ],
    system_prompt=(
        "你是网页代码生成专家。负责生成完整的 HTML/CSS/JS 落地页代码。\n\n"
        "工作流程：\n"
        "1. 任何生成或修改落地页任务，必须先用 get_brand_profile 读取当前品牌规范；如果规范不足，再用 search_brand_skills 检索相关资料。\n"
        "2. 如果用户要求修改已有页面，必须先用 list_project_files 查看当前项目文件，再用 read_project_file 读取相关文件，尤其是 index.html。\n"
        "   调用 read_project_file、write_project_file、validate_landing_page 时，file_path 只能传当前项目内的相对路径，例如 index.html，不要传 /projects/... 预览路径或绝对路径。\n"
        "3. 根据用户需求、品牌 skill、产品资料生成或修改完整的 HTML 页面（CSS 和 JS 内联在 HTML 中）。\n"
        "4. 必须使用 write_project_file 工具把最终页面保存为 index.html。\n"
        "5. 保存后必须调用 validate_landing_page 校验 index.html；如果返回 issues，必须修复后再次 write_project_file 保存。\n"
        "6. 禁止只把代码输出给用户手动保存；禁止声称自己无法保存、无法修改文件，除非 write_project_file 工具明确返回失败。\n"
        "7. 修改已有页面时，不要创建 index-tail.html、patch.js、sand-patch.js 等补丁文件来代替修改；必须把合并后的完整结果写回 index.html。\n"
        "8. 代码应该是完整的、可直接在浏览器打开的 HTML 文件。\n"
        "9. 设计必须服从品牌 skill：品牌色、字体/排版、语气、必需模块、禁用项的优先级高于通用审美建议。\n"
        "10. 保存和校验后，在回复的最后一行必须包含预览标记，格式为：\n"
        "   [PREVIEW:/projects/{user_id}/{brand_id}/{project_id}/index.html]\n"
        "   其中 user_id、brand_id、project_id 从 write_project_file 的返回值中提取；如果返回的是旧路径，也必须原样使用返回值里的路径。\n\n"
        "重要 — Shadow DOM 兼容：\n"
        "生成的页面最终会被下载并嵌入到主站（主站有自己的头部和尾部），通过 Shadow DOM 隔离。\n"
        "因此你必须遵守以下规则：\n"
        "- 所有 CSS 必须写在 <style> 标签内（内联在 HTML 里），不要用 <link> 引用外部样式表\n"
        "- 不要依赖全局样式（如 body、html 选择器设置背景色/字体），改为用一个根容器 div 包裹全部内容，样式写在该容器上\n"
        "- JS 中不要使用 document.body / document.documentElement，用 document.querySelector('.root-container') 或相对查询\n"
        "- 字体可以用 @import url(...) 写在 <style> 顶部，Shadow DOM 中 @import 仍然生效\n"
        "- 页面必须包含完整的 <!DOCTYPE html> 声明（独立预览时需要），同时确保核心内容在一个根容器 div 内，方便主站提取后挂载到 Shadow DOM\n\n"
        "注意：确保在移动端也有良好的展示效果。"
    ),
    name="code_generator",
)

# ── Supervisor（主管）节点 ────────────────────────────────────────────────────
# Supervisor 的职责：
# 1. 判断用户意图，决定交给哪个子 Agent
# 2. 普通对话（闲聊）自己直接回复，不转发
# 3. 子 Agent 完成后，把结果返回给用户

# 定义路由的输出结构，用 structured output 约束 LLM 只能输出这几个选项
AGENT_NAMES = ["researcher", "memory_manager", "knowledge_manager", "creator", "code_generator"]

class SupervisorDecision(BaseModel):
    """Supervisor 的路由决策"""
    next: Literal["researcher", "memory_manager", "knowledge_manager", "creator", "code_generator", "FINISH"] = Field(
        description="下一步交给哪个 Agent 处理，如果是普通对话则选 FINISH"
    )
    response: str = Field(
        default="",
        description="当 next 为 FINISH 时，Supervisor 直接回复用户的内容"
    )

SUPERVISOR_PROMPT_TEMPLATE = (
    "你是一个智能助手团队的主管（Supervisor）。当前时间：{time}。\n\n"
    "你的团队有以下专家：\n"
    "- researcher：信息检索专家，负责搜索网络、查天气\n"
    "- memory_manager：记忆管理专家，负责保存/查询/删除用户个人信息\n"
    "- knowledge_manager：知识库专家，负责保存笔记/文档、检索知识\n"
    "- creator：创作专家，负责生成图片、格式化输出\n"
    "- code_generator：网页代码专家，负责生成、修改、读取、保存 HTML/CSS/JS 落地页和网页代码，拥有读写项目文件的工具\n\n"
    "根据用户的消息，决定交给哪个专家处理。\n"
    "如果是普通对话（打招呼、闲聊、不需要工具的问题），选择 FINISH 并直接回复用户。\n"
    "如果用户要求创建、修改、更新、修复、保存、预览网页/页面/落地页/HTML/CSS/JS/项目文件，必须选择 code_generator，不能选择 FINISH，也不要直接输出代码让用户手动保存。\n"
    "如果用户的请求涉及多个领域，选择最主要的那个专家。\n"
    "如果是新对话的第一条消息，且需要个性化回复，先交给 memory_manager 读取用户信息。"
)

# Supervisor 用 structured output 来保证输出格式
supervisor_model = supervisor_llm.with_structured_output(SupervisorDecision)


def supervisor_node(state):
    """主管节点：判断用户意图，决定路由到哪个子 Agent 或直接回复。"""
    sys_msg = SystemMessage(content=SUPERVISOR_PROMPT_TEMPLATE.format(time=_now_str()))
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


# 需要人工审核的子 Agent（包含写入、删除、生成类工具）
# researcher 只做搜索和查天气，不需要审核
SENSITIVE_AGENTS = {"memory_manager", "knowledge_manager", "creator", "code_generator"}


def human_review(state: SupervisorState):
    """人工审核节点：在敏感子 Agent 执行前暂停，等用户确认。"""
    next_agent = state.get("next", "")

    # 告诉前端即将执行哪个子 Agent，暂停等待用户决定
    decision = interrupt({
        "question": f"AI 要将任务交给「{next_agent}」处理，是否允许？",
        "tool_calls": [
            {"name": next_agent, "args": {"action": "执行该专家的全部操作"}}
        ],
    })

    if decision == "approve":
        # 用户同意 → 继续执行子 Agent
        return state

    # 用户拒绝 → 直接回复拒绝信息，不执行子 Agent
    return {
        "messages": [AIMessage(content="好的，已取消该操作。")],
        "next": "REJECTED",  # 标记为拒绝，路由到 END
    }


def route_after_supervisor(state: SupervisorState):
    """Supervisor 之后的路由：根据 next 字段决定走哪个子 Agent，没有 next 说明已直接回复。"""
    next_val = state.get("next", END)
    if next_val in SENSITIVE_AGENTS:
        return "human_review"  # 敏感 Agent 先审核
    return next_val


def route_after_review(state: SupervisorState):
    """审核后的路由：同意则走子 Agent，拒绝则结束。"""
    next_val = state.get("next", END)
    if next_val == "REJECTED":
        return END
    return next_val


builder = StateGraph(SupervisorState)

# 添加节点
builder.add_node("supervisor", supervisor_node)
builder.add_node("human_review", human_review)
builder.add_node("researcher", researcher)
builder.add_node("memory_manager", memory_manager)
builder.add_node("knowledge_manager", knowledge_manager)
builder.add_node("creator", creator)
builder.add_node("code_generator", code_generator)

# 添加边
builder.add_edge(START, "supervisor")                                 # 入口 → 主管
builder.add_conditional_edges("supervisor", route_after_supervisor, {  # 主管 → 审核/子Agent/结束
    "human_review": "human_review",
    "researcher": "researcher",
    "code_generator": "code_generator",
    END: END,
})
builder.add_conditional_edges("human_review", route_after_review, {   # 审核 → 子Agent(同意) / 结束(拒绝)
    "memory_manager": "memory_manager",
    "knowledge_manager": "knowledge_manager",
    "creator": "creator",
    "code_generator": "code_generator",
    END: END,
})
# 所有子 Agent 完成后 → 结束（结果已在 messages 里）
builder.add_edge("researcher", END)
builder.add_edge("memory_manager", END)
builder.add_edge("knowledge_manager", END)
builder.add_edge("creator", END)
builder.add_edge("code_generator", END)

# 顶层暴露 graph 变量，langgraph.json 通过 "./agent_graph.py:graph" 找到它
# checkpointer 和 store 由框架根据 langgraph.json 自动注入
graph = builder.compile()
# ─────────────────────────────────────────────────────────────────────────────
