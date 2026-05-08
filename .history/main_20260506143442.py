import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage, trim_messages
from langchain_core.chat_history import InMemoryChatMessageHistory

# 加载 .env 文件
load_dotenv()

# 初始化聊天模型
chat = init_chat_model(
    model="deepseek-chat",
    model_provider="openai",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
)


def main():
    print("=== AI 聊天助手 ===")
    print("输入 'quit' 退出\n")

    # 使用 LangChain 内置的消息历史管理
    history = InMemoryChatMessageHistory()
    system_msg = SystemMessage(content="你是一个有帮助的AI助手。")

    while True:
        user_input = input("你: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("再见！")
            break

        try:
            history.add_user_message(user_input)

            # 使用 trim_messages 保留最近的消息（按 token 数量限制）
            trimmed = trim_messages(
                history.messages,
                max_tokens=4000,       # 最大保留 token 数
                # token_counter=len,     # 简单用消息数量计数，也可传入模型做精确计数
                token_length=chat.get_token_length,  # 使用模型的 token 计数方法
                strategy="last",       # 保留最近的消息
                start_on="human",      # 确保从用户消息开始
                allow_partial=False,
            )

            reply = chat.invoke([system_msg] + trimmed)
            history.add_ai_message(reply.content)
            print(f"AI: {reply.content}\n")
        except Exception as e:
            print(f"出错了: {e}\n")


if __name__ == "__main__":
    main()
