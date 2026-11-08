class ServiceError(Exception):
    """Erro de regra de negócio com mensagem amigável."""


class ValidationError(ServiceError):
    def __init__(self, errors, message="Verifique os campos destacados."):
        self.errors = errors
        super().__init__(message)


class BusinessRuleError(ServiceError):
    pass


class NotFound(ServiceError):
    pass
