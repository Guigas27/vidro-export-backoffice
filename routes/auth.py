from urllib.parse import urlparse

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, session, url_for

from models.user import User
from routes.helpers import login_required, services
from services.errors import BusinessRuleError, ValidationError

bp = Blueprint("auth", __name__)


def _safe_next(target):
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.netloc or parsed.scheme or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@bp.route("/login", methods=["GET", "POST"])
def login():
    if services().users.count() == 0:
        return redirect(url_for("auth.setup"))
    if g.user:
        return redirect(url_for("dashboard.index"))
    errors = {}
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if not username.strip():
            errors["username"] = "Informe o usuário ou e-mail."
        if not password:
            errors["password"] = "Informe a senha."
        if not errors:
            user = services().users.authenticate(username, password)
            if user:
                csrf = session.get("_csrf_token")
                session.clear()
                session["user_id"] = user.id
                if csrf:
                    session["_csrf_token"] = csrf
                session.permanent = True
                services().activities.log(user.id, "login", "usuarios", user.id, f"{user.username} entrou no sistema")
                flash(f"Bem-vindo(a), {user.nome}!", "success")
                return redirect(_safe_next(request.args.get("next")) or url_for("dashboard.index"))
            flash("Usuário ou senha inválidos.", "danger")
    return render_template("auth/login.html", errors=errors), (400 if errors else 200)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("Você saiu do sistema.", "info")
    return redirect(url_for("auth.login"))


@bp.route("/setup", methods=["GET", "POST"])
def setup():
    if services().users.count() > 0:
        return redirect(url_for("auth.login"))
    errors, form = {}, {}
    if request.method == "POST":
        form = request.form
        try:
            user = services().users.create_first_admin(form)
            session.clear()
            session["user_id"] = user.id
            flash("Administrador criado com sucesso. Bem-vindo(a)!", "success")
            return redirect(url_for("dashboard.index"))
        except ValidationError as exc:
            errors = exc.errors
        except BusinessRuleError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("auth.login"))
    return render_template("auth/setup.html", errors=errors, form=form)


@bp.route("/cadastro", methods=["GET", "POST"])
def register():
    if not current_app.config.get("ALLOW_SIGNUP"):
        abort(404)
    if services().users.count() == 0:
        return redirect(url_for("auth.setup"))
    if g.user:
        return redirect(url_for("dashboard.index"))
    errors, form = {}, {}
    if request.method == "POST":
        form = request.form
        try:
            user = services().users.register(form)
            csrf = session.get("_csrf_token")
            session.clear()
            session["user_id"] = user.id
            if csrf:
                session["_csrf_token"] = csrf
            flash(f"Conta criada com sucesso. Bem-vindo(a), {user.nome}!", "success")
            return redirect(url_for("dashboard.index"))
        except ValidationError as exc:
            errors = exc.errors
        except BusinessRuleError as exc:
            flash(str(exc), "danger")
    return render_template("auth/register.html", errors=errors, form=form), (400 if errors else 200)


@bp.route("/perfil", methods=["GET", "POST"])
@login_required
def profile():
    errors = {}
    if request.method == "POST":
        current = request.form.get("current_password", "")
        if not g.user.check_password(current):
            errors["current_password"] = "Senha atual incorreta."
        else:
            user = User.from_record({**g.user.to_record(exclude=()), "id": g.user.id})
            try:
                services().users.save(user, request.form.get("password"), request.form.get("password_confirm"), g.user.id)
                flash("Senha alterada com sucesso.", "success")
                return redirect(url_for("dashboard.index"))
            except ValidationError as exc:
                errors = exc.errors
                if not request.form.get("password"):
                    errors["password"] = "Informe a nova senha."
    return render_template("auth/profile.html", errors=errors)
