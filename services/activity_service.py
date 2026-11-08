class ActivityService:
    def __init__(self, repo):
        self.repo = repo

    def log(self, user_id, acao, entidade, entidade_id, descricao):
        return self.repo.insert("atividades", {
            "usuario_id": user_id, "acao": acao, "entidade": entidade,
            "entidade_id": entidade_id, "descricao": descricao[:255],
        })

    def recent(self, limit=8):
        rows = self.repo.list("atividades", order_by="criado_em", descending=True, limit=limit)
        users = {u["id"]: u for u in self.repo.list("usuarios")}
        for row in rows:
            user = users.get(row["usuario_id"])
            row["usuario_nome"] = user["nome"] if user else "Sistema"
        return rows
