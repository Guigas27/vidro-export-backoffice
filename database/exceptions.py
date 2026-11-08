class RepositoryError(Exception):
    """Erro genérico da camada de armazenamento."""


class DatabaseConnectionError(RepositoryError):
    """Falha ao conectar/abrir o armazenamento configurado."""


class NotFoundError(RepositoryError):
    pass


class DuplicateError(RepositoryError):
    def __init__(self, table, field, message=None):
        self.table = table
        self.field = field
        super().__init__(message or f"Já existe um registro em '{table}' com o mesmo valor de '{field}'.")


class IntegrityViolationError(RepositoryError):
    """Violação de integridade referencial (chave estrangeira)."""


class StorageCorruptedError(RepositoryError):
    pass
