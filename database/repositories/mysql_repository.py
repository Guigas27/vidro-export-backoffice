"""Repositório MySQL com a mesma interface do repositório JSON."""
import threading
from contextlib import contextmanager

from database import schema_def
from database.exceptions import (
    DatabaseConnectionError, DuplicateError, IntegrityViolationError, NotFoundError,
)
from database.repositories.base_repository import BaseRepository, coerce

try:
    import mysql.connector
    from mysql.connector import errorcode, pooling
except ImportError:  # pragma: no cover
    mysql = None

ER_DUP_ENTRY = 1062
ER_ROW_IS_REFERENCED = (1451, 1217)
ER_NO_REFERENCED_ROW = (1452, 1216)


def _q(identifier):
    return f"`{identifier}`"


class MySQLRepository(BaseRepository):
    mode = "mysql"

    def __init__(self, host, port, user, password, database, pool_size=5):
        if mysql is None:
            raise DatabaseConnectionError("O pacote 'mysql-connector-python' não está instalado.")
        self.database = database
        self._local = threading.local()
        try:
            self._pool = pooling.MySQLConnectionPool(
                pool_name=f"vidro_export_{id(self)}", pool_size=pool_size,
                host=host, port=port, user=user, password=password, database=database,
                charset="utf8mb4", collation="utf8mb4_unicode_ci", autocommit=False,
                connection_timeout=8,
            )
        except mysql.connector.Error as exc:
            hint = ""
            if exc.errno == errorcode.ER_BAD_DB_ERROR:
                hint = " Execute o script database/mysql/schema.sql para criar o banco."
            elif exc.errno == errorcode.ER_ACCESS_DENIED_ERROR:
                hint = " Verifique DB_USER e DB_PASSWORD no arquivo .env."
            raise DatabaseConnectionError(
                f"Não foi possível conectar ao MySQL em {host}:{port} (banco '{database}'): {exc.msg}.{hint}"
            ) from exc
        self.ping()

    # ------------------------------------------------------------ conexão
    @contextmanager
    def transaction(self):
        state = getattr(self._local, "state", None)
        if state is not None:
            state["depth"] += 1
            try:
                yield self
            finally:
                state["depth"] -= 1
            return
        try:
            conn = self._pool.get_connection()
        except mysql.connector.Error as exc:
            raise DatabaseConnectionError(f"Falha na conexão com o MySQL: {exc}") from exc
        self._local.state = {"depth": 1, "conn": conn}
        try:
            conn.start_transaction()
            yield self
            conn.commit()
        except BaseException:
            try:
                conn.rollback()
            except mysql.connector.Error:
                pass
            raise
        finally:
            self._local.state = None
            conn.close()

    def _execute(self, sql, params=(), fetch=None):
        with self.transaction():
            conn = self._local.state["conn"]
            cursor = conn.cursor(dictionary=True)
            try:
                cursor.execute(sql, params)
                if fetch == "all":
                    return cursor.fetchall()
                if fetch == "one":
                    return cursor.fetchone()
                return cursor.lastrowid
            except mysql.connector.IntegrityError as exc:
                raise self._map_integrity(exc) from exc
            finally:
                cursor.close()

    @staticmethod
    def _map_integrity(exc):
        if exc.errno == ER_DUP_ENTRY:
            # Ex.: Duplicate entry 'X' for key 'produtos.uk_produtos__codigo'
            key = str(exc.msg).rsplit("'", 2)[-2] if "'" in str(exc.msg) else ""
            table, _, index = key.rpartition(".")
            field = "id" if index == "PRIMARY" else index.split("__")[-1]
            return DuplicateError(table or "?", field or "?")
        if exc.errno in ER_ROW_IS_REFERENCED:
            return IntegrityViolationError("Não é possível excluir: existem registros vinculados a este item.")
        if exc.errno in ER_NO_REFERENCED_ROW:
            return IntegrityViolationError("Referência inválida: o registro relacionado não existe.")
        return IntegrityViolationError(str(exc))

    def ping(self):
        self._execute("SELECT 1 AS ok", fetch="one")
        return True

    # ------------------------------------------------------------ conversão
    @staticmethod
    def _to_python(table, row):
        if row is None:
            return None
        fields = schema_def.fields_of(table)
        return {name: coerce(ftype, row.get(name)) for name, ftype in fields.items()}

    @staticmethod
    def _to_db(value):
        return value

    def _where(self, table, filters, search):
        clauses, params = [], []
        for column, expected in (filters or {}).items():
            schema_def.check_column(table, column)
            if isinstance(expected, (list, tuple, set)):
                values = list(expected)
                if not values:
                    clauses.append("1=0")
                    continue
                clauses.append(f"{_q(column)} IN ({', '.join(['%s'] * len(values))})")
                params.extend(values)
            elif expected is None:
                clauses.append(f"{_q(column)} IS NULL")
            else:
                clauses.append(f"{_q(column)} = %s")
                params.append(expected)
        if search and str(search).strip():
            term = f"%{str(search).strip()}%"
            cols = schema_def.TABLES[table]["search"]
            clauses.append("(" + " OR ".join(f"{_q(c)} LIKE %s" for c in cols) + ")")
            params.extend([term] * len(cols))
        return (" WHERE " + " AND ".join(clauses)) if clauses else "", params

    # ------------------------------------------------------------- leitura
    def get(self, table, record_id):
        schema_def.check_table(table)
        row = self._execute(f"SELECT * FROM {_q(table)} WHERE id = %s", (int(record_id),), fetch="one")
        return self._to_python(table, row)

    def find_one(self, table, **filters):
        rows = self.list(table, filters=filters, limit=1)
        return rows[0] if rows else None

    def list(self, table, filters=None, search=None, order_by="id", descending=False, limit=None):
        schema_def.check_column(table, order_by)
        where, params = self._where(table, filters, search)
        direction = "DESC" if descending else "ASC"
        sql = f"SELECT * FROM {_q(table)}{where} ORDER BY {_q(order_by)} {direction}, id {direction}"
        if limit is not None:
            sql += " LIMIT %s"
            params.append(int(limit))
        return [self._to_python(table, r) for r in self._execute(sql, params, fetch="all")]

    def count(self, table, filters=None):
        schema_def.check_table(table)
        where, params = self._where(table, filters, None)
        row = self._execute(f"SELECT COUNT(*) AS total FROM {_q(table)}{where}", params, fetch="one")
        return int(row["total"])

    # ------------------------------------------------------------- escrita
    def insert(self, table, data):
        record = self.stamp(table, self.clean(table, data, partial=True), creating=True)
        if record.get("id") is None:
            record.pop("id", None)
        columns = list(record)
        sql = (f"INSERT INTO {_q(table)} ({', '.join(_q(c) for c in columns)}) "
               f"VALUES ({', '.join(['%s'] * len(columns))})")
        with self.transaction():
            new_id = self._execute(sql, [record[c] for c in columns])
            return self.get(table, record.get("id") or new_id)

    def update(self, table, record_id, data):
        changes = self.clean(table, {k: v for k, v in data.items() if k != "id"}, partial=True)
        changes = self.stamp(table, changes, creating=False)
        with self.transaction():
            if self.get(table, record_id) is None:
                raise NotFoundError(f"Registro {record_id} não encontrado em '{table}'.")
            if changes:
                sets = ", ".join(f"{_q(c)} = %s" for c in changes)
                self._execute(f"UPDATE {_q(table)} SET {sets} WHERE id = %s", [*changes.values(), int(record_id)])
            return self.get(table, record_id)

    def delete(self, table, record_id):
        with self.transaction():
            if self.get(table, record_id) is None:
                raise NotFoundError(f"Registro {record_id} não encontrado em '{table}'.")
            self._execute(f"DELETE FROM {_q(table)} WHERE id = %s", (int(record_id),))
            return True

    def close(self):
        pass
