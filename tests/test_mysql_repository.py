"""Executa o mesmo contrato no MySQL.

Requer um servidor MySQL de testes, configurado por variáveis de ambiente:
    MYSQL_TEST_HOST, MYSQL_TEST_PORT, MYSQL_TEST_USER, MYSQL_TEST_PASSWORD
    MYSQL_TEST_DATABASE (padrão: vidro_export_test — recriado a cada teste)
Sem MYSQL_TEST_HOST, os testes são ignorados (skip) e o modo JSON não é afetado.
"""
import pytest

from database.exceptions import DatabaseConnectionError
from tests.conftest import make_mysql_repo, mysql_settings
from tests.repository_contract import RepositoryContract


class TestMySQLRepositoryContract(RepositoryContract):
    @pytest.fixture
    def repo(self):
        return make_mysql_repo()


def test_connection_failure_is_explicit():
    from database import create_repository

    with pytest.raises(DatabaseConnectionError) as exc:
        create_repository({"DB_MODE": "mysql", "DB_HOST": "127.0.0.1", "DB_PORT": 1, "DB_USER": "x",
                           "DB_PASSWORD": "y", "DB_NAME": "vidro_export"})
    assert "MySQL" in str(exc.value)


def test_app_shows_error_instead_of_falling_back(tmp_path):
    from app import create_app

    app = create_app({"DB_MODE": "mysql", "DB_HOST": "127.0.0.1", "DB_PORT": 1, "JSON_DATA_DIR": tmp_path, "TESTING": True})
    response = app.test_client().get("/")
    assert response.status_code == 503
    assert "Banco de dados indisponível" in response.get_data(as_text=True)
    assert not any(tmp_path.iterdir()), "não deve criar arquivos JSON quando o modo é MySQL"


@pytest.mark.skipif(mysql_settings() is None, reason="MySQL de testes não configurado")
def test_migration_json_to_mysql(tmp_path, monkeypatch):
    from config import Config
    from database.repositories.json_repository import JsonRepository
    from services import ServiceContainer
    from services.exchange_service import ExchangeService
    from tests.conftest import fake_http_get, reset_mysql_database
    from tools import migrate_json_to_mysql
    from tools.seed_demo import seed

    settings = mysql_settings()
    reset_mysql_database(settings)
    src = JsonRepository(tmp_path)
    svc = ServiceContainer(src, ExchangeService(http_get=fake_http_get()))
    svc.settings.ensure_defaults()
    seed(svc)
    svc.orders.create(1, "BRL", [{"produto_id": 1, "quantidade": 3}])
    for key, attr in [("host", "DB_HOST"), ("port", "DB_PORT"), ("user", "DB_USER"),
                      ("password", "DB_PASSWORD"), ("database", "DB_NAME")]:
        monkeypatch.setattr(Config, attr, settings[key])
    assert migrate_json_to_mysql.main(["--json-dir", str(tmp_path)]) == 0
    from database.repositories.mysql_repository import MySQLRepository
    target = MySQLRepository(**settings)
    assert target.count("produtos") == src.count("produtos")
    assert target.get("pedidos", 1)["total"] == src.get("pedidos", 1)["total"]
    # segunda execução não duplica
    assert migrate_json_to_mysql.main(["--json-dir", str(tmp_path)]) == 3
    assert migrate_json_to_mysql.main(["--json-dir", str(tmp_path), "--skip-existing"]) == 0
    assert target.count("produtos") == src.count("produtos")
