import os
from typing import Any

import psycopg
from dotenv import load_dotenv


load_dotenv()

DEFAULT_RETENTION_DAYS = 30


def _db_url() -> str:
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise RuntimeError("缺少 DATABASE_URL 环境变量")
    return db_url


def _retention_days(days: int | None = None) -> int:
    if days is not None:
        return max(1, int(days))
    value = os.getenv("CHECKPOINT_RETENTION_DAYS", str(DEFAULT_RETENTION_DAYS))
    try:
        return max(1, int(value))
    except ValueError:
        return DEFAULT_RETENTION_DAYS


def checkpoint_cleanup_stats(days: int | None = None) -> dict[str, Any]:
    """返回超过保留期的 LangGraph 对话数据量，不删除任何数据。"""
    retention_days = _retention_days(days)
    with psycopg.connect(_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                with expired_threads as (
                    select thread_id
                    from thread
                    where coalesce(state_updated_at, updated_at, created_at)
                        < now() - (%s * interval '1 day')
                      and status not in ('running', 'pending')
                )
                select
                    (select count(*) from expired_threads) as threads,
                    (select count(*) from run where thread_id in (select thread_id from expired_threads)) as runs,
                    (select count(*) from checkpoints where thread_id in (select thread_id from expired_threads)) as checkpoints,
                    (select count(*) from checkpoint_blobs where thread_id in (select thread_id from expired_threads)) as checkpoint_blobs,
                    (select count(*) from checkpoint_writes where thread_id in (select thread_id from expired_threads)) as checkpoint_writes,
                    (select count(*) from checkpoint_delete_queue where thread_id in (select thread_id from expired_threads)) as checkpoint_delete_queue,
                    (select count(*) from thread_ttl where thread_id in (select thread_id from expired_threads)) as thread_ttl
                """,
                (retention_days,),
            )
            row = cur.fetchone()

    keys = [
        "threads",
        "runs",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
        "checkpoint_delete_queue",
        "thread_ttl",
    ]
    return {
        "retention_days": retention_days,
        "dry_run": True,
        "eligible": dict(zip(keys, row or [0] * len(keys))),
        "note": "只统计将被清理的 LangGraph 对话 checkpoint；不会清理 projects、brand_data 或向量知识库。",
    }


def cleanup_old_checkpoints(days: int | None = None, dry_run: bool = False) -> dict[str, Any]:
    """清理超过保留期的 LangGraph thread/run/checkpoint 数据。

    页面项目文件 projects/、品牌资料 brand_data/、向量库 skill 不会被删除。
    """
    retention_days = _retention_days(days)
    deleted: dict[str, int] = {}

    with psycopg.connect(_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                create temporary table cleanup_threads on commit drop as
                select thread_id
                from thread
                where coalesce(state_updated_at, updated_at, created_at)
                    < now() - (%s * interval '1 day')
                  and status not in ('running', 'pending')
                """,
                (retention_days,),
            )

            cur.execute("select count(*) from cleanup_threads")
            thread_count = int(cur.fetchone()[0])

            if dry_run:
                conn.rollback()
                stats = checkpoint_cleanup_stats(retention_days)
                stats["dry_run"] = True
                return stats

            delete_statements = [
                ("checkpoint_delete_queue", "delete from checkpoint_delete_queue q using cleanup_threads t where q.thread_id = t.thread_id"),
                ("checkpoint_writes", "delete from checkpoint_writes w using cleanup_threads t where w.thread_id = t.thread_id"),
                ("checkpoint_blobs", "delete from checkpoint_blobs b using cleanup_threads t where b.thread_id = t.thread_id"),
                ("checkpoints", "delete from checkpoints c using cleanup_threads t where c.thread_id = t.thread_id"),
                ("run", "delete from run r using cleanup_threads t where r.thread_id = t.thread_id"),
                ("thread_ttl", "delete from thread_ttl ttl using cleanup_threads t where ttl.thread_id = t.thread_id"),
                ("thread", "delete from thread th using cleanup_threads t where th.thread_id = t.thread_id"),
            ]

            for table_name, sql in delete_statements:
                cur.execute(sql)
                deleted[table_name] = cur.rowcount if cur.rowcount is not None else 0

            conn.commit()

    return {
        "retention_days": retention_days,
        "dry_run": False,
        "eligible_threads": thread_count,
        "deleted": deleted,
        "note": "已清理过期 LangGraph 对话 checkpoint；projects、brand_data、向量知识库未删除。",
    }


def auto_cleanup_enabled() -> bool:
    value = os.getenv("AUTO_CLEAN_CHECKPOINTS", "1").strip().lower()
    return value not in {"0", "false", "no", "off"}
