"""Configurações da aplicação carregadas do arquivo .env."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def _bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "sim", "on"}


class Config:
    BASE_DIR = BASE_DIR
    SECRET_KEY = os.getenv("SECRET_KEY") or ""
    # Cadastro público na tela de login (novas contas entram como operador)
    ALLOW_SIGNUP = os.getenv("ALLOW_SIGNUP", "true").strip().lower() in ("1", "true", "sim", "yes", "on")
    DB_MODE = (os.getenv("DB_MODE") or "json").strip().lower()

    JSON_DATA_DIR = Path(os.getenv("JSON_DATA_DIR") or BASE_DIR / "database" / "json")

    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT") or 3306)
    DB_USER = os.getenv("DB_USER", "root")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_NAME = os.getenv("DB_NAME", "vidro_export")

    EXCHANGE_API_URL = os.getenv("EXCHANGE_API_URL", "https://api.frankfurter.dev/v1")
    EXCHANGE_TIMEOUT = float(os.getenv("EXCHANGE_TIMEOUT") or 8)
    EXCHANGE_CACHE_SECONDS = int(os.getenv("EXCHANGE_CACHE_SECONDS") or 1800)

    JWT_EXPIRATION_MINUTES = int(os.getenv("JWT_EXPIRATION_MINUTES") or 60)

    FLASK_DEBUG = _bool(os.getenv("FLASK_DEBUG"), False)
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = int(os.getenv("PORT") or 5000)

    CSRF_ENABLED = True
    TESTING = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
