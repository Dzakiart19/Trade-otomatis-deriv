"""
=============================================================
TRADING SYMBOLS CONFIGURATION
=============================================================
Konfigurasi semua trading pair yang didukung oleh bot.
Setiap symbol memiliki setting khusus untuk durasi dan stake.
=============================================================
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class SymbolConfig:
    """Konfigurasi untuk satu trading symbol"""
    symbol: str
    name: str
    min_stake: float
    min_duration: int
    max_duration: int
    duration_unit: str
    supports_ticks: bool
    supports_minutes: bool
    supports_days: bool
    category: str
    description: str


SUPPORTED_SYMBOLS: dict[str, SymbolConfig] = {
    "R_100": SymbolConfig(
        symbol="R_100",
        name="Volatility 100 Index",
        min_stake=0.50,
        min_duration=5,
        max_duration=10,
        duration_unit="t",
        supports_ticks=True,
        supports_minutes=True,
        supports_days=False,
        category="Synthetic",
        description="Default - Ideal untuk short-term trading"
    ),
    "R_75": SymbolConfig(
        symbol="R_75",
        name="Volatility 75 Index",
        min_stake=0.50,
        min_duration=5,
        max_duration=10,
        duration_unit="t",
        supports_ticks=True,
        supports_minutes=True,
        supports_days=False,
        category="Synthetic",
        description="Medium volatility - short-term trading"
    ),
    "R_50": SymbolConfig(
        symbol="R_50",
        name="Volatility 50 Index",
        min_stake=0.50,
        min_duration=5,
        max_duration=10,
        duration_unit="t",
        supports_ticks=True,
        supports_minutes=True,
        supports_days=False,
        category="Synthetic",
        description="Lower volatility - short-term trading"
    ),
    "R_25": SymbolConfig(
        symbol="R_25",
        name="Volatility 25 Index",
        min_stake=0.50,
        min_duration=5,
        max_duration=10,
        duration_unit="t",
        supports_ticks=True,
        supports_minutes=True,
        supports_days=False,
        category="Synthetic",
        description="Low volatility - more stable"
    ),
    "R_10": SymbolConfig(
        symbol="R_10",
        name="Volatility 10 Index",
        min_stake=0.50,
        min_duration=5,
        max_duration=10,
        duration_unit="t",
        supports_ticks=True,
        supports_minutes=True,
        supports_days=False,
        category="Synthetic",
        description="Lowest volatility - very stable"
    ),
    "1HZ100V": SymbolConfig(
        symbol="1HZ100V",
        name="Volatility 100 (1s) Index",
        min_stake=0.50,
        min_duration=5,
        max_duration=10,
        duration_unit="t",
        supports_ticks=True,
        supports_minutes=True,
        supports_days=False,
        category="Synthetic",
        description="1 second ticks - very fast"
    ),
    "1HZ75V": SymbolConfig(
        symbol="1HZ75V",
        name="Volatility 75 (1s) Index",
        min_stake=0.50,
        min_duration=5,
        max_duration=10,
        duration_unit="t",
        supports_ticks=True,
        supports_minutes=True,
        supports_days=False,
        category="Synthetic",
        description="1 second ticks - fast"
    ),
    "1HZ50V": SymbolConfig(
        symbol="1HZ50V",
        name="Volatility 50 (1s) Index",
        min_stake=0.50,
        min_duration=5,
        max_duration=10,
        duration_unit="t",
        supports_ticks=True,
        supports_minutes=True,
        supports_days=False,
        category="Synthetic",
        description="1 second ticks - medium"
    ),
    "frxXAUUSD": SymbolConfig(
        symbol="frxXAUUSD",
        name="Gold/USD (XAU/USD)",
        min_stake=0.50,
        min_duration=1,
        max_duration=365,
        duration_unit="d",
        supports_ticks=False,
        supports_minutes=False,
        supports_days=True,
        category="Commodities",
        description="HANYA durasi HARIAN - min 1 hari!"
    ),
}

DEFAULT_SYMBOL = "R_100"
MIN_STAKE_GLOBAL = 0.50


def get_symbol_config(symbol: str) -> Optional[SymbolConfig]:
    """Dapatkan konfigurasi untuk symbol tertentu"""
    return SUPPORTED_SYMBOLS.get(symbol)


def get_symbols_by_category(category: str) -> List[SymbolConfig]:
    """Dapatkan semua symbol dalam kategori tertentu"""
    return [s for s in SUPPORTED_SYMBOLS.values() if s.category == category]


def get_short_term_symbols() -> List[SymbolConfig]:
    """Dapatkan symbol yang mendukung short-term trading (ticks)"""
    return [s for s in SUPPORTED_SYMBOLS.values() if s.supports_ticks]


def get_long_term_symbols() -> List[SymbolConfig]:
    """Dapatkan symbol yang hanya mendukung long-term trading (days)"""
    return [s for s in SUPPORTED_SYMBOLS.values() if s.supports_days and not s.supports_ticks]


def validate_duration_for_symbol(symbol: str, duration: int, duration_unit: str) -> tuple[bool, str]:
    """
    Validasi apakah durasi cocok untuk symbol tertentu.
    
    Args:
        symbol: Trading symbol
        duration: Nilai durasi
        duration_unit: Unit durasi (t=ticks, m=minutes, s=seconds, d=days)
        
    Returns:
        Tuple (is_valid, error_message)
    """
    config = get_symbol_config(symbol)
    if not config:
        return False, f"Symbol '{symbol}' tidak dikenal"
    
    if duration_unit == "t" and not config.supports_ticks:
        return False, f"{config.name} tidak mendukung durasi ticks. Gunakan durasi harian (d)."
    
    if duration_unit in ["m", "s"] and not config.supports_minutes:
        return False, f"{config.name} tidak mendukung durasi menit/detik. Gunakan durasi harian (d)."
    
    if duration_unit == "d" and not config.supports_days:
        return False, f"{config.name} tidak mendukung durasi harian."
    
    return True, ""


def get_symbol_list_text() -> str:
    """Generate text list semua symbol untuk display di Telegram"""
    lines = ["📊 **TRADING PAIRS TERSEDIA**\n"]
    
    lines.append("**Synthetic (Short-term):**")
    for sym in get_short_term_symbols():
        lines.append(f"• `{sym.symbol}` - {sym.name}")
    
    lines.append("\n**Commodities (Long-term):**")
    for sym in get_long_term_symbols():
        lines.append(f"• `{sym.symbol}` - {sym.name} ⚠️ HARIAN SAJA")
    
    return "\n".join(lines)
