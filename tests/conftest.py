import json
import os
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from database.repositories.json_repository import JsonRepository  # noqa: E402

SCHEMA = ROOT / "database" / "mysql" / "schema.sql"


def fake_http_get(rates=None):
    """Simula a API Frankfurter: taxas fixas a partir do USD."""
    table = rates or {"USD": Decimal("1"), "BRL": Decimal("5.5"), "EUR": Decimal("0.9"), "GBP": Decimal("0.8")}

    def _get(url, timeout):
        base = re.search(r"base=([A-Z]{3})", url).group(1)
        symbols = re.search(r"symbols=([A-Z,%2C]+)", url).group(1).replace("%2C", ",").split(",")
        return json.dumps({"amount": 1.0, "base": base, "date": "2026-11-06",
                           "rates": {s: float(table[s] / table[base]) for s in symbols if s in table}})
    return _get


def failing_http_get(url, timeout):
    raise OSError("sem internet")


# ------------------------------------------------------------------ MySQL
def mysql_settings():
    """MySQL de testes só é usado quando MYSQL_TEST_HOST está definido."""
    host = os.getenv("MYSQL_TEST_HOST")
    if not host:
        return None
    return {
        "host": host, "port": int(os.getenv("MYSQL_TEST_PORT", "3306")),
        "user": os.getenv("MYSQL_TEST_USER", "root"), "password": os.getenv("MYSQL_TEST_PASSWORD", ""),
        "database": os.getenv("MYSQL_TEST_DATABASE", "vidro_export_test"),
    }


def reset_mysql_database(settings):
    """Recria o banco de testes isolado a partir do schema.sql."""
    import mysql.connector

    assert settings["database"].endswith("_test"), "Use um banco de testes separado (nome terminado em _test)."
    sql = SCHEMA.read_text(encoding="utf-8").replace("vidro_export", settings["database"])
    conn = mysql.connector.connect(host=settings["host"], port=settings["port"], user=settings["user"],
                                   password=settings["password"])
    cur = conn.cursor()
    cur.execute(f"DROP DATABASE IF EXISTS `{settings['database']}`")
    for statement in [s.strip() for s in re.sub(r"--[^\n]*", "", sql).split(";") if s.strip()]:
        cur.execute(statement)
    conn.commit()
    cur.close()
    conn.close()


def make_mysql_repo():
    from database.repositories.mysql_repository import MySQLRepository

    settings = mysql_settings()
    if settings is None:
        pytest.skip("MySQL de testes não configurado (defina MYSQL_TEST_HOST para executar).")
    reset_mysql_database(settings)
    return MySQLRepository(**settings)


@pytest.fixture
def json_repo(tmp_path):
    return JsonRepository(tmp_path / "data")


@pytest.fixture(params=["json", "mysql"])
def any_repo(request, tmp_path):
    if request.param == "json":
        return JsonRepository(tmp_path / "data")
    return make_mysql_repo()


@pytest.fixture
def services(any_repo):
    from services import ServiceContainer
    from services.exchange_service import ExchangeService

    container = ServiceContainer(any_repo, ExchangeService(http_get=fake_http_get()))
    container.settings.ensure_defaults()
    return container


@pytest.fixture
def app(tmp_path):
    from app import create_app

    app = create_app({"JSON_DATA_DIR": tmp_path / "app-data", "DB_MODE": "json", "TESTING": True,
                      "SECRET_KEY": "test-secret", "EXCHANGE_HTTP_GET": fake_http_get()})
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def post(client, url, data=None, **kwargs):
    data = dict(data or {})
    data["csrf_token"] = csrf_token_of(client)
    return client.post(url, data=data, **kwargs)


def csrf_token_of(client):
    with client.session_transaction() as sess:
        token = sess.get("_csrf_token")
    if token:
        return token
    client.get("/login", follow_redirects=True)
    with client.session_transaction() as sess:
        return sess["_csrf_token"]


@pytest.fixture
def admin_client(client):
    post(client, "/setup", {"nome": "Administrador", "username": "admin", "email": "admin@vidro.example",
                            "password": "senha1234", "password_confirm": "senha1234"})
    return client
