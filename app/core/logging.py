import logging
import os
import sys


def _configured_level() -> int:
    value = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, value, None)
    if not isinstance(level, int):
        raise ValueError(f"Unsupported LOG_LEVEL: {value}")
    return level


logger = logging.getLogger(os.getenv("APP_NAME", "CompuGit_Backend"))
logger.setLevel(_configured_level())
logger.propagate = False

if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s request=%(request_id)s %(message)s"
        )
    )
    logger.addHandler(handler)


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            from flask import g, has_request_context

            record.request_id = g.get("request_id", "-") if has_request_context() else "-"
        except RuntimeError:
            record.request_id = "-"
        return True


for handler in logger.handlers:
    handler.addFilter(RequestContextFilter())
