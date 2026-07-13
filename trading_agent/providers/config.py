"""Environment-gated provider configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from trading_agent.discord.env import load_project_env


def _csv_env(name: str, default: str) -> List[str]:
    raw = os.getenv(name, default).strip()
    if not raw:
        return []
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


@dataclass
class ProviderConfig:
    """Keys and selection order for multi-provider market data / brokerage."""

    # Preference lists (first available/configured wins for secondary paths)
    quote_providers: List[str] = field(
        default_factory=lambda: ["yfinance", "finnhub", "alpha_vantage", "twelve_data", "tiingo", "marketstack"]
    )
    news_providers: List[str] = field(
        default_factory=lambda: ["yfinance", "finnhub", "tiingo", "fmp"]
    )
    # API keys (empty = unavailable)
    finnhub_api_key: str = ""
    alpha_vantage_api_key: str = ""
    twelve_data_api_key: str = ""
    tiingo_api_key: str = ""
    marketstack_api_key: str = ""
    nasdaq_data_link_api_key: str = ""
    massive_api_key: str = ""  # also POLYGON_API_KEY
    fmp_api_key: str = ""
    # Brokerage
    alpaca_api_key: str = ""
    alpaca_secret_key: str = ""
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    tradier_access_token: str = ""
    tradier_account_id: str = ""
    tradier_base_url: str = "https://sandbox.tradier.com"
    # IBKR: only a flag — real socket client is optional advanced
    ibkr_enabled: bool = False

    @classmethod
    def from_env(cls) -> "ProviderConfig":
        load_project_env()
        massive = (
            os.getenv("MASSIVE_API_KEY", "").strip()
            or os.getenv("POLYGON_API_KEY", "").strip()
        )
        return cls(
            quote_providers=_csv_env(
                "TRADING_AGENT_QUOTE_PROVIDERS",
                "yfinance,finnhub,alpha_vantage,twelve_data,tiingo,marketstack",
            ),
            news_providers=_csv_env(
                "TRADING_AGENT_NEWS_PROVIDERS",
                "yfinance,finnhub,tiingo,fmp",
            ),
            finnhub_api_key=os.getenv("FINNHUB_API_KEY", "").strip(),
            alpha_vantage_api_key=os.getenv("ALPHA_VANTAGE_API_KEY", "").strip(),
            twelve_data_api_key=os.getenv("TWELVE_DATA_API_KEY", "").strip(),
            tiingo_api_key=os.getenv("TIINGO_API_KEY", "").strip(),
            marketstack_api_key=os.getenv("MARKETSTACK_API_KEY", "").strip(),
            nasdaq_data_link_api_key=os.getenv("NASDAQ_DATA_LINK_API_KEY", "").strip(),
            massive_api_key=massive,
            fmp_api_key=os.getenv("FMP_API_KEY", "").strip(),
            alpaca_api_key=os.getenv("ALPACA_API_KEY", "").strip(),
            alpaca_secret_key=os.getenv("ALPACA_SECRET_KEY", "").strip(),
            alpaca_base_url=os.getenv(
                "ALPACA_BASE_URL", "https://paper-api.alpaca.markets"
            ).strip(),
            tradier_access_token=os.getenv("TRADIER_ACCESS_TOKEN", "").strip(),
            tradier_account_id=os.getenv("TRADIER_ACCOUNT_ID", "").strip(),
            tradier_base_url=os.getenv(
                "TRADIER_BASE_URL", "https://sandbox.tradier.com"
            ).strip(),
            ibkr_enabled=os.getenv("IBKR_ENABLED", "").lower() in ("1", "true", "yes"),
        )

    def key_for(self, provider: str) -> str:
        p = provider.lower()
        return {
            "finnhub": self.finnhub_api_key,
            "alpha_vantage": self.alpha_vantage_api_key,
            "twelve_data": self.twelve_data_api_key,
            "tiingo": self.tiingo_api_key,
            "marketstack": self.marketstack_api_key,
            "nasdaq_data_link": self.nasdaq_data_link_api_key,
            "massive": self.massive_api_key,
            "polygon": self.massive_api_key,
            "fmp": self.fmp_api_key,
            "alpaca": self.alpaca_api_key if self.alpaca_secret_key else "",
            "tradier": self.tradier_access_token,
        }.get(p, "")

    def is_configured(self, provider: str) -> bool:
        p = provider.lower()
        if p == "yfinance":
            return True
        if p == "pandas_datareader":
            try:
                import pandas_datareader  # noqa: F401

                return True
            except ImportError:
                return False
        if p == "ibkr_tws":
            return self.ibkr_enabled
        if p == "alpaca":
            return bool(self.alpaca_api_key and self.alpaca_secret_key)
        if p == "tradier":
            return bool(self.tradier_access_token)
        return bool(self.key_for(p))
