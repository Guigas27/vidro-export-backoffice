from collections import defaultdict
from decimal import Decimal

from models.order import OPEN_STATUSES


class DashboardService:
    def __init__(self, repo, activities):
        self.repo = repo
        self.activities = activities

    def summary(self):
        products = self.repo.list("produtos")
        clients = self.repo.list("clientes")
        orders = self.repo.list("pedidos")
        items = self.repo.list("itens_pedido")
        valid = [o for o in orders if o["status"] != "cancelado"]

        totals = defaultdict(lambda: Decimal("0"))
        counts = defaultdict(int)
        for order in valid:
            totals[order["moeda"]] += order["total"]
            counts[order["moeda"]] += 1
        totals_by_currency = [
            {"moeda": cur, "total": totals[cur], "pedidos": counts[cur],
             "ticket_medio": (totals[cur] / counts[cur]).quantize(Decimal("0.01"))}
            for cur in sorted(totals, key=lambda c: -counts[c])
        ]

        valid_ids = {o["id"] for o in valid}
        qty_by_product = defaultdict(int)
        for item in items:
            if item["pedido_id"] in valid_ids:
                qty_by_product[(item["produto_codigo"], item["produto_nome"])] += item["quantidade"]
        top_products = sorted(qty_by_product.items(), key=lambda kv: -kv[1])[:5]

        orders_by_client = defaultdict(int)
        for order in valid:
            orders_by_client[order["cliente_id"]] += 1
        client_names = {c["id"]: (c["nome"], c["pais"]) for c in clients}
        top_clients = [
            {"nome": client_names.get(cid, ("—", ""))[0], "pais": client_names.get(cid, ("—", ""))[1], "pedidos": n}
            for cid, n in sorted(orders_by_client.items(), key=lambda kv: -kv[1])[:5]
        ]

        status_counts = defaultdict(int)
        for order in orders:
            status_counts[order["status"]] += 1

        countries = {c["pais"].strip().casefold() for c in clients if c["pais"]}
        return {
            "total_produtos": len(products),
            "produtos_ativos": sum(1 for p in products if p["ativo"]),
            "estoque_baixo": sorted([p for p in products if p["ativo"] and (p["estoque"] or 0) < 100],
                                    key=lambda p: p["estoque"] or 0)[:5],
            "total_clientes": len(clients),
            "total_paises": len(countries),
            "total_pedidos": len(orders),
            "pedidos_pendentes": status_counts["pendente"],
            "pedidos_andamento": sum(status_counts[s] for s in OPEN_STATUSES),
            "pedidos_concluidos": status_counts["concluido"],
            "pedidos_cancelados": status_counts["cancelado"],
            "status_counts": dict(status_counts),
            "totais_moeda": totals_by_currency,
            "top_produtos": [{"codigo": k[0], "nome": k[1], "quantidade": v} for k, v in top_products],
            "top_clientes": top_clients,
            "pedidos_recentes": sorted(orders, key=lambda o: o["data_pedido"] or o["criado_em"], reverse=True)[:5],
            "clientes_por_id": client_names,
            "atividades": self.activities.recent(8),
        }
