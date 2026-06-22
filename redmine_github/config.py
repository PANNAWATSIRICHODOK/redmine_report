from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
REQUEST_TIMEOUT = 30


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class RedmineConfig:
    base_url: str
    api_key: str
    verify_ssl: bool


def load_dotenv(path: Path = BASE_DIR / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def env_int(name: str, default: int = 0) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc


def env_float(name: str, default: float | None = None) -> float | None:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        return float(raw_value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number") from exc


def env_str(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def load_redmine_config() -> RedmineConfig:
    load_dotenv()
    base_url = os.getenv("REDMINE_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("REDMINE_API_KEY", "").strip()
    if not base_url or not api_key:
        raise ConfigError("Missing REDMINE_BASE_URL or REDMINE_API_KEY")
    return RedmineConfig(
        base_url=base_url,
        api_key=api_key,
        verify_ssl=env_flag("REDMINE_VERIFY_SSL", True),
    )
