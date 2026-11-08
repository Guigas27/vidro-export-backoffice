"""Definição única das entidades persistidas.

Esta descrição é compartilhada pelos repositórios JSON e MySQL para que os
dois modos tenham exatamente as mesmas regras de tipos, unicidade e
integridade referencial.
"""

# Tipos suportados: int, str, decimal, bool, datetime, date
TABLES = {
    "usuarios": {
        "fields": {
            "id": "int", "nome": "str", "username": "str", "email": "str",
            "password_hash": "str", "perfil": "str", "ativo": "bool",
            "criado_em": "datetime", "atualizado_em": "datetime",
        },
        "unique": ["username", "email"],
        "search": ["nome", "username", "email"],
    },
    "produtos": {
        "fields": {
            "id": "int", "codigo": "str", "nome": "str", "descricao": "str",
            "custo_unitario": "decimal", "moeda": "str", "estoque": "int",
            "ativo": "bool", "criado_em": "datetime", "atualizado_em": "datetime",
        },
        "unique": ["codigo"],
        "search": ["codigo", "nome", "descricao"],
    },
    "clientes": {
        "fields": {
            "id": "int", "nome": "str", "pais": "str", "cidade": "str",
            "email": "str", "telefone": "str", "endereco": "str",
            "identificacao_fiscal": "str", "criado_em": "datetime",
            "atualizado_em": "datetime",
        },
        "unique": [],
        "search": ["nome", "pais", "cidade", "email", "identificacao_fiscal"],
    },
    "pedidos": {
        "fields": {
            "id": "int", "numero": "str", "cliente_id": "int", "moeda": "str",
            "status": "str", "total": "decimal", "observacoes": "str",
            "data_pedido": "datetime", "criado_por": "int",
            "criado_em": "datetime", "atualizado_em": "datetime",
        },
        "unique": ["numero"],
        "search": ["numero", "observacoes"],
    },
    "itens_pedido": {
        "fields": {
            "id": "int", "pedido_id": "int", "produto_id": "int",
            "produto_codigo": "str", "produto_nome": "str", "quantidade": "int",
            "custo_unitario": "decimal", "moeda_custo": "str",
            "multiplicador": "decimal", "taxa_cambio": "decimal",
            "data_cotacao": "date", "preco_unitario": "decimal",
            "subtotal": "decimal",
        },
        "unique": [],
        "search": ["produto_codigo", "produto_nome"],
    },
    "configuracoes": {
        "fields": {"id": "int", "chave": "str", "valor": "str", "atualizado_em": "datetime"},
        "unique": ["chave"],
        "search": ["chave"],
    },
    "atividades": {
        "fields": {
            "id": "int", "usuario_id": "int", "acao": "str", "entidade": "str",
            "entidade_id": "int", "descricao": "str", "criado_em": "datetime",
        },
        "unique": [],
        "search": ["descricao", "entidade", "acao"],
    },
}

# (tabela_filha, coluna) -> (tabela_pai, regra ao excluir o pai)
FOREIGN_KEYS = {
    ("pedidos", "cliente_id"): ("clientes", "RESTRICT"),
    ("pedidos", "criado_por"): ("usuarios", "SET NULL"),
    ("itens_pedido", "pedido_id"): ("pedidos", "CASCADE"),
    ("itens_pedido", "produto_id"): ("produtos", "RESTRICT"),
    ("atividades", "usuario_id"): ("usuarios", "SET NULL"),
}

# Ordem segura para inicialização e migração (pais antes dos filhos).
TABLE_ORDER = [
    "usuarios", "configuracoes", "produtos", "clientes",
    "pedidos", "itens_pedido", "atividades",
]

FILE_NAMES = {name: f"{name}.json" for name in TABLES}

DEFAULT_SETTINGS = {
    "multiplicador_preco": "2",
    "moeda_padrao": "USD",
    "empresa_nome": "Vidro Export",
}


def fields_of(table):
    return TABLES[table]["fields"]


def check_table(table):
    if table not in TABLES:
        raise ValueError(f"Tabela desconhecida: {table}")


def check_column(table, column):
    check_table(table)
    if column not in TABLES[table]["fields"]:
        raise ValueError(f"Coluna desconhecida: {table}.{column}")
