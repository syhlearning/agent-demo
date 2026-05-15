from embeddings import embed_text
from embeddings import embed_texts


def main():
    # vector = embed_text("测试文本")
    # print(f"向量维度: {len(vector)}")
    # # 打印前 5 个值,实际存储的维度可能是 1024 或 2048
    # print(f"前 5 个值: {vector[:5]}")

    texts = ["测试文本 1", "测试文本 2", "测试文本 3"]
    vectors = embed_texts(texts)
    for text, vector in zip(texts, vectors):
        print(f"文本: {text}")
        print(f"向量维度: {len(vector)}")
        print(f"前 5 个值: {vector[:5]}\n")


if __name__ == "__main__":
    main()
