import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.agents import create_agent
from langgraph.checkpoint.memory import MemorySaver

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
    tools=[],  # 后续可以在这里添加工具
    prompt="你是一个有帮助的AI助手。",
    checkpointer=MemorySaver(),  # 内置记忆管理
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
                # chunk 是 (message, metadata) 元组
                msg, metadata = chunk
                if msg.content and metadata.get("langgraph_node") == "agent":
                    print(msg.content, end="", flush=True)
            print("\n")  # 换行
        except Exception as e:
            print(f"出错了: {e}\n")


if __name__ == "__main__":
    main()
