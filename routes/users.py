from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from models.user import User
from routes.helpers import admin_required, services
from services.errors import BusinessRuleError, NotFound, ValidationError
from services.pagination import paginate

bp = Blueprint("users", __name__, url_prefix="/usuarios")


@bp.route("/")
@admin_required
def index():
    q = request.args.get("q", "").strip()
    return render_template("users/list.html", page=paginate(services().users.list(search=q), request.args.get("page", 1)), q=q)


@bp.route("/novo", methods=["GET", "POST"])
@admin_required
def create():
    user, errors = User(), {}
    if request.method == "POST":
        user = User.from_form(request.form)
        try:
            saved = services().users.save(user, request.form.get("password"), request.form.get("password_confirm"), g.user.id)
            flash(f"Usuário {saved.username} cadastrado com sucesso.", "success")
            return redirect(url_for("users.index"))
        except ValidationError as exc:
            errors = exc.errors
    return render_template("users/form.html", user=user, errors=errors, title="Novo usuário"), (400 if errors else 200)


@bp.route("/<int:user_id>/editar", methods=["GET", "POST"])
@admin_required
def edit(user_id):
    try:
        user = services().users.get(user_id)
    except NotFound as exc:
        flash(str(exc), "warning")
        return redirect(url_for("users.index"))
    errors = {}
    if request.method == "POST":
        user = User.from_form(request.form, user_id)
        try:
            services().users.save(user, request.form.get("password") or None, request.form.get("password_confirm"), g.user.id)
            flash("Usuário atualizado com sucesso.", "success")
            return redirect(url_for("users.index"))
        except ValidationError as exc:
            errors = exc.errors
        except BusinessRuleError as exc:
            errors = {"geral": str(exc)}
    return render_template("users/form.html", user=user, errors=errors, title="Editar usuário"), (400 if errors else 200)


@bp.route("/<int:user_id>/excluir", methods=["POST"])
@admin_required
def delete(user_id):
    try:
        user = services().users.delete(user_id, g.user.id)
        flash(f"Usuário {user.username} excluído.", "success")
    except (NotFound, BusinessRuleError) as exc:
        flash(str(exc), "danger")
    return redirect(url_for("users.index"))
