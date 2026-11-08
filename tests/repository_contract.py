"""Testes de contrato: os repositórios JSON e MySQL devem se comportar igual."""
from datetime import datetime
from decimal import Decimal

import pytest

from database.exceptions import DuplicateError, IntegrityViolationError, NotFoundError


def product(codigo="TAC-01", **kw):
    data = {"codigo": codigo, "nome": "Taça Teste", "descricao": "", "custo_unitario": Decimal("2.5"),
            "moeda": "USD", "estoque": 10, "ativo": True}
    data.update(kw)
    return data


def client(nome="Cliente A", pais="Brasil"):
    return {"nome": nome, "pais": pais, "cidade": "São Paulo", "email": "", "telefone": "",
            "endereco": "", "identificacao_fiscal": ""}


class RepositoryContract:
    @pytest.fixture
    def repo(self):
        raise NotImplementedError

    def test_insert_and_get_with_types(self, repo):
        rec = repo.insert("produtos", product())
        assert isinstance(rec["id"], int)
        got = repo.get("produtos", rec["id"])
        assert got["codigo"] == "TAC-01"
        assert got["custo_unitario"] == Decimal("2.5")
        assert got["ativo"] is True
        assert isinstance(got["criado_em"], datetime)
        assert repo.get("produtos", 9999) is None

    def test_unique_ids(self, repo):
        a = repo.insert("produtos", product("A"))
        b = repo.insert("produtos", product("B"))
        assert a["id"] != b["id"]

    def test_update(self, repo):
        rec = repo.insert("produtos", product())
        upd = repo.update("produtos", rec["id"], {"nome": "Novo nome", "estoque": 3})
        assert upd["nome"] == "Novo nome" and upd["estoque"] == 3
        assert repo.get("produtos", rec["id"])["nome"] == "Novo nome"
        with pytest.raises(NotFoundError):
            repo.update("produtos", 9999, {"nome": "x"})

    def test_delete(self, repo):
        rec = repo.insert("produtos", product())
        repo.delete("produtos", rec["id"])
        assert repo.get("produtos", rec["id"]) is None
        with pytest.raises(NotFoundError):
            repo.delete("produtos", rec["id"])

    def test_unique_constraint_case_insensitive(self, repo):
        repo.insert("produtos", product("TAC-01"))
        with pytest.raises(DuplicateError) as exc:
            repo.insert("produtos", product("tac-01"))
        assert exc.value.field == "codigo"

    def test_filters_search_order(self, repo):
        repo.insert("clientes", client("Zeta Importações", "Chile"))
        repo.insert("clientes", client("alfa Glass", "Portugal"))
        repo.insert("clientes", client("Média Distribuição", "Chile"))
        assert [c["nome"] for c in repo.list("clientes", order_by="nome")] == ["alfa Glass", "Média Distribuição", "Zeta Importações"]
        assert len(repo.list("clientes", filters={"pais": "Chile"})) == 2
        assert [c["nome"] for c in repo.list("clientes", search="GLASS")] == ["alfa Glass"]
        assert [c["nome"] for c in repo.list("clientes", search="media")] == ["Média Distribuição"]
        assert len(repo.list("clientes", order_by="nome", descending=True, limit=1)) == 1
        assert repo.count("clientes", {"pais": "Chile"}) == 2
        assert repo.find_one("clientes", pais="Portugal")["nome"] == "alfa Glass"

    def test_foreign_key_on_insert(self, repo):
        with pytest.raises(IntegrityViolationError):
            repo.insert("pedidos", {"cliente_id": 999, "moeda": "USD", "status": "pendente", "total": 0,
                                    "data_pedido": datetime.now()})

    def _order(self, repo):
        c = repo.insert("clientes", client())
        p = repo.insert("produtos", product())
        o = repo.insert("pedidos", {"cliente_id": c["id"], "moeda": "USD", "status": "pendente",
                                    "total": Decimal("5"), "data_pedido": datetime.now()})
        i = repo.insert("itens_pedido", {"pedido_id": o["id"], "produto_id": p["id"], "produto_codigo": "TAC-01",
                                         "produto_nome": "Taça", "quantidade": 1, "custo_unitario": Decimal("2.5"),
                                         "moeda_custo": "USD", "multiplicador": Decimal("2"), "taxa_cambio": Decimal("1"),
                                         "data_cotacao": datetime.now().date(), "preco_unitario": Decimal("5"),
                                         "subtotal": Decimal("5")})
        return c, p, o, i

    def test_restrict_delete(self, repo):
        c, p, o, i = self._order(repo)
        with pytest.raises(IntegrityViolationError):
            repo.delete("clientes", c["id"])
        with pytest.raises(IntegrityViolationError):
            repo.delete("produtos", p["id"])
        assert repo.get("clientes", c["id"]) is not None

    def test_cascade_delete(self, repo):
        c, p, o, i = self._order(repo)
        repo.delete("pedidos", o["id"])
        assert repo.get("itens_pedido", i["id"]) is None
        repo.delete("produtos", p["id"])

    def test_set_null_delete(self, repo):
        u = repo.insert("usuarios", {"nome": "U", "username": "u1", "email": "u@x.com", "password_hash": "h",
                                     "perfil": "operador", "ativo": True})
        a = repo.insert("atividades", {"usuario_id": u["id"], "acao": "x", "entidade": "y", "descricao": "z"})
        repo.delete("usuarios", u["id"])
        assert repo.get("atividades", a["id"])["usuario_id"] is None

    def test_transaction_rollback(self, repo):
        with pytest.raises(RuntimeError):
            with repo.transaction():
                repo.insert("produtos", product("ROLL"))
                raise RuntimeError("falha")
        assert repo.find_one("produtos", codigo="ROLL") is None

    def test_transaction_commit(self, repo):
        with repo.transaction():
            repo.insert("produtos", product("A"))
            repo.insert("produtos", product("B"))
        assert repo.count("produtos") == 2

    def test_explicit_id_insert(self, repo):
        repo.insert("produtos", product("X", id=50))
        nxt = repo.insert("produtos", product("Y"))
        assert nxt["id"] > 50
        with pytest.raises(DuplicateError):
            repo.insert("produtos", product("Z", id=50))
