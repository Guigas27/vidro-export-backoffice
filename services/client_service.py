from database.exceptions import IntegrityViolationError
from models.client import Client
from services.errors import BusinessRuleError, NotFound, ValidationError


class ClientService:
    def __init__(self, repo, activities):
        self.repo = repo
        self.activities = activities

    def list(self, search=None, pais=None):
        filters = {"pais": pais} if pais else None
        return [Client.from_record(r) for r in self.repo.list("clientes", filters=filters, search=search, order_by="nome")]

    def countries(self):
        return sorted({r["pais"] for r in self.repo.list("clientes") if r["pais"]}, key=str.casefold)

    def get(self, client_id):
        client = Client.from_record(self.repo.get("clientes", client_id))
        if client is None:
            raise NotFound("Cliente não encontrado.")
        return client

    def save(self, client, user_id=None):
        errors = client.validate()
        if errors:
            raise ValidationError(errors)
        with self.repo.transaction():
            if client.id:
                self.get(client.id)
                record = self.repo.update("clientes", client.id, client.to_record())
                self.activities.log(user_id, "atualizou", "clientes", record["id"], f"Cliente {record['nome']} atualizado")
            else:
                record = self.repo.insert("clientes", client.to_record())
                self.activities.log(user_id, "cadastrou", "clientes", record["id"], f"Cliente {record['nome']} cadastrado")
        return Client.from_record(record)

    def delete(self, client_id, user_id=None):
        client = self.get(client_id)
        try:
            with self.repo.transaction():
                self.repo.delete("clientes", client_id)
                self.activities.log(user_id, "excluiu", "clientes", None, f"Cliente {client.nome} excluído")
        except IntegrityViolationError:
            raise BusinessRuleError("Este cliente possui pedidos e não pode ser excluído.")
        return client
