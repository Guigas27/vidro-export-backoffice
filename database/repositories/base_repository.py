"""Interface comum aos repositórios JSON e MySQL."""
import unicodedata
from abc import ABC, abstractmethod
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from database import schema_def


def normalize_text(value):
    """Minúsculas e sem acentos: usado para pesquisas equivalentes nos dois modos."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def now():
    return datetime.now().replace(microsecond=0)


def coerce(field_type, value):
    """Converte um valor para o tipo Python definido no schema."""
    if value is None or (isinstance(value, str) and value == "" and field_type != "str"):
        return None
    if field_type == "int":
        return int(value)
    if field_type == "str":
        return str(value)
    if field_type == "decimal":
        try:
            return Decimal(str(value))
        except InvalidOperation as exc:
            raise ValueError(f"Valor decimal inválido: {value}") from exc
    if field_type == "bool":
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "sim", "on", "yes"}
        return bool(value)
    if field_type == "datetime":
        if isinstance(value, datetime):
            return value.replace(microsecond=0)
        return datetime.fromisoformat(str(value)).replace(microsecond=0)
    if field_type == "date":
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return date.fromisoformat(str(value)[:10])
    raise ValueError(f"Tipo desconhecido: {field_type}")


class BaseRepository(ABC):
    """Operações de persistência usadas pelas regras de negócio.

    Todas as implementações devem:
      * retornar dicionários com tipos Python (int, Decimal, datetime, ...);
      * preencher ``criado_em``/``atualizado_em`` automaticamente;
      * garantir unicidade e integridade referencial conforme ``schema_def``;
      * lançar as exceções de ``database.exceptions``.
    """

    mode = "base"

    # ----- utilitários compartilhados -------------------------------------
    @staticmethod
    def clean(table, data, partial=False):
        fields = schema_def.fields_of(table)
        out = {}
        for key, value in data.items():
            if key not in fields:
                raise ValueError(f"Campo desconhecido: {table}.{key}")
            out[key] = coerce(fields[key], value)
        if not partial:
            for key in fields:
                out.setdefault(key, None)
        return out

    @staticmethod
    def stamp(table, data, creating):
        fields = schema_def.fields_of(table)
        ts = now()
        if creating and "criado_em" in fields and not data.get("criado_em"):
            data["criado_em"] = ts
        if "atualizado_em" in fields and (creating and not data.get("atualizado_em") or not creating):
            data["atualizado_em"] = ts
        return data

    # ----- contrato -------------------------------------------------------
    @abstractmethod
    def ping(self):
        """Verifica se o armazenamento está acessível."""

    @abstractmethod
    @contextmanager
    def transaction(self):
        """Agrupa operações: ou todas são gravadas, ou nenhuma."""

    @abstractmethod
    def get(self, table, record_id):
        """Retorna o registro ou ``None``."""

    @abstractmethod
    def find_one(self, table, **filters):
        """Primeiro registro que atende aos filtros de igualdade, ou ``None``."""

    @abstractmethod
    def list(self, table, filters=None, search=None, order_by="id", descending=False, limit=None):
        """Lista registros com filtros de igualdade e pesquisa textual."""

    @abstractmethod
    def count(self, table, filters=None):
        """Quantidade de registros que atendem aos filtros."""

    @abstractmethod
    def insert(self, table, data):
        """Insere e retorna o registro completo (com ``id``)."""

    @abstractmethod
    def update(self, table, record_id, data):
        """Atualiza campos e retorna o registro completo."""

    @abstractmethod
    def delete(self, table, record_id):
        """Exclui respeitando as regras RESTRICT / CASCADE / SET NULL."""

    def close(self):
        """Libera recursos (opcional)."""
