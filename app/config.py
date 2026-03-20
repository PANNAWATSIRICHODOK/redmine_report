from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
USER_ALIASES_PATH = BASE_DIR / "UserAliases.csv"

PAGE_LIMIT = 100
REQUEST_TIMEOUT = 30
SQL_TIMEOUT = 60
CUSTOMER_FIELD_NAME = "Customer"
COMPANY_FIELD_NAME = "Company"
UNMATCHED_DEPARTMENT = "ยังไม่จับคู่แผนก"
UNKNOWN_REQUESTER = "ไม่ระบุผู้แจ้ง"

DEFAULT_SUPERSET_DIRECTORY_SQL = """
SELECT
  u.id,
  u.username,
  u.username_ad,
  u.email,
  u.code AS user_code,
  u.sap_user,
  u.firstname,
  u.lastname,
  u.firstname_th,
  u.lastname_th,
  CONCAT_WS(' ', NULLIF(u.firstname, ''), NULLIF(u.lastname, '')) AS full_name_en,
  CONCAT_WS(' ', NULLIF(u.firstname_th, ''), NULLIF(u.lastname_th, '')) AS full_name_th,
  d.name AS department_name
FROM users u
LEFT JOIN department d ON d.id = u.department_id
WHERE COALESCE(u.active, 0) = 1
ORDER BY u.id
""".strip()


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class RedmineConfig:
    base_url: str
    api_key: str
    verify_ssl: bool


@dataclass(frozen=True)
class SupersetConfig:
    base_url: str
    username: str
    password: str
    provider: str
    database_id: int
    schema: str
    verify_ssl: bool


@dataclass(frozen=True)
class ServerConfig:
    host: str
    port: int


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


load_dotenv(BASE_DIR / ".env")


def env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def env_int(name: str, default: int, minimum: int | None = None) -> int:
    raw_value = os.getenv(name)
    if raw_value is None or not raw_value.strip():
        value = default
    else:
        try:
            value = int(raw_value.strip())
        except ValueError as exc:
            raise ConfigError(f"Invalid integer value for {name}: {raw_value}") from exc

    if minimum is not None and value < minimum:
        raise ConfigError(f"{name} must be greater than or equal to {minimum}, got {value}")
    return value


def load_redmine_config() -> RedmineConfig:
    base_url = os.getenv("REDMINE_BASE_URL", "").strip().rstrip("/")
    api_key = os.getenv("REDMINE_API_KEY", "").strip()
    verify_ssl = env_flag("REDMINE_VERIFY_SSL", True)

    if not base_url or not api_key:
        raise ConfigError(
            "Missing REDMINE_BASE_URL or REDMINE_API_KEY. "
            "Create a .env file from .env.example or export both variables before starting the app."
        )

    return RedmineConfig(base_url=base_url, api_key=api_key, verify_ssl=verify_ssl)


def load_superset_config() -> SupersetConfig:
    base_url = os.getenv("SUPERSET_BASE_URL", "").strip().rstrip("/")
    username = os.getenv("SUPERSET_USERNAME", "").strip()
    password = os.getenv("SUPERSET_PASSWORD", "").strip()
    provider = os.getenv("SUPERSET_PROVIDER", "ldap").strip() or "ldap"

    if not base_url or not username or not password:
        raise ConfigError(
            "Missing SUPERSET_BASE_URL, SUPERSET_USERNAME or SUPERSET_PASSWORD. "
            "Populate them in .env before starting the app."
        )

    return SupersetConfig(
        base_url=base_url,
        username=username,
        password=password,
        provider=provider,
        database_id=env_int("SUPERSET_DATABASE_ID", 2, minimum=1),
        schema=(os.getenv("SUPERSET_SCHEMA", "bgerpshare").strip() or "bgerpshare"),
        verify_ssl=env_flag("SUPERSET_VERIFY_SSL", True),
    )


def load_server_config() -> ServerConfig:
    raw_port = os.getenv("PORT", "8000").strip()
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as exc:
        raise ConfigError(f"Invalid PORT value: {raw_port}") from exc

    if port <= 0:
        raise ConfigError(f"PORT must be greater than zero, got {raw_port}")

    host = os.getenv("HOST", "127.0.0.1").strip() or "127.0.0.1"
    return ServerConfig(host=host, port=port)
