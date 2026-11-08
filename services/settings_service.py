from decimal import Decimal, InvalidOperation

from database.schema_def import DEFAULT_SETTINGS
from services.errors import ValidationError
from services.exchange_service import SUPPORTED_CURRENCIES


class SettingsService:
    def __init__(self, repo):
        self.repo = repo

    def ensure_defaults(self):
        with self.repo.transaction():
            for key, value in DEFAULT_SETTINGS.items():
                if self.repo.find_one("configuracoes", chave=key) is None:
                    self.repo.insert("configuracoes", {"chave": key, "valor": value})

    def get(self, key, default=None):
        row = self.repo.find_one("configuracoes", chave=key)
        if row is None:
            return DEFAULT_SETTINGS.get(key, default)
        return row["valor"]

    def all(self):
        values = dict(DEFAULT_SETTINGS)
        values.update({r["chave"]: r["valor"] for r in self.repo.list("configuracoes")})
        return values

    @property
    def price_multiplier(self):
        try:
            return Decimal(self.get("multiplicador_preco", "2"))
        except InvalidOperation:
            return Decimal("2")

    @property
    def default_currency(self):
        return self.get("moeda_padrao", "USD")

    def update(self, form, activities=None, user_id=None):
        errors = {}
        raw = (form.get("multiplicador_preco") or "").replace(",", ".").strip()
        try:
            multiplier = Decimal(raw)
            if multiplier <= 0 or multiplier > 100:
                raise InvalidOperation
        except InvalidOperation:
            errors["multiplicador_preco"] = "Informe um multiplicador entre 0 e 100 (ex.: 2 = 100% sobre o custo)."
        currency = (form.get("moeda_padrao") or "").upper().strip()
        if currency not in SUPPORTED_CURRENCIES:
            errors["moeda_padrao"] = "Selecione uma moeda válida."
        company = (form.get("empresa_nome") or "").strip()[:120]
        if len(company) < 2:
            errors["empresa_nome"] = "Informe o nome da empresa."
        if errors:
            raise ValidationError(errors)
        values = {"multiplicador_preco": format(multiplier.normalize(), "f"), "moeda_padrao": currency, "empresa_nome": company}
        with self.repo.transaction():
            for key, value in values.items():
                row = self.repo.find_one("configuracoes", chave=key)
                if row:
                    self.repo.update("configuracoes", row["id"], {"valor": value})
                else:
                    self.repo.insert("configuracoes", {"chave": key, "valor": value})
            if activities:
                activities.log(user_id, "atualizou", "configuracoes", None, "Configurações comerciais atualizadas")
        return values
