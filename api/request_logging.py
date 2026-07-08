from __future__ import annotations

import time
from uuid import uuid4

import structlog
from fastapi import FastAPI, Request
from structlog.contextvars import bind_contextvars, clear_contextvars


logger = structlog.get_logger(__name__)


def install_request_logging(app: FastAPI) -> None:
    """安装请求/响应日志中间件。

    中间件会为每个 HTTP 请求生成一个 request_id，并把它绑定到 structlog 的
    contextvars。这样这个请求处理过程中输出的每条日志都会自动带上同一个 request_id。
    """

    @app.middleware("http")
    async def request_logging_middleware(request: Request, call_next):
        clear_contextvars()

        # 如果上游已经传了 request_id 就复用；没有的话在当前服务里生成一个。
        request_id = request.headers.get("x-request-id") or uuid4().hex
        bind_contextvars(request_id=request_id)

        started_at = time.perf_counter()
        path = request.url.path
        method = request.method

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logger.exception(
                "http.request.failed",
                method=method,
                path=path,
                duration_ms=duration_ms,
                client_host=request.client.host if request.client else None,
            )
            clear_contextvars()
            raise

        duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
        response.headers["x-request-id"] = request_id

        logger.info(
            "http.request.finished",
            method=method,
            path=path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_host=request.client.host if request.client else None,
        )
        clear_contextvars()
        return response
# 200 成功
# 201 创建成功
# 400 请求参数错误
# 401 未登录
# 403 无权限
# 404 不存在
# 422 参数校验失败
# 500 服务器错误
