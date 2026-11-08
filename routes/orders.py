from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for

from routes.helpers import current_user_id, login_required, services
from services.errors import BusinessRuleError, NotFound, ValidationError
from services.pagination import paginate

bp = Blueprint("orders", __name__, url_prefix="/pedidos")


def _items_from_form(form):
    produtos = form.getlist("produto_id[]")
    quantidades = form.getlist("quantidade[]")
    return [{"produto_id": p, "quantidade": q} for p, q in zip(produtos, quantidades)]


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    cliente_id = request.args.get("cliente_id", type=int)
    moeda = request.args.get("moeda", "")
    orders = services().orders.list(search=q, status=status or None, cliente_id=cliente_id, moeda=moeda or None)
    return render_template("orders/list.html", page=paginate(orders, request.args.get("page", 1)),
                           q=q, status=status, cliente_id=cliente_id, moeda=moeda,
                           clients=services().clients.list())


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def create():
    errors, form = {}, {"moeda": services().settings.default_currency, "itens": [{}]}
    if request.method == "POST":
        form = {"cliente_id": request.form.get("cliente_id"), "moeda": request.form.get("moeda"),
                "observacoes": request.form.get("observacoes", ""), "itens": _items_from_form(request.form) or [{}]}
        try:
            order = services().orders.create(form["cliente_id"], form["moeda"], form["itens"],
                                             form["observacoes"], current_user_id())
            flash(f"Pedido {order.numero} criado com sucesso.", "success")
            return redirect(url_for("orders.detail", order_id=order.id))
        except ValidationError as exc:
            errors = exc.errors
        except BusinessRuleError as exc:
            errors = {"geral": str(exc)}
    products = services().products.list(status="ativos")
    return render_template("orders/form.html", errors=errors, form=form, clients=services().clients.list(),
                           products=products, multiplier=services().settings.price_multiplier), (400 if errors else 200)


@bp.route("/calcular", methods=["POST"])
@login_required
def calculate():
    payload = request.get_json(silent=True) or {}
    try:
        items, total = services().orders.calculate(payload.get("moeda"), payload.get("itens") or [])
    except ValidationError as exc:
        return jsonify(ok=False, erros=exc.errors, mensagem=" ".join(exc.errors.values())), 400
    except BusinessRuleError as exc:
        return jsonify(ok=False, mensagem=str(exc)), 503
    return jsonify(ok=True, moeda=payload.get("moeda", "").upper(), total=str(total), itens=[{
        "produto_id": i.produto_id, "codigo": i.produto_codigo, "nome": i.produto_nome,
        "quantidade": i.quantidade, "custo_unitario": str(i.custo_unitario), "moeda_custo": i.moeda_custo,
        "taxa_cambio": str(i.taxa_cambio), "data_cotacao": i.data_cotacao.isoformat(),
        "preco_unitario": str(i.preco_unitario), "subtotal": str(i.subtotal),
    } for i in items])


@bp.route("/<int:order_id>")
@login_required
def detail(order_id):
    try:
        order = services().orders.get(order_id)
    except NotFound as exc:
        flash(str(exc), "warning")
        return redirect(url_for("orders.index"))
    return render_template("orders/detail.html", order=order)


@bp.route("/<int:order_id>/status", methods=["POST"])
@login_required
def change_status(order_id):
    try:
        order = services().orders.change_status(order_id, request.form.get("status"), current_user_id())
        flash(f"Status do pedido {order.numero} alterado para {order.status_label}.", "success")
    except (NotFound, BusinessRuleError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("orders.detail", order_id=order_id))


@bp.route("/<int:order_id>/observacoes", methods=["POST"])
@login_required
def update_notes(order_id):
    try:
        services().orders.update_notes(order_id, request.form.get("observacoes", ""), current_user_id())
        flash("Observações atualizadas.", "success")
    except NotFound as exc:
        flash(str(exc), "danger")
    return redirect(url_for("orders.detail", order_id=order_id))


@bp.route("/<int:order_id>/excluir", methods=["POST"])
@login_required
def delete(order_id):
    try:
        order = services().orders.delete(order_id, current_user_id())
        flash(f"Pedido {order.numero} excluído.", "success")
        return redirect(url_for("orders.index"))
    except (NotFound, BusinessRuleError) as exc:
        flash(str(exc), "danger")
        return redirect(url_for("orders.detail", order_id=order_id))
