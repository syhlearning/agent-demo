"""
向量存储与检索，基于 LlamaIndex + PGVector。
自动切块、嵌入、存储，无需手动分块。
"""

import os
from dotenv import load_dotenv
from llama_index.core import Settings, VectorStoreIndex, StorageContext
from llama_index.core.schema import Document as LlamaDocument
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.postgres import PGVectorStore
from llama_index.embeddings.openai import OpenAIEmbedding

load_dotenv()
# 新表
_TABLE_NAME = "llama_vector_docs"
_vector_store_instance = None


def _configure():
    Settings.embed_model = OpenAIEmbedding(
        model=os.environ["DASHSCOPE_EMBEDDING_MODEL"],
        api_key=os.environ["DASHSCOPE_API_KEY"],
        api_base=os.environ["DASHSCOPE_EMBEDDING_BASE_URL"].rstrip("/"),
        dimensions=int(os.environ["DASHSCOPE_EMBEDDING_DIMENSIONS"]),
    )
    Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    Settings.llm = None


def _get_vector_store() -> PGVectorStore:
    global _vector_store_instance
    if _vector_store_instance is None:
        _configure()
        _vector_store_instance = PGVectorStore.from_params(
            connection_string=os.environ["DATABASE_URL"],
            table_name=_TABLE_NAME,
            embed_dim=int(os.environ["DASHSCOPE_EMBEDDING_DIMENSIONS"]),
            perform_setup=True,
        )
    return _vector_store_instance


def _get_index() -> VectorStoreIndex:
    vs = _get_vector_store()
    storage_context = StorageContext.from_defaults(vector_store=vs)
    return VectorStoreIndex.from_vector_store(vs, storage_context=storage_context)


def upsert(id: str, text: str) -> None:
    """存储单条文本（自动嵌入）。"""
    _configure()
    vs = _get_vector_store()
    storage_context = StorageContext.from_defaults(vector_store=vs)
    index = VectorStoreIndex([], storage_context=storage_context)
    index.insert(LlamaDocument(text=text, id_=id, metadata={"doc_id": id}))


def upsert_document(doc_id: str, text: str) -> int:
    """把长文本自动分块后存入向量数据库，返回实际块数。"""
    _configure()
    doc = LlamaDocument(text=text, id_=doc_id, metadata={"doc_id": doc_id})
    # 先用 splitter 估算块数
    nodes = SentenceSplitter(chunk_size=512, chunk_overlap=50).get_nodes_from_documents([doc])
    vs = _get_vector_store()
    storage_context = StorageContext.from_defaults(vector_store=vs)
    index = VectorStoreIndex([], storage_context=storage_context)
    index.insert(doc)
    return len(nodes)


def search(query: str, top_k: int = 5) -> list[dict]:
    """语义检索，返回最相似的 top_k 条。"""
    _configure()
    index = _get_index()
    nodes = index.as_retriever(similarity_top_k=top_k).retrieve(query)
    return [
        {
            "id": node.node_id,
            "text": node.text,
            "metadata": node.metadata,
            "score": float(node.score) if node.score is not None else 0.0,
        }
        for node in nodes
    ]
