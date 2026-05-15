"""
向量存储与检索，基于 LangChain PGVector。
"""

import os
from dotenv import load_dotenv
from langchain_community.vectorstores import PGVector
from langchain_core.embeddings import Embeddings
from langchain_core.documents import Document
import embeddings as _emb

load_dotenv()

_DB_URL = os.environ["DATABASE_URL"]
_COLLECTION = "vector_docs"


class DashScopeEmbeddings(Embeddings):
    """把项目已有的 embeddings.py 包装成 LangChain Embeddings 接口。"""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return _emb.embed_texts(texts)

    def embed_query(self, text: str) -> list[float]:
        return _emb.embed_text(text)


def _embeddings():
    return DashScopeEmbeddings()


_store_instance = None

def _store():
    global _store_instance
    if _store_instance is None:
        _store_instance = PGVector(
            connection_string=_DB_URL,
            embedding_function=_embeddings(),
            embedding_length=int(os.environ["DASHSCOPE_EMBEDDING_DIMENSIONS"]),
            collection_name=_COLLECTION,
            use_jsonb=True,
        )
    return _store_instance


def setup() -> None:
    """建表（幂等）。"""
    _store()  # PGVector 初始化时自动建表


def upsert(id: str, text: str, metadata: dict | None = None) -> None:
    """存储一条文本（已存在则覆盖）。"""
    store = _store()
    store.add_documents(
        [Document(page_content=text, metadata=metadata or {})],
        ids=[id],
    )


def upsert_document(doc_id: str, text: str, chunk_size: int = 500, overlap: int = 50, metadata: dict | None = None) -> int:
    """把长文本分块后批量存入向量数据库。"""
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["。\n", "\n\n", "\n", "。", "!", "?", ".", "!", "?", " ", ""],
    )
    chunks = splitter.split_text(text)
    store = _store()

    base_meta = dict(metadata or {})
    base_meta["doc_id"] = doc_id
    base_meta["total_chunks"] = len(chunks)

    docs = [
        Document(page_content=chunk, metadata={**base_meta, "chunk_index": i})
        for i, chunk in enumerate(chunks)
    ]
    ids = [f"{doc_id}-chunk-{i}" for i in range(len(chunks))]
    store.add_documents(docs, ids=ids)

    return len(chunks)


def search(query: str, top_k: int = 5) -> list[dict]:
    """语义检索，返回最相似的 top_k 条。"""
    store = _store()
    results = store.similarity_search_with_score(query, k=top_k)
    return [
        {
            "id": doc.id,
            "text": doc.page_content,
            "metadata": doc.metadata,
            "score": float(score),
        }
        for doc, score in results
    ]


def delete(id: str) -> None:
    """删除一条记录。"""
    _store().delete(ids=[id])
