import sys
import os
import warnings

sys.path.insert(0, os.path.dirname(__file__))

from db.postgres import ensure_postgres
ensure_postgres()

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
from langchain_core.messages import SystemMessage
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

model_with_tools = model.bind_tools(TOOLS) 

def chatbot(state: State) -> str:
    last=state["messages"][-1]
 if hasattr(last, "tool_calls") and last.tool_calls:
# ─────────────────────────────────────────────────────────────────────────────


# def main():
#     print("=== AI 智能体聊天助手 (LangGraph) ===")
#     print("输入 'quit' 退出\n")

#     with (
#         # 记忆1 - 短期记忆：当前会话的对话历史和 graph 状态
#         # 存储位置：checkpoints / checkpoint_blobs / checkpoint_writes 表
#         # 作用：断点续话，下次启动同一 thread_id 可继续上次对话
#         PostgresSaver.from_conn_string(DB_URL) as checkpointer,

#         # 记忆2 - 长期记忆（结构化）：跨会话的用户个人信息
#         # 存储位置：store 表
#         # 作用：记住用户姓名、城市、职业、偏好等稳定信息，通过 save/get/delete_user_info 工具操作
#         PostgresStore.from_conn_string(DB_URL) as store,
#     ):
#         checkpointer.setup()  # 首次运行时自动建表
#         store.setup()         # 首次运行时自动建表

#         # 记忆3 - 长期记忆（向量）：知识、笔记、文档的语义检索
#         # 存储位置：llama_vector_docs 表（llama_store.py，已从旧版 vector_store 迁移）
#         # 作用：存储任意文本内容，支持语义相似度检索，通过 save_knowledge / save_long_document / search_knowledge 工具操作
#         # vs_setup() ← 不再需要，llama_store 的 perform_setup=True 首次访问时自动建表
#         agent = create_agent(
#             model=model,
#             tools=[
#                 output_formatter,
#                 get_weather,
#                 web_search,
#                 save_user_info,
#                 get_user_info,
#                 delete_user_info,
#                 generate_wan_image,
#                 save_knowledge,
#                 save_long_document,
#                 search_knowledge,
#                 parse_and_save_document,
#             ],
#             system_prompt=(
#                 f"你是一个有帮助的AI助手。当前日期和时间:{datetime.now().strftime('%Y年%m月%d日 %A %H:%M')}。"
#                 "在需要格式化输出时可以使用 output_formatter 工具，但普通对话直接回复即可。"
#                 "当使用 web_search 工具搜索信息后，回答中必须附上信息来源的网址链接。"
#                 "当用户要求生成图片、编辑图片、根据参考图生成图片时，使用 generate_wan_image 工具调用 wan2.7-image-pro。"
#                 "当用户主动告诉你稳定的个人信息（例如姓名、所在城市、职业、长期偏好、沟通习惯）时，"
#                 "使用 save_user_info 工具长期保存。不要保存密码、密钥、身份证号、银行卡号等敏感信息。"
#                 "当回答需要个性化信息，或用户问你是否记得某个信息时，先使用 get_user_info 工具读取长期记忆。"
#                 "当用户要求忘记或删除某项个人信息时，使用 delete_user_info 工具。"
#                 "不要显示的告诉我要查看你的信息或者我可以帮你存储你的信息，而是直接在对话中使用工具来存储和读取信息，来让对话更自然流畅。只需要回答用户的问题就行"
#                 "当用户要求记住一段简短的知识、笔记时，使用 save_knowledge 工具保存。"
#                 "当用户要求保存较长的文档、报告、账单等内容时，使用 save_long_document 工具，它会自动分块存储。"
#                 "保存知识时，id 使用简短的中文语义命名，格式为'类型-标识'，例如'账单-2026-05'、'会议记录-项目启动'、'笔记-Python技巧'。"
#                 "用户要求更新已有内容时，先用 search_knowledge 找到原来的记录，search_knowledge 返回格式为 [id] 内容，取出方括号里的 id，再用相同 id 调用 save_knowledge 或 save_long_document 覆盖，不要新建。"
#                 "当用户询问之前保存的知识，或问题需要从历史笔记中检索时，使用 search_knowledge 工具。"
#             ),
#             checkpointer=checkpointer,
#             store=store,
#         )

#         config = {"configurable": {"thread_id": f"chat-{USER_ID}", "user_id": USER_ID}}

#         while True:
#             user_input = input("你: ").strip()
#             if not user_input:
#                 continue
#             if user_input.lower() == "quit":
#                 print("再见！")
#                 break
#             try:
#                 print("AI: ", end="", flush=True)
#                 for chunk in agent.stream(
#                     {"messages": [{"role": "user", "content": user_input}]},
#                     config=config,
#                     stream_mode="messages",
#                 ):
#                     msg, metadata = chunk
#                     # print(f"Chunk received: {msg} with metadata {metadata}\n")  # 调试输出
#                     if msg.content and metadata.get("langgraph_node") == "model":
#                         print(msg.content, end="", flush=True)
#                 print()  # 换行
#             except Exception as e:
#                 print(f"出错了: {e}\n")


# def main():
#     """使用 stream_mode='values' 的版本"""
#     print("=== AI 智能体聊天助手 (LangGraph) ===")
#     print("输入 'quit' 退出\n")

#     while True:
#         user_input = input("你: ").strip()
#         if not user_input:
#             continue
#         if user_input.lower() == "quit":
#             print("再见！")
#             break
#         try:
#             for chunk in agent.stream(
#                 {"messages": [{"role": "user", "content": user_input}]},
#                 config=config,
#                 stream_mode="values",
#             ):
#                 # chunk 是完整的 state 字典: {"messages": [msg1, msg2, ...]}
#                 # 每次拿最后一条消息，就是最新的 AI 回复
#                 print(f"Chunk received: {chunk}\n")  # 调试输出
#                 last_msg = chunk["messages"][-1]
#                 if last_msg.type == "ai" and last_msg.content:
#                     print(f"AI: {last_msg.content}\n")
#         except Exception as e:
#             print(f"出错了: {e}\n")


# if __name__ == "__main__":
#     main()
