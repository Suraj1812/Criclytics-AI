import logging
from contextvars import ContextVar
from logging.config import dictConfig


_request_id_context: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_context.get()
        return True


def configure_logging(level: str) -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "filters": {"request_id": {"()": RequestIdFilter}},
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | request_id=%(request_id)s | %(message)s"
                }
            },
            "handlers": {
                "default": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "filters": ["request_id"],
                }
            },
            "root": {"handlers": ["default"], "level": level.upper()},
        }
    )


def set_request_id(request_id: str) -> None:
    _request_id_context.set(request_id)


def clear_request_id() -> None:
    _request_id_context.set("-")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)

