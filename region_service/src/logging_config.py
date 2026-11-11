import json
import logging
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Optional, Dict, Any
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response

correlation_id_ctx: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
transition_id_ctx: ContextVar[Optional[str]] = ContextVar("transition_id", default=None)
region_id_ctx: ContextVar[Optional[str]] = ContextVar("region_id", default=None)
fencing_epoch_ctx: ContextVar[Optional[int]] = ContextVar("fencing_epoch", default=None)


class StructuredJsonFormatter(logging.Formatter):
    def __init__(self, json_format: bool = False):
        super().__init__()
        self.json_format = json_format

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        corr_id = correlation_id_ctx.get() or getattr(record, "correlation_id", None)
        trans_id = transition_id_ctx.get() or getattr(record, "transition_id", None)
        reg_id = region_id_ctx.get() or getattr(record, "region_id", None)
        epoch = fencing_epoch_ctx.get() or getattr(record, "fencing_epoch", None)

        log_data: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if corr_id:
            log_data["correlation_id"] = corr_id
        if trans_id:
            log_data["transition_id"] = trans_id
        if reg_id:
            log_data["region_id"] = reg_id
        if epoch is not None:
            log_data["fencing_epoch"] = epoch

        for key, val in record.__dict__.items():
            if key not in (
                "args", "asctime", "created", "exc_info", "exc_text", "filename",
                "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                "message", "msg", "name", "pathname", "process", "processName",
                "relativeCreated", "stack_info", "thread", "threadName"
            ):
                if key not in log_data:
                    log_data[key] = val

        if self.json_format:
            return json.dumps(log_data)

        ctx_tokens = []
        if corr_id:
            ctx_tokens.append(f"req={corr_id}")
        if trans_id:
            ctx_tokens.append(f"tx={trans_id}")
        if reg_id:
            ctx_tokens.append(f"region={reg_id}")
        if epoch is not None:
            ctx_tokens.append(f"epoch={epoch}")
        ctx_str = f" [{', '.join(ctx_tokens)}]" if ctx_tokens else ""

        return f"{timestamp} [{record.levelname}]{ctx_str} {record.name}: {record.getMessage()}"


def setup_structured_logging(service_name: str, log_level: str = "INFO", json_format: bool = False):
    handler = logging.StreamHandler()
    formatter = StructuredJsonFormatter(json_format=json_format)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        corr_id = request.headers.get("X-Correlation-ID") or request.headers.get("X-Request-ID")
        if not corr_id:
            import uuid
            corr_id = f"req-{uuid.uuid4().hex[:10]}"
        correlation_id_ctx.set(corr_id)

        trans_id = request.headers.get("X-Transition-ID")
        if trans_id:
            transition_id_ctx.set(trans_id)

        epoch_hdr = request.headers.get("X-Fencing-Epoch")
        if epoch_hdr and epoch_hdr.isdigit():
            fencing_epoch_ctx.set(int(epoch_hdr))

        response = await call_next(request)
        response.headers["X-Correlation-ID"] = corr_id
        response.headers["X-Request-ID"] = corr_id
        if trans_id:
            response.headers["X-Transition-ID"] = trans_id
        return response
