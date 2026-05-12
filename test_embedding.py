from embeddings import embed_text


def main():
    vector = embed_text("测试文本")
    print(f"向量维度: {len(vector)}")
    # 打印前 5 个值,实际存储的维度可能是 1024 或 2048
    print(f"前 5 个值: {vector[:5]}")


if __name__ == "__main__":
    main()
