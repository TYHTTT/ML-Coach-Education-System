from __future__ import annotations

import logging
import re
from collections.abc import Iterable


def _redact(value: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        if secret:
            value = value.replace(secret, "***")
    return re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+\-/=]+", r"\1***", value)


class RedactingFormatter(logging.Formatter):
    """Redact the final formatted record, including exception tracebacks."""

    def __init__(self, fmt: str, secrets: Iterable[str] = ()) -> None:
        super().__init__(fmt)
        self.secrets = tuple(secret for secret in secrets if secret)

    def format(self, record: logging.LogRecord) -> str:
        return _redact(super().format(record), self.secrets)


def configure_logging(level: str, secrets: Iterable[str] = ()) -> None:
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(
        RedactingFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            secrets,
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(numeric_level)
