from flask import Blueprint, flash, redirect, render_template, request, url_for

from models.product import Product
from routes.helpers import current_user_id, login_required, services
from services.errors import BusinessRuleError, NotFound, ValidationError
from services.pagination import paginate
from services.price_calculator import PriceCalculator

bp = Blueprint("products", __name__, url_prefix="/produtos")


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    page = paginate(services().products.list(search=q, status=status), request.args.get("page", 1))
    calc = PriceCalculator(services().settings.price_multiplier)
    return render_template("products/list.html", page=page, q=q, status=status, calc=calc)


def _form(product, errors, title):
    return render_template("products/form.html", product=product, errors=errors, title=title,
                           multiplier=services().settings.price_multiplier)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def create():
    product = Product(moeda=services().settings.default_currency)
    errors = {}
    if request.method == "POST":
        product = Product.from_form(request.form)
        try:
            saved = services().products.save(product, current_user_id())
            flash(f"Produto {saved.codigo} cadastrado com sucesso.", "success")
            return redirect(url_for("products.index"))
        except ValidationError as exc:
            errors = exc.errors
    return _form(product, errors, "Novo produto"), (400 if errors else 200)


@bp.route("/<int:product_id>/editar", methods=["GET", "POST"])
@login_required
def edit(product_id):
    try:
        product = services().products.get(product_id)
    except NotFound as exc:
        flash(str(exc), "warning")
        return redirect(url_for("products.index"))
    errors = {}
    if request.method == "POST":
        product = Product.from_form(request.form, product_id)
        try:
            services().products.save(product, current_user_id())
            flash("Produto atualizado com sucesso.", "success")
            return redirect(url_for("products.index"))
        except ValidationError as exc:
            errors = exc.errors
    return _form(product, errors, "Editar produto"), (400 if errors else 200)


@bp.route("/<int:product_id>/excluir", methods=["POST"])
@login_required
def delete(product_id):
    try:
        product = services().products.delete(product_id, current_user_id())
        flash(f"Produto {product.codigo} excluído.", "success")
    except (NotFound, BusinessRuleError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("products.index"))
