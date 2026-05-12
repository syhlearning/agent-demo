from embeddings import embed_text


def main():
    vector = embed_text("测试文本")
    print(f"向量维度: {len(vector)}")
    print(f"前 5 个值: {vector[:5]}")


if __name__ == "__main__":
    main()
