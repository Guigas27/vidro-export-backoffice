from functools import wraps

from flask import abort, current_app, flash, g, redirect, request, session, url_for

from models.user import User


def services():
    return current_app.extensions["services"]


def load_current_user():
    g.user = None
    user_id = session.get("user_id")
    if user_id:
        user = User.from_record(services().repo.get("usuarios", user_id))
        if user and user.ativo:
            g.user = user
        else:
            session.clear()


def current_user_id():
    return g.user.id if getattr(g, "user", None) else None


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if getattr(g, "user", None) is None:
            if services().users.count() == 0:
                return redirect(url_for("auth.setup"))
            flash("Faça login para continuar.", "warning")
            return redirect(url_for("auth.login", next=request.full_path if request.method == "GET" else None))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not g.user.is_admin:
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def flash_errors(error):
    flash(str(error), "danger")
