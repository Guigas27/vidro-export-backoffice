from flask import Blueprint, render_template, request

from models.base import parse_decimal
from routes.helpers import login_required, services
from services.exchange_service import SUPPORTED_CURRENCIES, ExchangeUnavailableError

bp = Blueprint("exchange", __name__, url_prefix="/cambio")


@bp.route("/")
@login_required
def index():
    base = (request.args.get("base") or services().settings.default_currency).upper()
    target = (request.args.get("target") or ("BRL" if base != "BRL" else "USD")).upper()
    amount = parse_decimal(request.args.get("amount") or "1")
    if base not in SUPPORTED_CURRENCIES:
        base = "USD"
    if target not in SUPPORTED_CURRENCIES:
        target = "BRL"
    error, rates, conversion = None, {}, None
    if amount is None or amount < 0:
        error, amount = "Informe um valor válido.", None
    try:
        rates = services().exchange.get_rates(base, ["USD", "EUR", "BRL", "GBP", "CNY", "JPY", "CAD", "MXN", "CHF", "AUD"])
        if amount is not None:
            conversion = services().exchange.convert(amount, base, target)
    except ExchangeUnavailableError as exc:
        error = str(exc)
    return render_template("exchange/index.html", base=base, target=target, amount=amount,
                           rates=rates, conversion=conversion, error=error)
