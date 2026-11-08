from datetime import datetime

from models.order import OPEN_STATUSES, STATUS_LABELS, Order, OrderItem
from models.base import parse_int, text
from services.errors import BusinessRuleError, NotFound, ValidationError
from services.exchange_service import SUPPORTED_CURRENCIES, ExchangeUnavailableError
from services.price_calculator import PriceCalculator


class OrderService:
    def __init__(self, repo, exchange, settings, activities):
        self.repo = repo
        self.exchange = exchange
        self.settings = settings
        self.activities = activities

    # ------------------------------------------------------------ consulta
    def _attach(self, orders):
        clients = {c["id"]: c for c in self.repo.list("clientes")}
        for order in orders:
            client = clients.get(order.cliente_id)
            order.cliente_nome = client["nome"] if client else "—"
            order.cliente_pais = client["pais"] if client else ""
        return orders

    def list(self, search=None, status=None, cliente_id=None, moeda=None):
        filters = {}
        if status:
            filters["status"] = status
        if cliente_id:
            filters["cliente_id"] = int(cliente_id)
        if moeda:
            filters["moeda"] = moeda
        rows = self.repo.list("pedidos", filters=filters, order_by="data_pedido", descending=True)
        orders = self._attach([Order.from_record(r) for r in rows])
        if search and search.strip():
            from database.repositories.base_repository import normalize_text
            term = normalize_text(search.strip())
            orders = [o for o in orders if term in normalize_text(o.numero) or term in normalize_text(o.cliente_nome)
                      or term in normalize_text(o.observacoes)]
        return orders

    def get(self, order_id):
        order = Order.from_record(self.repo.get("pedidos", order_id))
        if order is None:
            raise NotFound("Pedido não encontrado.")
        order.itens = [OrderItem.from_record(r) for r in self.repo.list("itens_pedido", filters={"pedido_id": order.id})]
        self._attach([order])
        client = self.repo.get("clientes", order.cliente_id)
        order.cliente = client
        creator = self.repo.get("usuarios", order.criado_por) if order.criado_por else None
        order.criado_por_nome = creator["nome"] if creator else "—"
        return order

    # --------------------------------------------------------------- preço
    def _parse_items(self, raw_items):
        merged, errors = {}, []
        for index, raw in enumerate(raw_items or []):
            produto_id = parse_int(raw.get("produto_id"))
            quantidade = parse_int(raw.get("quantidade"))
            if produto_id is None and not text(raw.get("quantidade")):
                continue
            if produto_id is None:
                errors.append(f"Item {index + 1}: selecione um produto.")
                continue
            if quantidade is None or quantidade <= 0:
                errors.append(f"Item {index + 1}: a quantidade deve ser um número inteiro maior que zero.")
                continue
            if quantidade > 10_000_000:
                errors.append(f"Item {index + 1}: quantidade muito alta.")
                continue
            merged[produto_id] = merged.get(produto_id, 0) + quantidade
        if not merged and not errors:
            errors.append("Adicione pelo menos um produto ao pedido.")
        return merged, errors

    def calculate(self, moeda, raw_items, check_stock=True):
        """Calcula linhas e total sem gravar. Retorna (itens, total, avisos)."""
        moeda = (moeda or "").upper()
        errors = {}
        if moeda not in SUPPORTED_CURRENCIES:
            errors["moeda"] = "Selecione uma moeda válida."
        quantities, item_errors = self._parse_items(raw_items)
        if item_errors:
            errors["itens"] = " ".join(item_errors)
        if errors:
            raise ValidationError(errors)

        products = {}
        for produto_id, quantidade in quantities.items():
            product = self.repo.get("produtos", produto_id)
            if product is None:
                raise ValidationError({"itens": f"Produto {produto_id} não encontrado."})
            if not product["ativo"]:
                raise ValidationError({"itens": f"O produto {product['codigo']} está inativo."})
            if check_stock and quantidade > (product["estoque"] or 0):
                raise ValidationError({"itens": f"Estoque insuficiente para {product['codigo']}: disponível {product['estoque']}, solicitado {quantidade}."})
            products[produto_id] = product

        rates = {}
        try:
            for currency in {p["moeda"] for p in products.values()}:
                rates[currency] = self.exchange.get_rate(currency, moeda)
        except ExchangeUnavailableError as exc:
            raise BusinessRuleError(str(exc))

        calculator = PriceCalculator(self.settings.price_multiplier)
        items = []
        for produto_id, quantidade in quantities.items():
            product = products[produto_id]
            rate = rates[product["moeda"]]
            unit = calculator.unit_price(product["custo_unitario"], rate.rate)
            items.append(OrderItem(
                produto_id=produto_id, quantidade=quantidade,
                produto_codigo=product["codigo"], produto_nome=product["nome"],
                custo_unitario=product["custo_unitario"], moeda_custo=product["moeda"],
                multiplicador=calculator.multiplier, taxa_cambio=rate.rate, data_cotacao=rate.date,
                preco_unitario=unit, subtotal=calculator.line_total(unit, quantidade),
            ))
        total = calculator.order_total(i.subtotal for i in items)
        return items, total

    # ------------------------------------------------------------- escrita
    def create(self, cliente_id, moeda, raw_items, observacoes="", user_id=None):
        cliente_id = parse_int(cliente_id)
        if not cliente_id or self.repo.get("clientes", cliente_id) is None:
            raise ValidationError({"cliente_id": "Selecione um cliente válido."})
        # Taxas são consultadas fora da transação (chamada de rede).
        items, total = self.calculate(moeda, raw_items)
        with self.repo.transaction():
            for item in items:  # nova verificação de estoque dentro da transação
                product = self.repo.get("produtos", item.produto_id)
                if product is None or not product["ativo"]:
                    raise ValidationError({"itens": f"O produto {item.produto_codigo} não está mais disponível."})
                if item.quantidade > product["estoque"]:
                    raise ValidationError({"itens": f"Estoque insuficiente para {item.produto_codigo}."})
            order = Order(cliente_id=cliente_id, moeda=moeda.upper(), status="pendente", total=total,
                          observacoes=text(observacoes, 2000), data_pedido=datetime.now().replace(microsecond=0),
                          criado_por=user_id)
            record = self.repo.insert("pedidos", order.to_record())
            numero = f"PED-{record['data_pedido'].year}-{record['id']:05d}"
            record = self.repo.update("pedidos", record["id"], {"numero": numero})
            for item in items:
                item.pedido_id = record["id"]
                self.repo.insert("itens_pedido", item.to_record())
                product = self.repo.get("produtos", item.produto_id)
                self.repo.update("produtos", item.produto_id, {"estoque": product["estoque"] - item.quantidade})
            self.activities.log(user_id, "cadastrou", "pedidos", record["id"],
                                f"Pedido {numero} criado ({record['moeda']} {total})")
        return self.get(record["id"])

    def _restore_stock(self, order_id):
        for item in self.repo.list("itens_pedido", filters={"pedido_id": order_id}):
            product = self.repo.get("produtos", item["produto_id"])
            if product:
                self.repo.update("produtos", product["id"], {"estoque": product["estoque"] + item["quantidade"]})

    def change_status(self, order_id, new_status, user_id=None):
        with self.repo.transaction():
            order = self.get(order_id)
            if not order.can_transition_to(new_status):
                raise BusinessRuleError(
                    f"Não é possível alterar o status de '{order.status_label}' para '{STATUS_LABELS.get(new_status, new_status)}'."
                )
            if new_status == "cancelado":
                self._restore_stock(order.id)
            self.repo.update("pedidos", order.id, {"status": new_status})
            self.activities.log(user_id, "atualizou", "pedidos", order.id,
                                f"Pedido {order.numero}: {order.status_label} → {STATUS_LABELS[new_status]}")
        return self.get(order_id)

    def update_notes(self, order_id, observacoes, user_id=None):
        with self.repo.transaction():
            order = self.get(order_id)
            self.repo.update("pedidos", order.id, {"observacoes": text(observacoes, 2000)})
            self.activities.log(user_id, "atualizou", "pedidos", order.id, f"Observações do pedido {order.numero} atualizadas")

    def delete(self, order_id, user_id=None):
        with self.repo.transaction():
            order = self.get(order_id)
            if not order.can_be_deleted:
                raise BusinessRuleError("Somente pedidos pendentes ou cancelados podem ser excluídos.")
            if order.status in OPEN_STATUSES:
                self._restore_stock(order.id)
            self.repo.delete("pedidos", order.id)  # itens excluídos em cascata
            self.activities.log(user_id, "excluiu", "pedidos", None, f"Pedido {order.numero} excluído")
        return order
