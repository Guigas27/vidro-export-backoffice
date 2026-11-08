from flask import Blueprint, flash, redirect, render_template, request, url_for

from models.client import Client
from routes.helpers import current_user_id, login_required, services
from services.errors import BusinessRuleError, NotFound, ValidationError
from services.pagination import paginate

bp = Blueprint("clients", __name__, url_prefix="/clientes")


@bp.route("/")
@login_required
def index():
    q = request.args.get("q", "").strip()
    pais = request.args.get("pais", "").strip()
    page = paginate(services().clients.list(search=q, pais=pais or None), request.args.get("page", 1))
    return render_template("clients/list.html", page=page, q=q, pais=pais, countries=services().clients.countries())


@bp.route("/<int:client_id>")
@login_required
def detail(client_id):
    try:
        client = services().clients.get(client_id)
    except NotFound as exc:
        flash(str(exc), "warning")
        return redirect(url_for("clients.index"))
    orders = services().orders.list(cliente_id=client_id)
    return render_template("clients/detail.html", client=client, orders=orders)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def create():
    client, errors = Client(), {}
    if request.method == "POST":
        client = Client.from_form(request.form)
        try:
            saved = services().clients.save(client, current_user_id())
            flash(f"Cliente {saved.nome} cadastrado com sucesso.", "success")
            return redirect(url_for("clients.index"))
        except ValidationError as exc:
            errors = exc.errors
    return render_template("clients/form.html", client=client, errors=errors, title="Novo cliente"), (400 if errors else 200)


@bp.route("/<int:client_id>/editar", methods=["GET", "POST"])
@login_required
def edit(client_id):
    try:
        client = services().clients.get(client_id)
    except NotFound as exc:
        flash(str(exc), "warning")
        return redirect(url_for("clients.index"))
    errors = {}
    if request.method == "POST":
        client = Client.from_form(request.form, client_id)
        try:
            services().clients.save(client, current_user_id())
            flash("Cliente atualizado com sucesso.", "success")
            return redirect(url_for("clients.index"))
        except ValidationError as exc:
            errors = exc.errors
    return render_template("clients/form.html", client=client, errors=errors, title="Editar cliente"), (400 if errors else 200)


@bp.route("/<int:client_id>/excluir", methods=["POST"])
@login_required
def delete(client_id):
    try:
        client = services().clients.delete(client_id, current_user_id())
        flash(f"Cliente {client.nome} excluído.", "success")
    except (NotFound, BusinessRuleError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("clients.index"))
