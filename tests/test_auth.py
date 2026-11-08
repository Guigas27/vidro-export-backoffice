import json

from tests.conftest import post


def login(client, username="admin", password="senha1234"):
    return post(client, "/login", {"username": username, "password": password})


def test_app_starts_and_redirects_to_setup(client):
    response = client.get("/")
    assert response.status_code == 302 and "/setup" in response.location


def test_setup_creates_admin_once(admin_client, app):
    user = app.extensions["services"].repo.find_one("usuarios", username="admin")
    assert user["perfil"] == "admin"
    assert user["password_hash"] != "senha1234" and "senha1234" not in user["password_hash"]
    assert admin_client.get("/setup").status_code == 302


def test_passwords_never_stored_in_plain_text(admin_client, app):
    data_dir = app.config["JSON_DATA_DIR"]
    content = (data_dir / "usuarios.json").read_text(encoding="utf-8")
    assert "senha1234" not in content


def test_login_logout(admin_client):
    post(admin_client, "/logout")
    assert admin_client.get("/").status_code == 302
    response = login(admin_client)
    assert response.status_code == 302
    assert admin_client.get("/").status_code == 200


def test_invalid_credentials(admin_client):
    post(admin_client, "/logout")
    response = login(admin_client, password="errada123")
    assert response.status_code == 200
    assert "Usuário ou senha inválidos" in response.get_data(as_text=True)
    assert admin_client.get("/produtos/").status_code == 302


def test_empty_login_fields_validated(admin_client):
    post(admin_client, "/logout")
    response = post(admin_client, "/login", {"username": "", "password": ""})
    assert response.status_code == 400


def test_protected_routes_require_login(client, admin_client):
    post(admin_client, "/logout")
    for url in ["/", "/produtos/", "/clientes/", "/pedidos/", "/pedidos/novo", "/usuarios/", "/cambio/", "/configuracoes/"]:
        response = admin_client.get(url)
        assert response.status_code == 302 and "/login" in response.location, url


def test_csrf_required(admin_client):
    response = admin_client.post("/produtos/novo", data={"codigo": "X"})
    assert response.status_code == 400


def test_open_redirect_blocked(admin_client):
    post(admin_client, "/logout")
    response = post(admin_client, "/login?next=https://evil.example", {"username": "admin", "password": "senha1234"})
    assert response.location.endswith("/")


def test_operator_cannot_manage_users(admin_client):
    response = post(admin_client, "/usuarios/novo", {"nome": "Operador", "username": "oper", "email": "op@x.com",
                                                      "perfil": "operador", "ativo": "on",
                                                      "password": "senha1234", "password_confirm": "senha1234"})
    assert response.status_code == 302
    post(admin_client, "/logout")
    login(admin_client, "oper")
    assert admin_client.get("/produtos/").status_code == 200
    assert admin_client.get("/usuarios/").status_code == 403
    assert admin_client.get("/configuracoes/").status_code == 403


def test_inactive_user_cannot_login(admin_client, app):
    svc = app.extensions["services"]
    post(admin_client, "/usuarios/novo", {"nome": "Inativo", "username": "inativo", "email": "in@x.com",
                                          "perfil": "operador", "password": "senha1234", "password_confirm": "senha1234"})
    assert svc.repo.find_one("usuarios", username="inativo")["ativo"] is False
    post(admin_client, "/logout")
    assert login(admin_client, "inativo").status_code == 200


def test_cannot_delete_self_or_last_admin(admin_client, app):
    admin = app.extensions["services"].repo.find_one("usuarios", username="admin")
    post(admin_client, f"/usuarios/{admin['id']}/excluir")
    assert app.extensions["services"].repo.get("usuarios", admin["id"]) is not None


def test_jwt_api(admin_client):
    response = admin_client.post("/api/token", json={"username": "admin", "password": "senha1234"})
    token = response.get_json()["token"]
    assert admin_client.get("/api/produtos").status_code == 401
    assert admin_client.get("/api/produtos", headers={"Authorization": "Bearer invalido"}).status_code == 401
    ok = admin_client.get("/api/produtos", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200 and ok.get_json() == []
    assert admin_client.post("/api/token", json={"username": "admin", "password": "x"}).status_code == 401


SIGNUP = {"nome": "Maria Souza", "username": "maria", "email": "maria@x.com",
          "password": "senha1234", "password_confirm": "senha1234"}


def test_signup_creates_active_operator_and_logs_in(admin_client, app):
    post(admin_client, "/logout")
    assert "Criar conta" in admin_client.get("/login").get_data(as_text=True)
    response = post(admin_client, "/cadastro", {**SIGNUP, "perfil": "admin", "ativo": ""})
    assert response.status_code == 302 and response.location.endswith("/")
    user = app.extensions["services"].repo.find_one("usuarios", username="maria")
    assert user["perfil"] == "operador" and user["ativo"] is True
    assert "senha1234" not in user["password_hash"]
    assert admin_client.get("/pedidos/").status_code == 200
    assert admin_client.get("/usuarios/").status_code == 403
    post(admin_client, "/logout")
    assert login(admin_client, "maria").status_code == 302


def test_signup_validation_and_duplicates(admin_client):
    post(admin_client, "/logout")
    response = post(admin_client, "/cadastro", {**SIGNUP, "username": "admin"})
    assert response.status_code == 400 and "já está em uso" in response.get_data(as_text=True)
    response = post(admin_client, "/cadastro", {**SIGNUP, "password_confirm": "outra1234"})
    assert response.status_code == 400
    response = post(admin_client, "/cadastro", {**SIGNUP, "password": "curta", "password_confirm": "curta"})
    assert response.status_code == 400


def test_signup_before_setup_redirects(client):
    response = client.get("/cadastro")
    assert response.status_code == 302 and "/setup" in response.location


def test_signup_can_be_disabled(admin_client, app):
    app.config["ALLOW_SIGNUP"] = False
    post(admin_client, "/logout")
    assert admin_client.get("/cadastro").status_code == 404
    assert "Criar conta" not in admin_client.get("/login").get_data(as_text=True)
