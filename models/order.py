from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from models.base import ModelMixin

STATUS_LABELS = {
    "pendente": "Pendente",
    "confirmado": "Confirmado",
    "enviado": "Enviado",
    "concluido": "Concluído",
    "cancelado": "Cancelado",
}

STATUS_TRANSITIONS = {
    "pendente": ["confirmado", "cancelado"],
    "confirmado": ["enviado", "cancelado"],
    "enviado": ["concluido"],
    "concluido": [],
    "cancelado": [],
}

OPEN_STATUSES = ("pendente", "confirmado", "enviado")


@dataclass
class OrderItem(ModelMixin):
    produto_id: int = 0
    quantidade: int = 0
    produto_codigo: str = ""
    produto_nome: str = ""
    custo_unitario: Decimal = Decimal("0")
    moeda_custo: str = ""
    multiplicador: Decimal = Decimal("2")
    taxa_cambio: Decimal = Decimal("1")
    data_cotacao: Optional[date] = None
    preco_unitario: Decimal = Decimal("0")
    subtotal: Decimal = Decimal("0")
    pedido_id: Optional[int] = None
    id: Optional[int] = None


@dataclass
class Order(ModelMixin):
    cliente_id: int = 0
    moeda: str = "USD"
    status: str = "pendente"
    total: Decimal = Decimal("0")
    observacoes: str = ""
    numero: Optional[str] = None
    data_pedido: Optional[datetime] = None
    criado_por: Optional[int] = None
    id: Optional[int] = None
    criado_em: Optional[datetime] = field(default=None, compare=False)
    atualizado_em: Optional[datetime] = field(default=None, compare=False)
    itens: List[OrderItem] = field(default_factory=list, compare=False)

    def to_record(self, exclude=("criado_em", "atualizado_em", "itens")):
        return super().to_record(exclude)

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status)

    @property
    def next_statuses(self):
        return STATUS_TRANSITIONS.get(self.status, [])

    def can_transition_to(self, new_status):
        return new_status in self.next_statuses

    @property
    def can_be_deleted(self):
        return self.status in ("pendente", "cancelado")
