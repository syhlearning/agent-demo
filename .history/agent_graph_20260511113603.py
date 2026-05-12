import sys
import os
import warnings

sys.path.insert(0, os.path.dirname(__file__))

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
from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde import jsonplus
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from datetime import datetime
from tools import (
    output_formatter,
    get_weather,
    web_search,
    save_user_info,
    get_user_info,
    delete_user_info,
)
# 持久存储（长期记忆）
from langgraph.store.postgres import PostgresStore

jsonplus.LC_REVIVER = Reviver(allowed_objects="core")


# 加载 .env 文件
load_dotenv()

DB_URL = os.getenv("DATABASE_URL")
USER_ID = os.getenv("USER_ID", "default-user")

# 初始化聊天模型
model = init_chat_model(
    model="deepseek-chat",
    model_provider="openai",
    api_key=os.getenv("DASHSCOPE_API_KEY"),
    base_url=os.getenv("DASHSCOPE_BASE_URL"),
)


def main():
    print("=== AI 智能体聊天助手 (LangGraph) ===")
    print("输入 'quit' 退出\n")

    # MemorySaver: 当前会话的对话历史（内存中）
    # PostgresStore: 跨会话的长期记忆（持久化到 Postgres）
    with PostgresStore.from_conn_string(DB_URL) as store:
        store.setup()  # 首次运行时自动创建表

        agent = create_agent(
            model=model,
            tools=[
                output_formatter,
                get_weather,
                web_search,
                save_user_info,
                get_user_info,
                delete_user_info,
            ],
            system_prompt=(
                f"你是一个有帮助的AI助手。当前日期和时间:{datetime.now().strftime('%Y年%m月%d日 %A %H:%M')}。"
                "在需要格式化输出时可以使用 output_formatter 工具，但普通对话直接回复即可。"
                "当使用 web_search 工具搜索信息后，回答中必须附上信息来源的网址链接。"
                "当用户主动告诉你稳定的个人信息（例如姓名、所在城市、职业、长期偏好、沟通习惯）时，"
                "使用 save_user_info 工具长期保存。不要保存密码、密钥、身份证号、银行卡号等敏感信息。"
                "当回答需要个性化信息，或用户问你是否记得某个信息时，先使用 get_user_info 工具读取长期记忆。"
                "当用户要求忘记或删除某项个人信息时，使用 delete_user_info 工具。"
                "不要显示的告诉我要查看你的信息或者我可以帮你存储你的信息，而是直接在对话中使用工具来存储和读取信息，来让对话更自然流畅。只需要回答用户的问题就行"
            ),
            checkpointer=MemorySaver(
                serde=JsonPlusSerializer(allowed_msgpack_modules=None)
            ),
            store=store,
        )

        config = {"configurable": {"thread_id": f"chat-{USER_ID}", "user_id": USER_ID}}

        while True:
            user_input = input("你: ").strip()
            if not user_input:
                continue
            if user_input.lower() == "quit":
                print("再见！")
                break
            try:
                print("AI: ", end="", flush=True)
                for chunk in agent.stream(
                    {"messages": [{"role": "user", "content": user_input}]},
                    config=config,
                    stream_mode="messages",
                ):
                    msg, metadata = chunk
                    if msg.content and metadata.get("langgraph_node") == "model":
                        print(msg.content, end="", flush=True)
                print()  # 换行
            except Exception as e:
                print(f"出错了: {e}\n")


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


if __name__ == "__main__":
    main()
