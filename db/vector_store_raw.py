"""
向量存储与检索，基于 pgvector。

用法示例：
    from vector_store import setup, upsert, search

    setup()  # 首次运行建表，之后幂等
    upsert("doc-1", "今天天气很好", {"source": "user"})
    results = search("天气怎么样", top_k=3)
    for r in results:
        print(r["id"], r["text"], r["score"])
"""

import json
import os

import psycopg
from dotenv import load_dotenv
from pgvector.psycopg import register_vector
from pgvector import Vector

from embeddings import embed_text, embedding_dimensions

load_dotenv()

_DB_URL = os.environ["DATABASE_URL"]
_TABLE = "vector_docs"


def _conn():
    conn = psycopg.connect(_DB_URL)
    register_vector(conn)
    return conn


def setup() -> None:
    """建表 + 建索引（幂等）。"""
    dims = embedding_dimensions()
    with _conn() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {_TABLE} (
                id       TEXT PRIMARY KEY,
                text     TEXT NOT NULL,
                metadata JSONB,
                embedding vector({dims}) NOT NULL
            )
        """)
        conn.execute(f"""
            CREATE INDEX IF NOT EXISTS {_TABLE}_embedding_idx
            ON {_TABLE} USING hnsw (embedding vector_cosine_ops)
        """)
        conn.commit()


def upsert(id: str, text: str, metadata: dict | None = None) -> None:
    """存储一条文本（已存在则覆盖）。"""
    embedding = Vector(embed_text(text))
    meta_json = json.dumps(metadata or {}, ensure_ascii=False)
    with _conn() as conn:
        conn.execute(f"""
            INSERT INTO {_TABLE} (id, text, metadata, embedding)
            VALUES (%s, %s, %s::jsonb, %s)
            ON CONFLICT (id) DO UPDATE
                SET text = EXCLUDED.text,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding
        """, (id, text, meta_json, embedding))
        conn.commit()


def search(query: str, top_k: int = 5) -> list[dict]:
    """语义检索，返回最相似的 top_k 条。

    返回列表，每项包含：id、text、metadata、score（越小越相似，余弦距离）。
    """
    embedding = Vector(embed_text(query))
    with _conn() as conn:
        rows = conn.execute(f"""
            SELECT id, text, metadata,
                   (embedding <=> %s) AS score
            FROM {_TABLE}
            ORDER BY score
            LIMIT %s
        """, (embedding, top_k)).fetchall()
    return [
        {"id": r[0], "text": r[1], "metadata": r[2], "score": float(r[3])}
        for r in rows
    ]


def delete(id: str) -> None:
    """删除一条记录。"""
    with _conn() as conn:
        conn.execute(f"DELETE FROM {_TABLE} WHERE id = %s", (id,))
        conn.commit()


def upsert_document(doc_id: str, text: str, chunk_size: int = 500, overlap: int = 50, metadata: dict | None = None) -> int:
    """把长文本分块后批量存入向量数据库。

    Args:
        doc_id: 文档唯一标识，每块的 id 会自动命名为 {doc_id}-chunk-0、{doc_id}-chunk-1 ...
        text: 完整的长文本
        chunk_size: 每块最大字符数，默认 500
        overlap: 相邻块之间的重叠字符数，避免语义在边界处截断，默认 50
        metadata: 附加信息

    Returns:
        实际存入的块数
    """
    chunks = _split_text(text, chunk_size, overlap)
    base_meta = dict(metadata or {})
    base_meta["doc_id"] = doc_id
    base_meta["total_chunks"] = len(chunks)

    for i, chunk in enumerate(chunks):
        chunk_meta = {**base_meta, "chunk_index": i}
        upsert(f"{doc_id}-chunk-{i}", chunk, chunk_meta)

    # 删除旧版本多余的块（文档更新后块数可能变少）
    with _conn() as conn:
        conn.execute(f"""
            DELETE FROM {_TABLE}
            WHERE id LIKE %s
              AND (metadata->>'chunk_index')::int >= %s
        """, (f"{doc_id}-chunk-%", len(chunks)))
        conn.commit()

    return len(chunks)


def _split_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """按字符数滑动窗口分块，尽量在句号/换行处断开。"""
    text = text.strip()
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        if end >= len(text):
            chunks.append(text[start:])
            break

        # 尝试在句号、换行处断开，避免截断句子
        cut = end
        for sep in ("。", "\n", ".", "！", "？", "!", "?"):
            pos = text.rfind(sep, start + chunk_size // 2, end)
            if pos != -1:
                cut = pos + 1
                break

        chunks.append(text[start:cut])
        start = cut - overlap

    return chunks
