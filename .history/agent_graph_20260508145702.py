import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver
from datetime import datetime
from tools import output_formatter, get_weather
from tavily import TavilyClient


# 加载 .env 文件
load_dotenv()

# 初始化聊天模型
model = init_chat_model(
    model="deepseek-chat",
    model_provider="openai",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)

# 创建 LangGraph Agent（带记忆）
agent = create_agent(
    model=model,
    tools=[output_formatter, get_weather],  # 注册工具
    system_prompt=f"""你是一个有帮助的AI助手。当前日期和时间：{datetime.now().strftime('%Y年%m月%d日 %A %H:%M')}。在需要格式化输出时可以使用 output_formatter 工具，但普通对话直接回复即可。""",
    checkpointer=MemorySaver(),
)

# 会话配置（同一个 thread_id 共享记忆）
config = {"configurable": {"thread_id": "chat-1"}}


def main():
    print("=== AI 智能体聊天助手 (LangGraph) ===")
    print("输入 'quit' 退出\n")

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
            print()  # 最后换行
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
