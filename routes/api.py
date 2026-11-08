"""API JSON autenticada por token JWT (PyJWT)."""
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import Blueprint, current_app, g, jsonify, request

from models.user import User
from routes.helpers import services
from services.errors import BusinessRuleError, NotFound, ValidationError

bp = Blueprint("api", __name__, url_prefix="/api")


def _serialize(obj):
    from dataclasses import asdict, is_dataclass
    from datetime import date
    from decimal import Decimal

    if is_dataclass(obj):
        obj = asdict(obj)
        obj.pop("password_hash", None)
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items() if k != "password_hash"}
    if isinstance(obj, (list, tuple)):
        return [_serialize(v) for v in obj]
    if isinstance(obj, Decimal):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return obj


def issue_token(user):
    now = datetime.now(timezone.utc)
    payload = {"sub": str(user.id), "perfil": user.perfil, "iat": now,
               "exp": now + timedelta(minutes=current_app.config["JWT_EXPIRATION_MINUTES"])}
    return jwt.encode(payload, current_app.config["SECRET_KEY"], algorithm="HS256")


def token_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify(erro="Token ausente. Envie 'Authorization: Bearer <token>'."), 401
        try:
            payload = jwt.decode(header[7:], current_app.config["SECRET_KEY"], algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            return jsonify(erro="Token expirado."), 401
        except jwt.InvalidTokenError:
            return jsonify(erro="Token inválido."), 401
        user = User.from_record(services().repo.get("usuarios", int(payload["sub"])))
        if user is None or not user.ativo:
            return jsonify(erro="Usuário inválido."), 401
        g.api_user = user
        return view(*args, **kwargs)
    return wrapper


@bp.route("/token", methods=["POST"])
def token():
    data = request.get_json(silent=True) or {}
    user = services().users.authenticate(data.get("username"), data.get("password"))
    if user is None:
        return jsonify(erro="Usuário ou senha inválidos."), 401
    return jsonify(token=issue_token(user), tipo="Bearer", expira_em_minutos=current_app.config["JWT_EXPIRATION_MINUTES"])


@bp.route("/produtos")
@token_required
def products():
    return jsonify(_serialize(services().products.list(search=request.args.get("q"))))


@bp.route("/clientes")
@token_required
def clients():
    return jsonify(_serialize(services().clients.list(search=request.args.get("q"))))


@bp.route("/pedidos")
@token_required
def orders():
    rows = services().orders.list(search=request.args.get("q"), status=request.args.get("status"))
    return jsonify([{**_serialize(o), "cliente_nome": o.cliente_nome} for o in rows])


@bp.route("/pedidos/<int:order_id>")
@token_required
def order_detail(order_id):
    try:
        order = services().orders.get(order_id)
    except NotFound as exc:
        return jsonify(erro=str(exc)), 404
    return jsonify({**_serialize(order), "cliente": _serialize(order.cliente)})


@bp.route("/pedidos", methods=["POST"])
@token_required
def order_create():
    data = request.get_json(silent=True) or {}
    try:
        order = services().orders.create(data.get("cliente_id"), data.get("moeda"), data.get("itens") or [],
                                         data.get("observacoes", ""), g.api_user.id)
    except ValidationError as exc:
        return jsonify(erro=str(exc), campos=exc.errors), 400
    except BusinessRuleError as exc:
        return jsonify(erro=str(exc)), 409
    return jsonify(_serialize(order)), 201
