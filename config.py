"""
MAC Bot (version GitHub Actions) - Configuration centrale

Adapté depuis la version originale (pensée pour Render + webhook Telegram) :
retrait de CRON_SECRET, DATABASE_PATH, PASSWORD_CANAUX_TELEGRAM, CANAL_SIGNAUX_URL
(tous liés au serveur web/webhook, qu'on ne peut pas faire tourner sur GitHub
Actions - voir le README pour le détail de ce choix). Ajout de STATE_FILE et
HISTORY_FILE (persistance JSON, comme MR EMA) à la place de SQLite.

Toutes les valeurs modifiables sont ici. Rien n'est en dur ailleurs dans le code.
"""

import os

# ============================================================
# TELEGRAM
# ============================================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")  # canal des signaux

# ============================================================
# TWELVE DATA - rotation de 4 clés API
# ============================================================
# Chaque clé gratuite : 8 appels/minute, 800 appels/jour.
# Avec rotation sur 4 clés : jusqu'à 3200 appels/jour cumulés.
TWELVE_DATA_API_KEYS = [
    os.environ.get("TWELVE_DATA_KEY_1", ""),
    os.environ.get("TWELVE_DATA_KEY_2", ""),
    os.environ.get("TWELVE_DATA_KEY_3", ""),
    os.environ.get("TWELVE_DATA_KEY_4", ""),
]
TWELVE_DATA_API_KEYS = [k for k in TWELVE_DATA_API_KEYS if k]

TWELVE_DATA_BASE_URL = "https://api.twelvedata.com/time_series"
TWELVE_DATA_MAX_CALLS_PER_MINUTE_PER_KEY = 8
TWELVE_DATA_MIN_DELAY_BETWEEN_CALLS_SECONDS = 8

# ============================================================
# ACTIFS SUIVIS (mêmes 24 que MR EMA, cohérence entre les deux projets)
# ============================================================
ASSETS = {
    "XAUUSD": {"symbol": "XAU/USD", "type": "metal", "display": "XAU/USD (Or)"},
    "XAGUSD": {"symbol": "XAG/USD", "type": "metal", "display": "XAG/USD (Argent)"},
    "BTCUSD": {"symbol": "BTC/USD", "type": "crypto", "display": "BTC/USD"},
    "GBPUSD": {"symbol": "GBP/USD", "type": "forex", "display": "GBP/USD"},
    "EURUSD": {"symbol": "EUR/USD", "type": "forex", "display": "EUR/USD"},
    "USDJPY": {"symbol": "USD/JPY", "type": "forex", "display": "USD/JPY"},
    "USDCHF": {"symbol": "USD/CHF", "type": "forex", "display": "USD/CHF"},
    "AUDUSD": {"symbol": "AUD/USD", "type": "forex", "display": "AUD/USD"},
    "USDCAD": {"symbol": "USD/CAD", "type": "forex", "display": "USD/CAD"},
    "NZDUSD": {"symbol": "NZD/USD", "type": "forex", "display": "NZD/USD"},
    "EURJPY": {"symbol": "EUR/JPY", "type": "forex", "display": "EUR/JPY"},
    "GBPJPY": {"symbol": "GBP/JPY", "type": "forex", "display": "GBP/JPY"},
    "EURGBP": {"symbol": "EUR/GBP", "type": "forex", "display": "EUR/GBP"},
    "AUDJPY": {"symbol": "AUD/JPY", "type": "forex", "display": "AUD/JPY"},
    "EURAUD": {"symbol": "EUR/AUD", "type": "forex", "display": "EUR/AUD"},
    "GBPAUD": {"symbol": "GBP/AUD", "type": "forex", "display": "GBP/AUD"},
    "GBPCAD": {"symbol": "GBP/CAD", "type": "forex", "display": "GBP/CAD"},
    "EURCAD": {"symbol": "EUR/CAD", "type": "forex", "display": "EUR/CAD"},
    "AUDCAD": {"symbol": "AUD/CAD", "type": "forex", "display": "AUD/CAD"},
    "AUDNZD": {"symbol": "AUD/NZD", "type": "forex", "display": "AUD/NZD"},
    "CADJPY": {"symbol": "CAD/JPY", "type": "forex", "display": "CAD/JPY"},
    "CHFJPY": {"symbol": "CHF/JPY", "type": "forex", "display": "CHF/JPY"},
    "NZDJPY": {"symbol": "NZD/JPY", "type": "forex", "display": "NZD/JPY"},
    "EURCHF": {"symbol": "EUR/CHF", "type": "forex", "display": "EUR/CHF"},
}

# ============================================================
# TIMEFRAME - un seul, contrainte du plan gratuit Twelve Data
# ============================================================
TIMEFRAME = "15min"
CANDLES_REQUESTED = 1000
MIN_CANDLES_REQUIRED = 210

# ============================================================
# INDICATEURS
# ============================================================
EMA_FAST = 50
EMA_SLOW = 200

TDI_RSI_PERIOD = 13
TDI_RSI_PRICE_LINE = 2
TDI_TRADE_SIGNAL_LINE = 7
TDI_VOLATILITY_BAND = 34

ATR_PERIOD = 14

# ============================================================
# STRATÉGIE 1 - Retest EMA50 + confirmation TDI
# ============================================================
STRAT1_ECART_MIN_TENDANCE = 0.0006
STRAT1_TOLERANCE_CONTACT_EMA50 = 0.0012
STRAT1_ZONE_RSI_REBOND = 6

# ============================================================
# STRATÉGIE 2 - Croisement EMA50/EMA200 + rejection
# ============================================================
STRAT2_FENETRE_CROISEMENT = 30
STRAT2_FENETRE_RETEST = 15
STRAT2_RATIO_MECHE_MIN = 0.5

# ============================================================
# RISK MANAGEMENT (règle non-négociable, commune aux deux stratégies)
# ============================================================
MIN_RISK_REWARD = 1.50
MAX_RISK_REWARD = 3.50
MARGE_DERRIERE_MECHE_ATR = 0.15
FENETRE_SWING_TP = 40

# ============================================================
# HORAIRES (Burkina Faso = UTC+0 toute l'année)
# ============================================================
TIMEZONE_BF = "Africa/Ouagadougou"
MORNING_HOUR_BF = 7
EVENING_HOUR_BF = 20

# ============================================================
# STOCKAGE D'ÉTAT (JSON committé automatiquement par le workflow GitHub Actions,
# remplace SQLite - voir position_manager.py)
# ============================================================
STATE_FILE = "data/positions_ouvertes.json"
HISTORY_FILE = "data/historique_cloture.json"
MARQUEURS_FILE = "data/marqueurs_messages.json"

# ============================================================
# SUPPORT
# ============================================================
SUPPORT_TELEGRAM_URL = "https://t.me/Sienouobedalai226"

# ============================================================
# DAY TRADING - durée de vie max d'une position
# ============================================================
MAX_POSITION_HOURS = 18

# ============================================================
# LIMITE ANTI-SPAM (cohérence avec MR EMA)
# ============================================================
MAX_SIGNAUX_PAR_CYCLE = 3
