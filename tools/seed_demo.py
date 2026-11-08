"""Cadastra produtos e clientes de exemplo. Uso: flask --app app seed-demo"""
from decimal import Decimal

from models.client import Client
from models.product import Product
from services.errors import ValidationError

PRODUCTS = [
    ("TAC-BOR-450", "Taça Bordeaux 450 ml", "Cristal sonoro, haste longa. Caixa com 6.", "2.10", "USD", 1200),
    ("TAC-CHA-200", "Taça Champagne Flûte 200 ml", "Vidro sodo-cálcico temperado.", "1.35", "USD", 3400),
    ("TAC-GIN-600", "Taça Gin 600 ml", "Bojo largo para drinks.", "1.80", "EUR", 800),
    ("COP-LON-350", "Copo Long Drink 350 ml", "Base reforçada, empilhável.", "0.55", "USD", 9600),
    ("COP-WHI-300", "Copo Whisky 300 ml", "Fundo grosso, lapidado.", "4.20", "BRL", 2500),
    ("COP-AMR-190", "Copo Americano 190 ml", "Clássico, embalagem com 24.", "1.10", "BRL", 60),
]
CLIENTS = [
    ("Glassworks Import LLC", "Estados Unidos", "Miami", "compras@glassworks.example", "+1 305 555 0100", "1200 Biscayne Blvd", "EIN 12-3456789"),
    ("Vinhos & Copos Lda.", "Portugal", "Porto", "geral@vinhoscopos.example", "+351 22 555 0101", "Rua das Flores, 45", "PT509876543"),
    ("Hostelería Andina S.A.", "Chile", "Santiago", "pedidos@andina.example", "+56 2 2555 0102", "Av. Providencia 1500", "RUT 76.543.210-K"),
]


def seed(services):
    created = 0
    for codigo, nome, desc, custo, moeda, estoque in PRODUCTS:
        if services.repo.find_one("produtos", codigo=codigo):
            continue
        try:
            services.products.save(Product(codigo=codigo, nome=nome, descricao=desc, custo_unitario=Decimal(custo),
                                           moeda=moeda, estoque=estoque, ativo=True))
            created += 1
        except ValidationError:
            pass
    for nome, pais, cidade, email, tel, end, fiscal in CLIENTS:
        if services.repo.find_one("clientes", nome=nome):
            continue
        services.clients.save(Client(nome=nome, pais=pais, cidade=cidade, email=email, telefone=tel,
                                     endereco=end, identificacao_fiscal=fiscal))
        created += 1
    return f"{created} registro(s) de exemplo criados."
