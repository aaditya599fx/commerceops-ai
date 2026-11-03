from dataclasses import dataclass, field
from pathlib import Path
import os
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / '.env', override=True)

@dataclass
class Settings:
    mode: str = field(default_factory=lambda: os.getenv('APP_MODE', 'fixture'))
    database_url: str = field(default_factory=lambda: os.getenv('DATABASE_URL', 'sqlite:///./runtime/commerceops.db'))
    token: str = field(default_factory=lambda: os.getenv('APP_TOKEN', ''))
    base_url: str = field(default_factory=lambda: os.getenv('PUBLIC_BASE_URL', 'http://localhost:8000'))
    min_cart: float = field(default_factory=lambda: float(os.getenv('MIN_CART_VALUE', '25')))
    cooldown_hours: int = field(default_factory=lambda: int(os.getenv('RECOVERY_COOLDOWN_HOURS', '72')))
    high_spend: float = field(default_factory=lambda: float(os.getenv('HIGH_SPEND_THRESHOLD', '500')))
    high_spend_currency: str = field(default_factory=lambda: os.getenv('HIGH_SPEND_CURRENCY', 'USD'))
    external_writes_enabled: bool = field(default_factory=lambda: os.getenv('ENABLE_EXTERNAL_WRITES','false').lower()=='true')
    api_timeout: float = 12
    def __post_init__(self):
        if self.mode not in ('fixture', 'live'):
            raise ValueError('APP_MODE must be fixture or live')
        if len(self.token) < 24:
            raise ValueError('Set APP_TOKEN to a random secret of at least 24 characters')
