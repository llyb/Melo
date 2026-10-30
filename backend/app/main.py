import asyncio
import hmac
import logging
import time
from datetime import UTC, datetime
from uuid import uuid4

import openai
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from langgraph.errors import GraphRecursionError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from app.agent import AgentRunner, InvalidOutputError
from app.schemas import ChatRequest
from app.settings import Settings

logger = logging.getLogger("melo")


class ChatError(Exception):
    def __init__(self, status: int, code: str, message: str, retryable: bool = False):
        self.status, self.code, self.message, self.retryable = status, code, message, retryable


def create_app(settings: Settings | None = None, runner=None) -> FastAPI:
    settings = settings or Settings.from_env()
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.chat_timeout = 60
    app.state.busy = False
    app.state.runner = runner

    def error_response(request: Request, error: ChatError):
        request.state.error_code = error.code
        headers = {"X-Request-ID": request.state.request_id}
        if error.status == 429:
            headers["Retry-After"] = "5"
        return JSONResponse(status_code=error.status, headers=headers, content={
            "request_id": request.state.request_id,
            "error": {"code": error.code, "message": error.message, "retryable": error.retryable},
        })

    @app.middleware("http")
    async def boundary(request: Request, call_next):
        request.state.request_id = str(uuid4())
        start = time.monotonic()
        try:
            expected = f"Bearer {settings.local_token}"
            if not settings.local_token or not hmac.compare_digest(
                request.headers.get("authorization", "").encode(), expected.encode()
            ):
                raise ChatError(401, "UNAUTHORIZED", "本地服务认证失败，请检查本机配置。")
            size, chunks = 0, []
            async for chunk in request.stream():
                size += len(chunk)
                if size > 1024 * 1024:
                    raise ChatError(413, "REQUEST_TOO_LARGE", "请求过大，请新建会话。")
                chunks.append(chunk)
            request._body = b"".join(chunks)
            response = await call_next(request)
        except ChatError as error:
            response = error_response(request, error)
        except Exception:  # noqa: BLE001 -- last boundary prevents internal details reaching clients
            response = error_response(request, ChatError(500, "INTERNAL_ERROR", "服务内部错误。"))
        response.headers["X-Request-ID"] = request.state.request_id
        logger.info("timestamp=%s request_id=%s route=%s status=%s duration_ms=%.1f error_code=%s",
                    datetime.now(UTC).isoformat(), request.state.request_id,
                    request.scope.get("route").path if request.scope.get("route") else "unknown",
                    response.status_code, (time.monotonic() - start) * 1000,
                    getattr(request.state, "error_code", ""))
        return response

    @app.exception_handler(ChatError)
    async def chat_error(request, error):
        return error_response(request, error)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, _error):
        return error_response(request, ChatError(422, "INVALID_REQUEST", "消息格式或长度不符合要求。"))

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return error_response(request, ChatError(error.status_code, "INVALID_REQUEST", "请求无效。"))

    @app.get("/api/v1/health")
    async def health():
        return {"status": "ok", "model_configured": settings.model_configured}

    @app.post("/api/v1/chat")
    async def chat(payload: ChatRequest, request: Request):
        if app.state.busy:
            raise ChatError(429, "RATE_LIMITED", "服务繁忙，请稍后重试。", True)
        if app.state.runner is None and not settings.model_configured:
            raise ChatError(503, "MODEL_NOT_CONFIGURED", "请在后端配置模型 API Key。")
        app.state.busy = True
        try:
            if app.state.runner is None:
                app.state.runner = AgentRunner(settings)
            async with asyncio.timeout(app.state.chat_timeout):
                text = await app.state.runner.reply(payload.messages)
            if not isinstance(text, str) or not text.strip() or len(text) > 16000:
                raise InvalidOutputError
            return {"request_id": request.state.request_id,
                    "message": {"role": "assistant", "content": text}}
        except (TimeoutError, openai.APITimeoutError, GraphRecursionError):
            raise ChatError(504, "MODEL_TIMEOUT", "模型响应超时，请重试。", True) from None
        except (openai.AuthenticationError, openai.PermissionDeniedError):
            raise ChatError(502, "MODEL_AUTH_ERROR", "模型认证失败，请检查后端配置。") from None
        except openai.RateLimitError:
            raise ChatError(429, "RATE_LIMITED", "模型服务限流，请稍后重试。", True) from None
        except (openai.APIError, InvalidOutputError):
            raise ChatError(502, "UPSTREAM_ERROR", "模型服务暂时不可用，请重试。", True) from None
        finally:
            app.state.busy = False

    return app
