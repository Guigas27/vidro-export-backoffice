"""Fábrica do repositório conforme ``DB_MODE`` (sem fallback silencioso)."""
from database.exceptions import DatabaseConnectionError


def create_repository(config):
    """``config`` é um dicionário (ex.: ``app.config``)."""
    mode = str(config.get("DB_MODE") or "json").strip().lower()
    if mode == "json":
        from database.repositories.json_repository import JsonRepository
        return JsonRepository(config.get("JSON_DATA_DIR"))
    if mode == "mysql":
        from database.repositories.mysql_repository import MySQLRepository
        return MySQLRepository(
            host=config.get("DB_HOST"), port=int(config.get("DB_PORT") or 3306),
            user=config.get("DB_USER"), password=config.get("DB_PASSWORD") or "",
            database=config.get("DB_NAME"),
        )
    raise DatabaseConnectionError(f"DB_MODE inválido: '{mode}'. Use 'json' ou 'mysql'.")
