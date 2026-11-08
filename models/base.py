import re
from dataclasses import asdict, fields
from decimal import Decimal, InvalidOperation

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


class ModelMixin:
    @classmethod
    def from_record(cls, record):
        if record is None:
            return None
        names = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in record.items() if k in names})

    def to_record(self, exclude=("criado_em", "atualizado_em")):
        data = asdict(self)
        for key in exclude:
            data.pop(key, None)
        if data.get("id") is None:
            data.pop("id", None)
        return data


def text(value, max_len=None):
    value = (value or "").strip() if isinstance(value, str) else ("" if value is None else str(value).strip())
    return value[:max_len] if max_len else value


def parse_decimal(value):
    if isinstance(value, Decimal):
        return value
    raw = text(value).replace(" ", "")
    if not raw:
        return None
    # aceita "1.234,56" e "1234.56"
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


def parse_int(value):
    try:
        return int(text(value))
    except (TypeError, ValueError):
        return None
