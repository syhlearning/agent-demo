from openai import OpenAI

# 初始化客户端
client = OpenAI(
    api_key="your-api-key",  # 替换为你的 API Key
    # base_url="https://api.deepseek.com",  # 如果用 DeepSeek，取消注释这行
)


def chat(user_message: str) -> str:
    """发送消息并获取回复"""
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",  # 可换成 gpt-4o / deepseek-chat
        messages=[
            {"role": "system", "content": "你是一个有用的助手。"},
            {"role": "user", "content": user_message},
        ],
        stream=False,  # 设置为 True 可启用流式响应
        temperature=0.7,
        # max_tokens=150,
    )
    return response.choices[0].message.content


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
