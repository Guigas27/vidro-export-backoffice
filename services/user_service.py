from database.exceptions import DuplicateError
from models.user import User
from services.errors import BusinessRuleError, NotFound, ValidationError

# Hash fixo usado para equalizar o tempo de resposta quando o usuário não existe.
_DUMMY = User()
_DUMMY.set_password("senha-inexistente-123")


class UserService:
    def __init__(self, repo, activities):
        self.repo = repo
        self.activities = activities

    def count(self):
        return self.repo.count("usuarios")

    def list(self, search=None):
        return [User.from_record(r) for r in self.repo.list("usuarios", search=search, order_by="nome")]

    def get(self, user_id):
        user = User.from_record(self.repo.get("usuarios", user_id))
        if user is None:
            raise NotFound("Usuário não encontrado.")
        return user

    def authenticate(self, username, password):
        username = (username or "").strip().lower()
        record = self.repo.find_one("usuarios", username=username) if username else None
        if record is None and "@" in username:
            record = self.repo.find_one("usuarios", email=username)
        user = User.from_record(record)
        if user is None:
            _DUMMY.check_password(password or "")
            return None
        if not user.check_password(password or "") or not user.ativo:
            return None
        return user

    def _admins(self):
        return self.repo.count("usuarios", {"perfil": "admin", "ativo": True})

    def save(self, user, password=None, confirmation=None, acting_user_id=None):
        errors = user.validate()
        if not user.id or password:
            message = User.validate_password(password, confirmation)
            if message:
                errors["password"] = message
        if errors:
            raise ValidationError(errors)
        try:
            with self.repo.transaction():
                if user.id:
                    current = self.get(user.id)
                    if current.is_admin and current.ativo and (not user.is_admin or not user.ativo) and self._admins() <= 1:
                        raise BusinessRuleError("É necessário manter pelo menos um administrador ativo.")
                    if password:
                        user.set_password(password)
                    else:
                        user.password_hash = current.password_hash
                    record = self.repo.update("usuarios", user.id, user.to_record())
                    self.activities.log(acting_user_id, "atualizou", "usuarios", record["id"], f"Usuário {record['username']} atualizado")
                else:
                    user.set_password(password)
                    record = self.repo.insert("usuarios", user.to_record())
                    self.activities.log(acting_user_id or record["id"], "cadastrou", "usuarios", record["id"], f"Usuário {record['username']} cadastrado")
        except DuplicateError as exc:
            field = exc.field if exc.field in ("username", "email") else "username"
            label = "e-mail" if field == "email" else "nome de usuário"
            raise ValidationError({field: f"Este {label} já está em uso."})
        return User.from_record(record)

    def create_first_admin(self, form):
        if self.count() > 0:
            raise BusinessRuleError("A configuração inicial já foi realizada.")
        user = User.from_form({**form, "perfil": "admin", "ativo": "on"})
        return self.save(user, form.get("password"), form.get("password_confirm"))

    def register(self, form):
        """Cadastro público: sempre cria um operador ativo, ignorando perfil/ativo enviados."""
        if self.count() == 0:
            raise BusinessRuleError("Realize primeiro a configuração inicial do administrador.")
        user = User.from_form({**form, "perfil": "operador", "ativo": "on"})
        return self.save(user, form.get("password"), form.get("password_confirm"))

    def delete(self, user_id, acting_user_id):
        user = self.get(user_id)
        if user.id == acting_user_id:
            raise BusinessRuleError("Você não pode excluir o próprio usuário.")
        with self.repo.transaction():
            if user.is_admin and user.ativo and self._admins() <= 1:
                raise BusinessRuleError("É necessário manter pelo menos um administrador ativo.")
            self.repo.delete("usuarios", user_id)
            self.activities.log(acting_user_id, "excluiu", "usuarios", None, f"Usuário {user.username} excluído")
        return user
