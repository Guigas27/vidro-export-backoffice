"""Camada de regras de negócio."""
from services.activity_service import ActivityService
from services.client_service import ClientService
from services.dashboard_service import DashboardService
from services.exchange_service import ExchangeService
from services.order_service import OrderService
from services.product_service import ProductService
from services.settings_service import SettingsService
from services.user_service import UserService


class ServiceContainer:
    """Instancia os serviços sobre o repositório configurado (JSON ou MySQL)."""

    def __init__(self, repo, exchange_service):
        self.repo = repo
        self.exchange = exchange_service
        self.activities = ActivityService(repo)
        self.settings = SettingsService(repo)
        self.users = UserService(repo, self.activities)
        self.products = ProductService(repo, self.activities)
        self.clients = ClientService(repo, self.activities)
        self.orders = OrderService(repo, self.exchange, self.settings, self.activities)
        self.dashboard = DashboardService(repo, self.activities)
