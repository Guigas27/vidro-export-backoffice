import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash

from models.base import EMAIL_RE, ModelMixin, text

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_.-]{3,40}$")
PROFILES = {"admin": "Administrador", "operador": "Operador"}


@dataclass
class User(ModelMixin):
    nome: str = ""
    username: str = ""
    email: str = ""
    perfil: str = "operador"
    ativo: bool = True
    password_hash: Optional[str] = field(default=None, repr=False)
    id: Optional[int] = None
    criado_em: Optional[datetime] = field(default=None, compare=False)
    atualizado_em: Optional[datetime] = field(default=None, compare=False)

    @classmethod
    def from_form(cls, form, user_id=None):
        return cls(
            id=user_id,
            nome=text(form.get("nome"), 120),
            username=text(form.get("username"), 40).lower(),
            email=text(form.get("email"), 150).lower(),
            perfil=text(form.get("perfil")) or "operador",
            ativo=form.get("ativo") in ("on", "1", "true", True),
        )

    @property
    def is_admin(self):
        return self.perfil == "admin"

    @property
    def perfil_label(self):
        return PROFILES.get(self.perfil, self.perfil)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

    def validate(self):
        errors = {}
        if len(self.nome) < 2:
            errors["nome"] = "Informe o nome."
        if not USERNAME_RE.match(self.username):
            errors["username"] = "Usuário deve ter 3 a 40 caracteres (letras, números, '.', '_' ou '-')."
        if not EMAIL_RE.match(self.email):
            errors["email"] = "Informe um e-mail válido."
        if self.perfil not in PROFILES:
            errors["perfil"] = "Perfil inválido."
        return errors

    @staticmethod
    def validate_password(password, confirmation=None):
        if not password or len(password) < 8:
            return "A senha deve ter pelo menos 8 caracteres."
        if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
            return "A senha deve conter letras e números."
        if confirmation is not None and password != confirmation:
            return "A confirmação da senha não confere."
        return None
