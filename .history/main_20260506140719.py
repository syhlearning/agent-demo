import os

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
# from openai import OpenAI

# 加载 .env 文件
load_dotenv()

# 初始化聊天模型
chat = init_chat_model(
    model="deepseek-chat",
    model_provider="openai",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
) 

# 初始化客户端
# client = OpenAI(
#     api_key=os.getenv("DEEPSEEK_API_KEY"),  # 从 .env 文件读取
#     # base_url="https://api.deepseek.com",  # 如果用 DeepSeek，取消注释这行
# )





def main():
    print("=== OpenAI 聊天助手 ===")
    print("输入 'quit' 退出\n")

    while True:
        user_input = input("你: ").strip()
        if not user_input:
            continue
        if user_input.lower() == "quit":
            print("再见！")
            break

        try:
            reply = chat(user_input)
            print(f"AI: {reply}\n")
        except Exception as e:
            print(f"出错了: {e}\n")


if __name__ == "__main__":
    main()
