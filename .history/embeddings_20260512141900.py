import os
from functools import lru_cache
from typing import Sequence

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

BATCH_SIZE = 10


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"缺少 {name} 环境变量")
    return value


def _embedding_dimensions() -> int:
    try:
        return int(_required_env("DASHSCOPE_EMBEDDING_DIMENSIONS"))
    except ValueError as exc:
        raise ValueError("DASHSCOPE_EMBEDDING_DIMENSIONS 必须是整数") from exc


@lru_cache(maxsize=1)
def _embedding_client() -> OpenAI:
    return OpenAI(
        api_key=_required_env("DASHSCOPE_API_KEY"),
        base_url=_required_env("DASHSCOPE_EMBEDDING_BASE_URL").rstrip("/"),
    )


def _validate_text(text: str) -> str:
    normalized = text.strip()
    if not normalized:
        raise ValueError("嵌入文本不能为空")
    return normalized


def embed_text(text: str) -> list[float]:
    """把单个字符串转换成向量。"""
    return embed_texts([text])[0]


def embed_texts(texts: Sequence[str]) -> list[list[float]]:
    """批量把字符串转换成向量。

    DashScope text-embedding-v4 单次最多支持 10 条输入，所以这里会自动分批。
    """
    if isinstance(texts, str):
        raise TypeError("embed_texts 需要传入字符串列表；单个字符串请使用 embed_text")

    normalized_texts = [_validate_text(text) for text in texts]
    if not normalized_texts:
        return []

    vectors: list[list[float]] = []
    for start in range(0, len(normalized_texts), BATCH_SIZE):
        batch = normalized_texts[start : start + BATCH_SIZE]
        response = _embedding_client().embeddings.create(
            model=_required_env("DASHSCOPE_EMBEDDING_MODEL"),
            input=batch,
            dimensions=_embedding_dimensions(),
            encoding_format="float",
        )
        vectors.extend(
            item.embedding for item in sorted(response.data, key=lambda item: item.index)
        )

    return vectors


def embedding_dimensions() -> int:
    """返回当前配置的向量维度，建 pgvector 表时需要和它保持一致。"""
    return _embedding_dimensions()
