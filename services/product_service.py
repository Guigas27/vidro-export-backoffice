from database.exceptions import DuplicateError, IntegrityViolationError
from models.product import Product
from services.errors import BusinessRuleError, NotFound, ValidationError
from services.exchange_service import SUPPORTED_CURRENCIES


class ProductService:
    def __init__(self, repo, activities):
        self.repo = repo
        self.activities = activities

    def list(self, search=None, status=None):
        filters = {}
        if status == "ativos":
            filters["ativo"] = True
        elif status == "inativos":
            filters["ativo"] = False
        return [Product.from_record(r) for r in self.repo.list("produtos", filters=filters, search=search, order_by="nome")]

    def get(self, product_id):
        product = Product.from_record(self.repo.get("produtos", product_id))
        if product is None:
            raise NotFound("Produto não encontrado.")
        return product

    def save(self, product, user_id=None):
        errors = product.validate(SUPPORTED_CURRENCIES)
        if errors:
            raise ValidationError(errors)
        try:
            with self.repo.transaction():
                if product.id:
                    self.get(product.id)
                    record = self.repo.update("produtos", product.id, product.to_record())
                    self.activities.log(user_id, "atualizou", "produtos", record["id"], f"Produto {record['codigo']} atualizado")
                else:
                    record = self.repo.insert("produtos", product.to_record())
                    self.activities.log(user_id, "cadastrou", "produtos", record["id"], f"Produto {record['codigo']} cadastrado")
        except DuplicateError:
            raise ValidationError({"codigo": "Já existe um produto com este código."})
        return Product.from_record(record)

    def delete(self, product_id, user_id=None):
        product = self.get(product_id)
        try:
            with self.repo.transaction():
                self.repo.delete("produtos", product_id)
                self.activities.log(user_id, "excluiu", "produtos", None, f"Produto {product.codigo} excluído")
        except IntegrityViolationError:
            raise BusinessRuleError(
                "Este produto está presente em pedidos e não pode ser excluído. Desative-o para impedir novos pedidos."
            )
        return product
