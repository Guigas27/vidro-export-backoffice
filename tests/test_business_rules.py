"""Regras de negócio executadas nos dois modos (JSON sempre; MySQL se configurado)."""
from decimal import Decimal

import pytest

from models.client import Client
from models.product import Product
from services.errors import BusinessRuleError, ValidationError
from services.exchange_service import ExchangeService, ExchangeUnavailableError
from services.price_calculator import PriceCalculator
from tests.conftest import failing_http_get, fake_http_get, post


# ---------------------------------------------------------------- preços
def test_price_is_cost_times_two():
    calc = PriceCalculator()
    assert calc.sale_price(Decimal("2.10")) == Decimal("4.20")
    assert calc.markup_percent == Decimal("100")
    assert calc.unit_price(Decimal("1.00"), Decimal("5.5")) == Decimal("11.00")
    assert calc.line_total(Decimal("11.00"), 3) == Decimal("33.00")
    assert calc.order_total([Decimal("1.005"), Decimal("2")]) == Decimal("3.01")
    with pytest.raises(ValueError):
        calc.line_total(Decimal("1"), 0)


def test_custom_multiplier():
    assert PriceCalculator(Decimal("2.5")).sale_price(Decimal("10")) == Decimal("25.00")


# ---------------------------------------------------------------- câmbio
def test_exchange_conversion():
    svc = ExchangeService(http_get=fake_http_get())
    rate = svc.get_rate("USD", "BRL")
    assert rate.rate == Decimal("5.5") and rate.source == "Frankfurter"
    assert svc.convert(Decimal("10"), "USD", "BRL")[0] == Decimal("55.00")
    assert svc.get_rate("EUR", "EUR").rate == Decimal("1")


def test_exchange_unavailable_never_invents_rates():
    svc = ExchangeService(http_get=failing_http_get)
    with pytest.raises(ExchangeUnavailableError):
        svc.get_rate("USD", "BRL")
    assert svc.get_rate("USD", "USD").rate == Decimal("1")  # sem conversão, sem API


def test_exchange_cache():
    calls = []
    inner = fake_http_get()

    def counting(url, timeout):
        calls.append(url)
        return inner(url, timeout)
    svc = ExchangeService(http_get=counting)
    svc.get_rate("USD", "BRL")
    svc.get_rate("USD", "BRL")
    assert len(calls) == 1


# -------------------------------------------------------------- cadastros
def _setup(services):
    p1 = services.products.save(Product(codigo="TAC-1", nome="Taça 1", custo_unitario=Decimal("2.00"), moeda="USD", estoque=100))
    p2 = services.products.save(Product(codigo="COP-1", nome="Copo 1", custo_unitario=Decimal("1.00"), moeda="EUR", estoque=50))
    c = services.clients.save(Client(nome="Importadora X", pais="Chile", cidade="Santiago"))
    return p1, p2, c


def test_product_validation_and_duplicates(services):
    with pytest.raises(ValidationError) as exc:
        services.products.save(Product(codigo="", nome="", custo_unitario=Decimal("-1"), moeda="XXX", estoque=-1))
    assert {"codigo", "nome", "custo_unitario", "moeda", "estoque"} <= set(exc.value.errors)
    _setup(services)
    with pytest.raises(ValidationError) as exc:
        services.products.save(Product(codigo="tac-1", nome="Outra", custo_unitario=Decimal("1"), moeda="USD"))
    assert "codigo" in exc.value.errors


def test_client_validation(services):
    with pytest.raises(ValidationError) as exc:
        services.clients.save(Client(nome="", pais="", cidade="", email="invalido"))
    assert {"nome", "pais", "cidade", "email"} <= set(exc.value.errors)


def test_filters(services):
    _setup(services)
    services.clients.save(Client(nome="Glass Co", pais="Portugal", cidade="Porto"))
    assert [c.nome for c in services.clients.list(pais="Portugal")] == ["Glass Co"]
    assert [p.codigo for p in services.products.list(search="copo")] == ["COP-1"]
    assert services.clients.countries() == ["Chile", "Portugal"]


# ---------------------------------------------------------------- pedidos
def test_create_order_with_conversion_and_snapshot(services):
    p1, p2, c = _setup(services)
    order = services.orders.create(c.id, "BRL", [{"produto_id": p1.id, "quantidade": 10},
                                                 {"produto_id": p2.id, "quantidade": "5"}], "FOB Santos")
    # TAC-1: 2.00 USD × 2 × 5.5 = 22.00 BRL ; COP-1: 1.00 EUR × 2 × (5.5/0.9) = 12.22 BRL
    items = {i.produto_codigo: i for i in order.itens}
    assert items["TAC-1"].preco_unitario == Decimal("22.00") and items["TAC-1"].subtotal == Decimal("220.00")
    assert items["COP-1"].preco_unitario == Decimal("12.22")
    assert order.total == Decimal("281.10")
    assert order.numero.startswith("PED-") and order.status == "pendente"
    assert services.products.get(p1.id).estoque == 90

    # alterar custo e multiplicador não altera pedido antigo
    p1.custo_unitario = Decimal("9.99")
    services.products.save(p1)
    services.settings.update({"multiplicador_preco": "3", "moeda_padrao": "USD", "empresa_nome": "Vidro X"})
    again = services.orders.get(order.id)
    assert again.total == Decimal("281.10")
    assert {i.produto_codigo: i.preco_unitario for i in again.itens}["TAC-1"] == Decimal("22.00")


def test_duplicate_lines_are_merged(services):
    p1, _, c = _setup(services)
    order = services.orders.create(c.id, "USD", [{"produto_id": p1.id, "quantidade": 1}, {"produto_id": p1.id, "quantidade": 2}])
    assert len(order.itens) == 1 and order.itens[0].quantidade == 3


def test_order_validations(services):
    p1, _, c = _setup(services)
    with pytest.raises(ValidationError):
        services.orders.create(None, "USD", [{"produto_id": p1.id, "quantidade": 1}])
    with pytest.raises(ValidationError):
        services.orders.create(c.id, "USD", [])
    with pytest.raises(ValidationError):
        services.orders.create(c.id, "USD", [{"produto_id": p1.id, "quantidade": 0}])
    with pytest.raises(ValidationError) as exc:
        services.orders.create(c.id, "USD", [{"produto_id": p1.id, "quantidade": 101}])
    assert "Estoque insuficiente" in exc.value.errors["itens"]
    assert services.repo.count("pedidos") == 0


def test_order_fails_cleanly_without_exchange(services):
    p1, p2, c = _setup(services)
    services.exchange._http_get = failing_http_get
    services.exchange._cache.clear()
    with pytest.raises(BusinessRuleError):
        services.orders.create(c.id, "BRL", [{"produto_id": p1.id, "quantidade": 1}])
    assert services.repo.count("pedidos") == 0
    assert services.products.get(p1.id).estoque == 100
    # mesma moeda funciona offline
    assert services.orders.create(c.id, "USD", [{"produto_id": p1.id, "quantidade": 1}]).total == Decimal("4.00")


def test_status_flow_and_stock_restore(services):
    p1, _, c = _setup(services)
    order = services.orders.create(c.id, "USD", [{"produto_id": p1.id, "quantidade": 10}])
    with pytest.raises(BusinessRuleError):
        services.orders.change_status(order.id, "concluido")
    services.orders.change_status(order.id, "confirmado")
    services.orders.change_status(order.id, "cancelado")
    assert services.products.get(p1.id).estoque == 100
    with pytest.raises(BusinessRuleError):
        services.orders.change_status(order.id, "pendente")


def test_delete_rules_and_integrity(services):
    p1, _, c = _setup(services)
    order = services.orders.create(c.id, "USD", [{"produto_id": p1.id, "quantidade": 5}])
    with pytest.raises(BusinessRuleError):
        services.clients.delete(c.id)
    with pytest.raises(BusinessRuleError):
        services.products.delete(p1.id)
    services.orders.change_status(order.id, "confirmado")
    services.orders.change_status(order.id, "enviado")
    with pytest.raises(BusinessRuleError):
        services.orders.delete(order.id)
    services.orders.change_status(order.id, "concluido")
    assert services.products.get(p1.id).estoque == 95

    pending = services.orders.create(c.id, "USD", [{"produto_id": p1.id, "quantidade": 5}])
    services.orders.delete(pending.id)
    assert services.repo.list("itens_pedido", filters={"pedido_id": pending.id}) == []
    assert services.products.get(p1.id).estoque == 95


def test_dashboard_reflects_stored_data(services):
    p1, p2, c = _setup(services)
    services.orders.create(c.id, "USD", [{"produto_id": p1.id, "quantidade": 2}])
    o2 = services.orders.create(c.id, "USD", [{"produto_id": p1.id, "quantidade": 1}])
    services.orders.change_status(o2.id, "cancelado")
    data = services.dashboard.summary()
    assert data["total_produtos"] == 2 and data["total_clientes"] == 1 and data["total_pedidos"] == 2
    assert data["pedidos_pendentes"] == 1 and data["pedidos_cancelados"] == 1
    assert data["totais_moeda"][0]["total"] == Decimal("8.00")
    assert data["atividades"]


# ------------------------------------------------------- fluxo via HTTP
def test_full_crud_flow_over_http(admin_client, app, tmp_path):
    r = post(admin_client, "/produtos/novo", {"codigo": "tac-bor", "nome": "Taça Bordeaux", "custo_unitario": "2,10",
                                              "moeda": "USD", "estoque": "100", "ativo": "on"})
    assert r.status_code == 302
    r = post(admin_client, "/produtos/novo", {"codigo": "TAC-BOR", "nome": "Dup", "custo_unitario": "1", "moeda": "USD"})
    assert r.status_code == 400 and "Já existe" in r.get_data(as_text=True)
    page = admin_client.get("/produtos/?q=bordeaux").get_data(as_text=True)
    assert "TAC-BOR" in page and "USD 4,20" in page
    assert post(admin_client, "/produtos/1/editar", {"codigo": "TAC-BOR", "nome": "Taça Bordeaux 450",
                                                    "custo_unitario": "2.10", "moeda": "USD", "estoque": "100",
                                                    "ativo": "on"}).status_code == 302
    assert post(admin_client, "/clientes/novo", {"nome": "Importadora", "pais": "Chile", "cidade": "Santiago"}).status_code == 302
    assert "Importadora" in admin_client.get("/clientes/?pais=Chile").get_data(as_text=True)

    calc = admin_client.post("/pedidos/calcular", json={"moeda": "BRL", "itens": [{"produto_id": 1, "quantidade": 2}]},
                             headers={"X-CSRFToken": _token(admin_client)})
    assert calc.get_json()["total"] == "46.20"
    r = post(admin_client, "/pedidos/novo", {"cliente_id": "1", "moeda": "BRL", "produto_id[]": ["1"], "quantidade[]": ["2"]})
    assert r.status_code == 302
    detail = admin_client.get(r.location).get_data(as_text=True)
    assert "BRL 46,20" in detail
    assert "Pendente" in admin_client.get("/pedidos/?status=pendente").get_data(as_text=True)
    assert post(admin_client, "/pedidos/1/status", {"status": "confirmado"}).status_code == 302
    assert "Confirmado" in admin_client.get("/pedidos/1").get_data(as_text=True)

    # integridade: cliente com pedido não pode ser excluído
    post(admin_client, "/clientes/1/excluir")
    assert app.extensions["services"].repo.get("clientes", 1) is not None

    # persistência: nova instância da aplicação lê os mesmos arquivos
    from app import create_app
    app2 = create_app({"JSON_DATA_DIR": app.config["JSON_DATA_DIR"], "SECRET_KEY": "test-secret", "TESTING": True})
    repo2 = app2.extensions["services"].repo
    assert repo2.get("pedidos", 1)["status"] == "confirmado"
    assert repo2.get("produtos", 1)["estoque"] == 98

    for url in ["/", "/cambio/", "/configuracoes/", "/usuarios/", "/clientes/1", "/pedidos/novo"]:
        assert admin_client.get(url).status_code == 200, url


def _token(client):
    with client.session_transaction() as sess:
        return sess["_csrf_token"]
