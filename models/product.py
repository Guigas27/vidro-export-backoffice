from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from models.base import ModelMixin, parse_decimal, parse_int, text


@dataclass
class Product(ModelMixin):
    codigo: str = ""
    nome: str = ""
    descricao: str = ""
    custo_unitario: Optional[Decimal] = None
    moeda: str = "USD"
    estoque: Optional[int] = 0
    ativo: bool = True
    id: Optional[int] = None
    criado_em: Optional[datetime] = field(default=None, compare=False)
    atualizado_em: Optional[datetime] = field(default=None, compare=False)

    @classmethod
    def from_form(cls, form, product_id=None):
        return cls(
            id=product_id,
            codigo=text(form.get("codigo"), 40).upper(),
            nome=text(form.get("nome"), 150),
            descricao=text(form.get("descricao"), 2000),
            custo_unitario=parse_decimal(form.get("custo_unitario")),
            moeda=text(form.get("moeda"), 3).upper(),
            estoque=parse_int(form.get("estoque")) if text(form.get("estoque")) else 0,
            ativo=form.get("ativo") in ("on", "1", "true", True),
        )

    def validate(self, currencies):
        errors = {}
        if not self.codigo:
            errors["codigo"] = "Informe o código do produto."
        elif not all(c.isalnum() or c in "-_." for c in self.codigo):
            errors["codigo"] = "Use apenas letras, números, '-', '_' ou '.'."
        if len(self.nome) < 2:
            errors["nome"] = "Informe o nome do produto (mínimo 2 caracteres)."
        if self.custo_unitario is None:
            errors["custo_unitario"] = "Informe um custo unitário válido."
        elif self.custo_unitario <= 0:
            errors["custo_unitario"] = "O custo unitário deve ser maior que zero."
        elif self.custo_unitario >= Decimal("100000000"):
            errors["custo_unitario"] = "Custo unitário muito alto."
        else:
            self.custo_unitario = self.custo_unitario.quantize(Decimal("0.0001"))
        if self.moeda not in currencies:
            errors["moeda"] = "Selecione uma moeda válida."
        if self.estoque is None or self.estoque < 0:
            errors["estoque"] = "O estoque deve ser um número inteiro maior ou igual a zero."
        return errors
