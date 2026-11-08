from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from models.base import EMAIL_RE, ModelMixin, text


@dataclass
class Client(ModelMixin):
    nome: str = ""
    pais: str = ""
    cidade: str = ""
    email: str = ""
    telefone: str = ""
    endereco: str = ""
    identificacao_fiscal: str = ""
    id: Optional[int] = None
    criado_em: Optional[datetime] = field(default=None, compare=False)
    atualizado_em: Optional[datetime] = field(default=None, compare=False)

    @classmethod
    def from_form(cls, form, client_id=None):
        return cls(
            id=client_id,
            nome=text(form.get("nome"), 150),
            pais=text(form.get("pais"), 80),
            cidade=text(form.get("cidade"), 80),
            email=text(form.get("email"), 150).lower(),
            telefone=text(form.get("telefone"), 40),
            endereco=text(form.get("endereco"), 255),
            identificacao_fiscal=text(form.get("identificacao_fiscal"), 60),
        )

    def validate(self):
        errors = {}
        if len(self.nome) < 2:
            errors["nome"] = "Informe o nome ou razão social."
        if len(self.pais) < 2:
            errors["pais"] = "Informe o país."
        if len(self.cidade) < 2:
            errors["cidade"] = "Informe a cidade."
        if self.email and not EMAIL_RE.match(self.email):
            errors["email"] = "Informe um e-mail válido."
        if self.telefone and not all(c.isdigit() or c in "+-() ." for c in self.telefone):
            errors["telefone"] = "Telefone contém caracteres inválidos."
        return errors
