"""Cotações de câmbio via API pública Frankfurter (https://frankfurter.dev).

Se a API estiver indisponível, é lançada ``ExchangeUnavailableError``: o
sistema nunca inventa ou estima taxas.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

SUPPORTED_CURRENCIES = {
    "USD": "Dólar americano", "EUR": "Euro", "BRL": "Real brasileiro",
    "GBP": "Libra esterlina", "CNY": "Yuan chinês", "JPY": "Iene japonês",
    "CAD": "Dólar canadense", "AUD": "Dólar australiano", "CHF": "Franco suíço",
    "MXN": "Peso mexicano", "ZAR": "Rand sul-africano", "INR": "Rupia indiana",
    "KRW": "Won sul-coreano", "SEK": "Coroa sueca", "NOK": "Coroa norueguesa",
    "DKK": "Coroa dinamarquesa", "PLN": "Zloty polonês", "TRY": "Lira turca",
    "NZD": "Dólar neozelandês", "SGD": "Dólar de Singapura", "HKD": "Dólar de Hong Kong",
}


class ExchangeUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class ExchangeRate:
    base: str
    target: str
    rate: Decimal
    date: date
    source: str


def _default_http_get(url, timeout):
    request = urllib.request.Request(url, headers={"User-Agent": "VidroExportBackoffice/1.0", "Accept": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8")


class ExchangeService:
    def __init__(self, base_url="https://api.frankfurter.dev/v1", timeout=8, cache_seconds=1800, http_get=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache_seconds = cache_seconds
        self._http_get = http_get or _default_http_get
        self._cache = {}
        self._lock = threading.Lock()

    @staticmethod
    def _check(currency):
        currency = (currency or "").upper()
        if currency not in SUPPORTED_CURRENCIES:
            raise ValueError(f"Moeda não suportada: {currency}")
        return currency

    def _fetch(self, base, targets):
        query = urllib.parse.urlencode({"base": base, "symbols": ",".join(targets)})
        url = f"{self.base_url}/latest?{query}"
        try:
            payload = json.loads(self._http_get(url, self.timeout), parse_float=Decimal, parse_int=Decimal)
            rates = payload["rates"]
            quote_date = date.fromisoformat(payload["date"])
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, TypeError) as exc:
            raise ExchangeUnavailableError(
                "Não foi possível consultar as taxas de câmbio na API Frankfurter. "
                "Verifique a conexão com a internet e tente novamente. "
                "Nenhuma taxa foi estimada."
            ) from exc
        result = {}
        for target in targets:
            if target not in rates:
                raise ExchangeUnavailableError(f"A API Frankfurter não retornou a cotação {base}→{target}.")
            result[target] = ExchangeRate(base, target, Decimal(str(rates[target])), quote_date, "Frankfurter")
        return result

    def get_rate(self, base, target):
        base, target = self._check(base), self._check(target)
        if base == target:
            return ExchangeRate(base, target, Decimal("1"), date.today(), "mesma moeda")
        return self.get_rates(base, [target])[target]

    def get_rates(self, base, targets=None):
        base = self._check(base)
        targets = [self._check(t) for t in (targets or SUPPORTED_CURRENCIES) if t.upper() != base]
        now = time.monotonic()
        result, missing = {}, []
        with self._lock:
            for target in targets:
                cached = self._cache.get((base, target))
                if cached and now - cached[0] < self.cache_seconds:
                    result[target] = cached[1]
                else:
                    missing.append(target)
        if missing:
            fetched = self._fetch(base, missing)
            with self._lock:
                for target, rate in fetched.items():
                    self._cache[(base, target)] = (now, rate)
            result.update(fetched)
        return result

    def convert(self, amount, base, target):
        rate = self.get_rate(base, target)
        return (Decimal(str(amount)) * rate.rate).quantize(Decimal("0.01")), rate
