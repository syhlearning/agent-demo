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
from llama_index.core.vector_stores import ExactMatchFilter, MetadataFilters
from llama_index.vector_stores.postgres import PGVectorStore
from db import embeddings as _emb

load_dotenv()
# 新表
_TABLE_NAME = "llama_vector_docs"
_vector_store_instance = None


class DashScopeEmbedding(BaseEmbedding):
    # 如果用 OpenAI 内置模型（比如 text-embedding-3-small），可以省掉：
    # 1. db/embeddings.py — 整个文件不需要了                                                                                                                                                                                                                       
    # 2. db/llama_store.py 里的 DashScopeEmbedding 类 — 整个类删掉                                                                                                                                                                                                 
    # 3. db/vector_store.py 里的 DashScopeEmbeddings 类 — 整个类删掉（如果旧版也要换）                                                                                                                                                                                                                                                                                                                                                                                                                                       
    # 4. .env 里的 DashScope 嵌入相关配置 换成 OpenAI 的：                                                                                                                                                                                                         
    # 删掉这些                                                                                                                                                                                                                                                   
    # DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4                                                                                                                                                                                                                  
    # DASHSCOPE_EMBEDDING_DIMENSIONS=1024    
    # DASHSCOPE_EMBEDDING_BASE_URL=...
    # 换成
    # OPENAI_API_KEY=sk-xxx

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
    # 设置全局嵌入模型、切块方式，禁用 LLM（向量存储不需要 LLM）
    Settings.embed_model = DashScopeEmbedding()
    Settings.node_parser = SentenceSplitter(chunk_size=512, chunk_overlap=50)
    Settings.llm = None


def _get_vector_store() -> PGVectorStore:
    global _vector_store_instance
    # 单例模式：只创建一次数据库连接，避免重复连接消耗资源
    if _vector_store_instance is None:
        _configure()
        # PGVectorStore 不支持直接传连接字符串，用 urlparse 拆开各个参数
        url = urlparse(os.environ["DATABASE_URL"])
        _vector_store_instance = PGVectorStore.from_params(
            host=url.hostname,
            port=url.port or 5432,
            database=url.path.lstrip("/"),  # "/agent_memory" → "agent_memory"
            user=url.username,
            password=url.password,
            table_name=_TABLE_NAME,
            embed_dim=int(os.environ["DASHSCOPE_EMBEDDING_DIMENSIONS"]),  # 向量维度必须和嵌入模型一致
            perform_setup=True,  # 自动建表，表已存在则跳过
        )
    return _vector_store_instance


def _get_index() -> VectorStoreIndex:
    vs = _get_vector_store()
    # 指定向量数据存到 pgvector，其他存储（文档、索引元数据）用默认内存
    storage_context = StorageContext.from_defaults(vector_store=vs)
    # from_vector_store：挂载已有数据，用于检索（区别于空索引插入数据）
    return VectorStoreIndex.from_vector_store(vs, storage_context=storage_context)


def upsert(id: str, text: str, metadata: dict | None = None) -> None:
    """存储单条文本（自动嵌入）。"""
    _configure()
    vs = _get_vector_store()
    storage_context = StorageContext.from_defaults(vector_store=vs)
    # 空索引，只用来插入新数据
    index = VectorStoreIndex([], storage_context=storage_context)
    doc_meta = {"doc_id": id, **(metadata or {})}
    index.insert(LlamaDocument(text=text, id_=id, metadata=doc_meta))


def upsert_document(doc_id: str, text: str, metadata: dict | None = None) -> int:
    """把长文本自动分块后存入向量数据库，返回实际块数。"""
    _configure()
    doc_meta = {"doc_id": doc_id, **(metadata or {})}
    doc = LlamaDocument(text=text, id_=doc_id, metadata=doc_meta)
    # 提前用 splitter 跑一遍估算块数，用于返回值；实际切块由 index.insert 内部完成
    nodes = SentenceSplitter(chunk_size=512, chunk_overlap=50).get_nodes_from_documents([doc])
    vs = _get_vector_store()
    storage_context = StorageContext.from_defaults(vector_store=vs)
    index = VectorStoreIndex([], storage_context=storage_context)
    index.insert(doc)  # LlamaIndex 自动切块 + 嵌入 + 存入 pgvector
    return len(nodes)


def _rerank(query: str, docs: list[dict], top_n: int) -> list[dict]:
    """调用 DashScope qwen3-rerank 对检索结果重排序（精排）。
    粗排（向量检索）靠 embedding 余弦相似度，速度快但精度一般；
    精排（reranker）用 cross-encoder 把 query 和每条结果一起编码打分，精度更高但更慢。
    两者组合：先粗排召回候选，再精排筛选最终结果。
    """
    import requests as _req

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        # 没有 API key 就跳过 rerank，退化成普通向量检索
        return docs[:top_n]

    try:
        resp = _req.post(
            "https://dashscope.aliyuncs.com/compatible-api/v1/reranks",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "qwen3-rerank",
                "query": query,
                "documents": [d["text"] for d in docs],
                "top_n": top_n,
            },
            timeout=15,
        )
        data = resp.json()
        # 返回格式：{"results": [{"index": 2, "relevance_score": 0.95}, ...]}
        ranked = []
        for item in data.get("results", []):
            idx = item["index"]
            doc = docs[idx].copy()
            doc["score"] = item["relevance_score"]  # 用 reranker 分数替换原始向量相似度分数
            ranked.append(doc)
        return ranked
    except Exception:
        # rerank 失败不影响主流程，退化成原始排序
        return docs[:top_n]


def search(query: str, top_k: int = 5, metadata: dict | None = None) -> list[dict]:
    """语义检索 + Reranking。
    流程：向量粗排 top_k*4 → qwen3-rerank 精排 → 返回 top_k 条。
    """
    _configure()
    index = _get_index()  # 挂载已有数据的索引
    # 粗排：多取一些候选（top_k 的 4 倍），给 reranker 更多选择空间
    coarse_top = top_k * 4
    filters = None
    if metadata:
        filters = MetadataFilters(
            filters=[
                ExactMatchFilter(key=key, value=value)
                for key, value in metadata.items()
            ]
        )
    retriever = index.as_retriever(similarity_top_k=coarse_top, filters=filters)
    nodes = retriever.retrieve(query)

    coarse_results = [
        {
            "id": node.node_id,
            "text": node.text,
            "metadata": node.metadata,
            "score": float(node.score) if node.score is not None else 0.0,
        }
        for node in nodes
    ]

    if not coarse_results:
        return []

    # 精排：用 reranker 重新打分，筛选出最相关的 top_k 条
    return _rerank(query, coarse_results, top_n=top_k)
