from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from routes.helpers import admin_required, services
from services.errors import ValidationError

bp = Blueprint("settings", __name__, url_prefix="/configuracoes")


@bp.route("/", methods=["GET", "POST"])
@admin_required
def index():
    errors, values = {}, services().settings.all()
    if request.method == "POST":
        try:
            services().settings.update(request.form, services().activities, g.user.id)
            flash("Configurações salvas. Novos pedidos usarão as novas regras; pedidos existentes não são alterados.", "success")
            return redirect(url_for("settings.index"))
        except ValidationError as exc:
            errors, values = exc.errors, request.form
    return render_template("settings.html", errors=errors, values=values, db_mode=services().repo.mode), (400 if errors else 200)
