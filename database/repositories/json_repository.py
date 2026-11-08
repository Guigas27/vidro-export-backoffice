"""Repositório que persiste os dados em arquivos JSON locais.

Garantias implementadas na camada de aplicação (o JSON não as oferece nativamente):

* **Gravação atômica**: cada arquivo é escrito em um temporário, sincronizado
  com o disco (fsync) e só então substitui o original (``os.replace``).
* **Transações**: as alterações ficam em memória até o ``commit``. No commit,
  o conteúdo de todos os arquivos alterados é gravado primeiro em um diário
  (``_transacao.journal``); se o processo for interrompido no meio, o diário
  é reaplicado na próxima abertura. Em caso de erro, nada é gravado.
* **Concorrência**: ``threading.RLock`` entre threads e um arquivo de trava
  (``.lock``) entre processos.
* **Backup**: antes de substituir um arquivo, a versão anterior é copiada
  para ``.bak``; arquivos corrompidos são recuperados a partir dele.
* **Integridade**: unicidade e chaves estrangeiras (RESTRICT, CASCADE e
  SET NULL) conforme ``database/schema_def.py``.
"""
import json
import os
import shutil
import tempfile
import threading
import time
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from database import schema_def
from database.exceptions import (
    DatabaseConnectionError, DuplicateError, IntegrityViolationError,
    NotFoundError, StorageCorruptedError,
)
from database.repositories.base_repository import BaseRepository, coerce, normalize_text

FORMAT_VERSION = 1
JOURNAL_NAME = "_transacao.journal"
LOCK_NAME = ".lock"

if os.name == "nt":  # pragma: no cover - exercitado apenas no Windows
    import msvcrt

    def _lock_file(handle):
        handle.seek(0)
        while True:
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                return
            except OSError:
                time.sleep(0.05)

    def _unlock_file(handle):
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock_file(handle):
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)

    def _unlock_file(handle):
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _to_json_value(value):
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _sort_key(value):
    # NULL primeiro (como no MySQL), textos sem diferenciar maiúsculas/acentos.
    if value is None:
        return (0, "")
    if isinstance(value, str):
        return (1, normalize_text(value))
    return (1, value)


def _replace_with_retry(src, dst, attempts=10):
    # No Windows, antivírus/indexadores podem manter o arquivo aberto por instantes.
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.1)


class JsonRepository(BaseRepository):
    mode = "json"

    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DatabaseConnectionError(f"Não foi possível criar a pasta de dados JSON '{self.data_dir}': {exc}") from exc
        self._lock = threading.RLock()
        self._local = threading.local()
        self._cache = {}
        with self._process_lock():
            self._recover_journal()
            for table in schema_def.TABLE_ORDER:
                self._ensure_file(table)

    # ------------------------------------------------------------------ util
    def _path(self, table):
        return self.data_dir / schema_def.FILE_NAMES[table]

    @contextmanager
    def _process_lock(self):
        with self._lock:
            handle = open(self.data_dir / LOCK_NAME, "a+b")
            try:
                if os.name == "nt":  # msvcrt precisa de ao menos 1 byte
                    handle.seek(0, os.SEEK_END)
                    if handle.tell() == 0:
                        handle.write(b"0")
                        handle.flush()
                _lock_file(handle)
                try:
                    yield
                finally:
                    _unlock_file(handle)
            finally:
                handle.close()

    @staticmethod
    def _empty_document(table):
        return {"tabela": table, "versao": FORMAT_VERSION, "proximo_id": 1, "registros": []}

    def _atomic_write_text(self, path, text):
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            _replace_with_retry(tmp, path)
        except BaseException:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise

    def _serialize(self, table, doc):
        out = {
            "tabela": table,
            "versao": FORMAT_VERSION,
            "proximo_id": doc["proximo_id"],
            "registros": [{k: _to_json_value(rec.get(k)) for k in schema_def.fields_of(table)} for rec in doc["registros"]],
        }
        return json.dumps(out, ensure_ascii=False, indent=2)

    def _validate_document(self, table, raw):
        if not isinstance(raw, dict) or not isinstance(raw.get("registros"), list):
            raise ValueError("estrutura inválida")
        fields = schema_def.fields_of(table)
        records = []
        for item in raw["registros"]:
            if not isinstance(item, dict) or "id" not in item:
                raise ValueError("registro inválido")
            rec = {name: coerce(ftype, item.get(name)) for name, ftype in fields.items()}
            records.append(rec)
        max_id = max((r["id"] for r in records), default=0)
        next_id = max(int(raw.get("proximo_id") or 1), max_id + 1)
        return {"proximo_id": next_id, "registros": records}

    def _read_file(self, table, path):
        text = path.read_text(encoding="utf-8")
        if not text.strip():
            return None
        return self._validate_document(table, json.loads(text))

    def _ensure_file(self, table):
        path = self._path(table)
        if not path.exists() or path.stat().st_size == 0 or not path.read_text(encoding="utf-8").strip():
            backup = path.with_suffix(path.suffix + ".bak")
            if backup.exists():
                try:
                    if self._read_file(table, backup) is not None:
                        shutil.copy2(backup, path)
                        return
                except (ValueError, json.JSONDecodeError):
                    pass
            self._atomic_write_text(path, self._serialize(table, self._empty_document(table)))

    def _load(self, table):
        path = self._path(table)
        self._ensure_file(table)
        stat = path.stat()
        signature = (stat.st_mtime_ns, stat.st_size)
        cached = self._cache.get(table)
        if cached and cached[0] == signature:
            return cached[1]
        try:
            doc = self._read_file(table, path) or self._empty_document(table)
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            doc = self._recover_from_backup(table, path, exc)
            stat = path.stat()
            signature = (stat.st_mtime_ns, stat.st_size)
        self._cache[table] = (signature, doc)
        return doc

    def _recover_from_backup(self, table, path, error):
        backup = path.with_suffix(path.suffix + ".bak")
        try:
            doc = self._read_file(table, backup) if backup.exists() else None
        except (ValueError, json.JSONDecodeError, TypeError):
            doc = None
        if doc is None:
            raise StorageCorruptedError(
                f"O arquivo '{path.name}' está corrompido ({error}) e não há backup válido. "
                f"Corrija o arquivo manualmente ou restaure uma cópia."
            )
        stamp = datetime.now().strftime("%Y%m%d%H%M%S")
        shutil.copy2(path, path.with_suffix(path.suffix + f".corrompido-{stamp}"))
        shutil.copy2(backup, path)
        return doc

    def _recover_journal(self):
        journal = self.data_dir / JOURNAL_NAME
        if not journal.exists():
            return
        try:
            payload = json.loads(journal.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            # Diário incompleto: o commit não chegou a começar a substituir arquivos.
            journal.unlink()
            return
        if payload.get("completo"):
            for table, text in payload["arquivos"].items():
                self._atomic_write_text(self._path(table), text)
        journal.unlink()

    def _commit(self, work, dirty):
        if not dirty:
            return
        texts = {table: self._serialize(table, work[table]) for table in dirty}
        journal = self.data_dir / JOURNAL_NAME
        self._atomic_write_text(journal, json.dumps({"completo": True, "arquivos": texts}, ensure_ascii=False))
        for table, text in texts.items():
            path = self._path(table)
            if path.exists():
                shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
            self._atomic_write_text(path, text)
            self._cache.pop(table, None)
        journal.unlink()

    # ------------------------------------------------------------ transação
    def _state(self):
        return getattr(self._local, "state", None)

    @contextmanager
    def transaction(self):
        state = self._state()
        if state is not None:
            state["depth"] += 1
            try:
                yield self
            finally:
                state["depth"] -= 1
            return
        with self._process_lock():
            self._recover_journal()
            work = {}
            for table in schema_def.TABLES:
                doc = self._load(table)
                work[table] = {"proximo_id": doc["proximo_id"], "registros": [dict(r) for r in doc["registros"]]}
            self._local.state = {"depth": 1, "work": work, "dirty": set()}
            try:
                yield self
                self._commit(work, self._local.state["dirty"])
            finally:
                self._local.state = None

    def _work(self, table):
        schema_def.check_table(table)
        state = self._state()
        if state is None:
            raise RuntimeError("operação fora de transação")
        return state["work"][table]

    def _mark(self, table):
        self._state()["dirty"].add(table)

    # --------------------------------------------------------------- leitura
    def ping(self):
        with self.transaction():
            return True

    def _match(self, table, record, filters):
        fields = schema_def.fields_of(table)
        for column, expected in (filters or {}).items():
            schema_def.check_column(table, column)
            value = record.get(column)
            if isinstance(expected, (list, tuple, set)):
                options = {coerce(fields[column], e) for e in expected}
                if value not in options:
                    return False
            else:
                expected = coerce(fields[column], expected) if expected is not None else None
                if fields[column] == "str" and value is not None and expected is not None:
                    if normalize_text(value) != normalize_text(expected):
                        return False
                elif value != expected:
                    return False
        return True

    def _search(self, table, record, search):
        term = normalize_text(search)
        return any(term in normalize_text(record.get(col)) for col in schema_def.TABLES[table]["search"])

    def get(self, table, record_id):
        with self.transaction():
            record_id = int(record_id)
            for rec in self._work(table)["registros"]:
                if rec["id"] == record_id:
                    return dict(rec)
        return None

    def find_one(self, table, **filters):
        rows = self.list(table, filters=filters, limit=1)
        return rows[0] if rows else None

    def list(self, table, filters=None, search=None, order_by="id", descending=False, limit=None):
        schema_def.check_column(table, order_by)
        with self.transaction():
            rows = [dict(r) for r in self._work(table)["registros"] if self._match(table, r, filters)]
        if search and str(search).strip():
            rows = [r for r in rows if self._search(table, r, str(search).strip())]
        rows.sort(key=lambda r: r["id"], reverse=descending)
        rows.sort(key=lambda r: _sort_key(r.get(order_by)), reverse=descending)
        if limit is not None:
            rows = rows[: int(limit)]
        return rows

    def count(self, table, filters=None):
        with self.transaction():
            return sum(1 for r in self._work(table)["registros"] if self._match(table, r, filters))

    # --------------------------------------------------------------- escrita
    def _check_unique(self, table, record):
        rows = self._work(table)["registros"]
        for column in schema_def.TABLES[table]["unique"]:
            value = record.get(column)
            if value is None:
                continue
            key = normalize_text(value)
            for other in rows:
                if other["id"] != record["id"] and other.get(column) is not None and normalize_text(other[column]) == key:
                    raise DuplicateError(table, column)

    def _check_foreign_keys(self, table, record):
        for (child, column), (parent, _rule) in schema_def.FOREIGN_KEYS.items():
            if child != table or record.get(column) is None:
                continue
            if not any(r["id"] == record[column] for r in self._work(parent)["registros"]):
                raise IntegrityViolationError(
                    f"Referência inválida: {table}.{column}={record[column]} não existe em '{parent}'."
                )

    def insert(self, table, data):
        with self.transaction():
            doc = self._work(table)
            record = self.stamp(table, self.clean(table, data), creating=True)
            if record.get("id") is None:
                record["id"] = doc["proximo_id"]
            elif any(r["id"] == record["id"] for r in doc["registros"]):
                raise DuplicateError(table, "id")
            self._check_unique(table, record)
            self._check_foreign_keys(table, record)
            doc["registros"].append(record)
            doc["proximo_id"] = max(doc["proximo_id"], record["id"] + 1)
            self._mark(table)
            return dict(record)

    def update(self, table, record_id, data):
        with self.transaction():
            record_id = int(record_id)
            changes = self.clean(table, {k: v for k, v in data.items() if k != "id"}, partial=True)
            for index, rec in enumerate(self._work(table)["registros"]):
                if rec["id"] == record_id:
                    updated = self.stamp(table, {**rec, **changes}, creating=False)
                    self._check_unique(table, updated)
                    self._check_foreign_keys(table, updated)
                    self._work(table)["registros"][index] = updated
                    self._mark(table)
                    return dict(updated)
            raise NotFoundError(f"Registro {record_id} não encontrado em '{table}'.")

    def delete(self, table, record_id):
        with self.transaction():
            record_id = int(record_id)
            if not any(r["id"] == record_id for r in self._work(table)["registros"]):
                raise NotFoundError(f"Registro {record_id} não encontrado em '{table}'.")
            self._delete_cascade(table, record_id)
            return True

    def _delete_cascade(self, table, record_id):
        for (child, column), (parent, rule) in schema_def.FOREIGN_KEYS.items():
            if parent != table:
                continue
            children = [r for r in self._work(child)["registros"] if r.get(column) == record_id]
            if not children:
                continue
            if rule == "RESTRICT":
                raise IntegrityViolationError(
                    f"Não é possível excluir: existem registros em '{child}' vinculados a este item."
                )
            if rule == "CASCADE":
                for rec in children:
                    self._delete_cascade(child, rec["id"])
            elif rule == "SET NULL":
                for rec in children:
                    rec[column] = None
                self._mark(child)
        doc = self._work(table)
        doc["registros"] = [r for r in doc["registros"] if r["id"] != record_id]
        self._mark(table)
