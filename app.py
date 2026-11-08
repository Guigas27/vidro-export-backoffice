"""Vidro Export Backoffice — ponto de entrada da aplicação Flask."""
import secrets
from pathlib import Path
import sys
from datetime import date, datetime
from decimal import Decimal

import click
from flask import Flask, abort, render_template, request, session

from config import Config
from database import create_repository
from database.exceptions import DatabaseConnectionError, RepositoryError, StorageCorruptedError
from models.order import STATUS_LABELS
from models.user import PROFILES
from services import ServiceContainer
from services.exchange_service import SUPPORTED_CURRENCIES, ExchangeService


def format_money(value, currency=None):
    if value is None:
        return "—"
    value = Decimal(value).quantize(Decimal("0.01"))
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{currency} {text}" if currency else text


def format_number(value, places=0):
    if value is None:
        return "—"
    text = f"{Decimal(value):,.{places}f}"
    return text.replace(",", "X").replace(".", ",").replace("X", ".")


def format_datetime(value, with_time=True):
    if not value:
        return "—"
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M" if with_time else "%d/%m/%Y")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    return str(value)


def _local_secret_key(app):
    """Sem SECRET_KEY no .env, gera uma chave aleatória e a guarda em instance/.secret_key."""
    if app.config.get("TESTING"):
        return secrets.token_hex(32)
    path = Path(app.config["BASE_DIR"]) / "instance" / ".secret_key"
    try:
        if path.exists() and path.read_text(encoding="utf-8").strip():
            return path.read_text(encoding="utf-8").strip()
        path.parent.mkdir(parents=True, exist_ok=True)
        key = secrets.token_hex(32)
        path.write_text(key, encoding="utf-8")
        app.logger.warning("SECRET_KEY não definida no .env; chave gerada em %s.", path)
        return key
    except OSError:
        app.logger.warning("SECRET_KEY não definida e não foi possível gravar instance/.secret_key; usando chave temporária.")
        return secrets.token_hex(32)


def _csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def create_app(overrides=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    if not app.config.get("SECRET_KEY") or app.config["SECRET_KEY"] == "defina_uma_chave_segura":
        app.config["SECRET_KEY"] = _local_secret_key(app)

    app.extensions["db_error"] = None
    try:
        repo = create_repository(app.config)
        exchange = ExchangeService(
            app.config["EXCHANGE_API_URL"], app.config["EXCHANGE_TIMEOUT"], app.config["EXCHANGE_CACHE_SECONDS"],
            http_get=app.config.get("EXCHANGE_HTTP_GET"),
        )
        container = ServiceContainer(repo, exchange)
        container.settings.ensure_defaults()
        app.extensions["services"] = container
    except (DatabaseConnectionError, StorageCorruptedError) as exc:
        app.extensions["db_error"] = str(exc)
        app.logger.error("Falha ao abrir o banco de dados (%s): %s", app.config.get("DB_MODE"), exc)

    register_blueprints(app)
    register_template_helpers(app)
    register_hooks(app)
    register_commands(app)
    return app


def register_blueprints(app):
    from routes.api import bp as api_bp
    from routes.auth import bp as auth_bp
    from routes.clients import bp as clients_bp
    from routes.dashboard import bp as dashboard_bp
    from routes.exchange import bp as exchange_bp
    from routes.orders import bp as orders_bp
    from routes.products import bp as products_bp
    from routes.settings import bp as settings_bp
    from routes.users import bp as users_bp

    for bp in (auth_bp, dashboard_bp, products_bp, clients_bp, orders_bp, users_bp, exchange_bp, settings_bp, api_bp):
        app.register_blueprint(bp)


def register_template_helpers(app):
    app.jinja_env.filters["money"] = format_money
    app.jinja_env.filters["number"] = format_number
    app.jinja_env.filters["dt"] = format_datetime
    app.jinja_env.globals.update(
        csrf_token=_csrf_token, STATUS_LABELS=STATUS_LABELS, CURRENCIES=SUPPORTED_CURRENCIES,
        PROFILES=PROFILES,
    )


def register_hooks(app):
    from routes.helpers import load_current_user

    @app.before_request
    def _guard():
        if request.endpoint == "static":
            return None
        if app.extensions.get("db_error"):
            return render_template("errors/db_error.html", message=app.extensions["db_error"],
                                   mode=app.config.get("DB_MODE")), 503
        load_current_user()
        if (app.config.get("CSRF_ENABLED") and request.method in ("POST", "PUT", "PATCH", "DELETE")
                and not request.path.startswith("/api/")):
            sent = request.form.get("csrf_token") or request.headers.get("X-CSRFToken")
            if not sent or not secrets.compare_digest(sent, session.get("_csrf_token", "")):
                abort(400, description="Sessão expirada ou formulário inválido. Recarregue a página e tente novamente.")
        return None

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response

    @app.errorhandler(400)
    def _bad_request(error):
        return render_template("errors/error.html", code=400, title="Requisição inválida",
                               message=getattr(error, "description", "")), 400

    @app.errorhandler(403)
    def _forbidden(error):
        return render_template("errors/error.html", code=403, title="Acesso negado",
                               message="Você não tem permissão para acessar esta página."), 403

    @app.errorhandler(404)
    def _not_found(error):
        return render_template("errors/error.html", code=404, title="Página não encontrada",
                               message="O endereço acessado não existe ou o registro foi removido."), 404

    @app.errorhandler(RepositoryError)
    def _repo_error(error):
        app.logger.exception("Erro no armazenamento")
        return render_template("errors/error.html", code=503, title="Erro no banco de dados", message=str(error)), 503

    @app.errorhandler(500)
    def _server_error(error):
        return render_template("errors/error.html", code=500, title="Erro interno",
                               message="Ocorreu um erro inesperado. Tente novamente."), 500


def register_commands(app):
    @app.cli.command("create-admin")
    @click.option("--nome", prompt="Nome completo")
    @click.option("--username", prompt="Usuário")
    @click.option("--email", prompt="E-mail")
    @click.password_option("--password", prompt="Senha", confirmation_prompt="Confirme a senha")
    def create_admin(nome, username, email, password):
        """Cria um usuário administrador de forma segura (senha com hash)."""
        from models.user import User
        from services.errors import ValidationError

        services = app.extensions.get("services")
        if services is None:
            raise click.ClickException(app.extensions.get("db_error") or "Banco indisponível.")
        user = User(nome=nome, username=username.lower(), email=email.lower(), perfil="admin", ativo=True)
        try:
            services.users.save(user, password, password)
        except ValidationError as exc:
            raise click.ClickException("; ".join(exc.errors.values()))
        click.echo(f"Administrador '{user.username}' criado com sucesso.")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Cadastra produtos e clientes de exemplo (não cria pedidos)."""
        from tools.seed_demo import seed
        click.echo(seed(app.extensions["services"]))


if __name__ == "__main__":
    app = create_app()
    if app.extensions.get("db_error"):
        print("\n[ERRO] " + app.extensions["db_error"], file=sys.stderr)
        print("A aplicação exibirá esta mensagem no navegador até que o problema seja corrigido.\n", file=sys.stderr)
    print(f"Vidro Export Backoffice — modo de banco: {app.config['DB_MODE'].upper()}")
    print(f"Acesse: http://{app.config['HOST']}:{app.config['PORT']}")
    app.run(host=app.config["HOST"], port=app.config["PORT"], debug=app.config["FLASK_DEBUG"])
