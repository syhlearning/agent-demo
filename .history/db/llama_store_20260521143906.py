"""
向量存储与检索，基于 LlamaIndex + PGVector。
自动切块、嵌入、存储，无需手动分块。
"""

import os
from urllib.parse import urlparse
from dotenv import load_dotenv
from llama_index.core import Settings, VectorStoreIndex, StorageContext
from llama_index.core.schema import Document as LlamaDocument
from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.embeddings import BaseEmbedding
from llama_index.vector_stores.postgres import PGVectorStore
from db import embeddings as _emb

load_dotenv()
# 新表
_TABLE_NAME = "llama_vector_docs"
_vector_store_instance = None


class DashScopeEmbedding(BaseEmbedding):
    # 如果用 OpenAI 内置模型（比如 text-embedding-3-small），可以省掉：1. db/embeddings.py — 整个文件不需要了                                                                                                                                                                                                                       
                                                                                                                                                                                                                                                               
#   2. db/llama_store.py 里的 DashScopeEmbedding 类 — 整个类删掉                                                                                                                                                                                                 
                                                                                                                                                                                                                                                               
#   3. db/vector_store.py 里的 DashScopeEmbeddings 类 — 整个类删掉（如果旧版也要换）                                                                                                                                                                             
                                                                                                                                                                                                                                                               
#   4. .env 里的 DashScope 嵌入相关配置 换成 OpenAI 的：                                                                                                                                                                                                         
  # 删掉这些                                                                                                                                                                                                                                                   
#   DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4                                                                                                                                                                                                                  
#   DASHSCOPE_EMBEDDING_DIMENSIONS=1024    
#   DASHSCOPE_EMBEDDING_BASE_URL=...

  # 换成
#   OPENAI_API_KEY=sk-xxx

    """复用 db/embeddings.py 的 DashScope 嵌入，绕过 LlamaIndex 的模型名校验。
    因为用的是 DashScope 的 text-embedding-v4, 不是 LlamaIndex 内置的模型。
    """

    def _get_text_embedding(self, text: str) -> list[float]:
        return _emb.embed_text(text)

    def _get_query_embedding(self, query: str) -> list[float]:
        return _emb.embed_text(query)

    async def _aget_query_embedding(self, query: str) -> list[float]:
        return _emb.embed_text(query)

    def _get_text_embeddings(self, texts: list[str]) -> list[list[float]]:
        return _emb.embed_texts(texts)


def _configure():
    Settings.embed_model = DashScopeEmbedding()
    Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    Settings.llm = None


def _get_vector_store() -> PGVectorStore:
    global _vector_store_instance
    if _vector_store_instance is None:
        _configure()
        url = urlparse(os.environ["DATABASE_URL"])
        _vector_store_instance = PGVectorStore.from_params(
            host=url.hostname,
            port=url.port or 5432,
            database=url.path.lstrip("/"),
            user=url.username,
            password=url.password,
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
