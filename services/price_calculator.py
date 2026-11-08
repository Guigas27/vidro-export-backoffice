from decimal import ROUND_HALF_UP, Decimal

CENT = Decimal("0.01")


class PriceCalculator:
    """Regra comercial: preço de venda = custo × multiplicador (padrão 2 = +100%)."""

    def __init__(self, multiplier=Decimal("2")):
        self.multiplier = Decimal(str(multiplier))
        if self.multiplier <= 0:
            raise ValueError("O multiplicador deve ser positivo.")

    @staticmethod
    def round_money(value):
        return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)

    def sale_price(self, cost):
        """Preço de venda na moeda do custo."""
        cost = Decimal(str(cost))
        if cost < 0:
            raise ValueError("O custo não pode ser negativo.")
        return self.round_money(cost * self.multiplier)

    def unit_price(self, cost, exchange_rate=Decimal("1")):
        """Preço de venda unitário convertido para a moeda do pedido."""
        rate = Decimal(str(exchange_rate))
        if rate <= 0:
            raise ValueError("A taxa de câmbio deve ser positiva.")
        return self.round_money(Decimal(str(cost)) * self.multiplier * rate)

    def line_total(self, unit_price, quantity):
        if int(quantity) <= 0:
            raise ValueError("A quantidade deve ser maior que zero.")
        return self.round_money(Decimal(unit_price) * int(quantity))

    def order_total(self, line_totals):
        return self.round_money(sum((Decimal(v) for v in line_totals), Decimal("0")))

    @property
    def markup_percent(self):
        return (self.multiplier - 1) * 100
