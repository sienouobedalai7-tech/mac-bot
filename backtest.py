"""
MAC Bot - Backtest de la stratégie sur données historiques réelles (Twelve Data)

Réutilise DIRECTEMENT strategy.py, indicators.py, risk_management.py - pas de
réimplémentation parallèle. Simule chaque signal bougie par bougie jusqu'à
SL, TP, ou expiration day-trading, pour donner un vrai résultat chiffré.

LANCEMENT :
    pip install -r requirements.txt
    python3 backtest.py

RÉSULTAT : rapport texte (nombre de trades, win rate, profit factor, détail
par actif ET par stratégie interne) affiché en console et sauvegardé dans
data/rapport_backtest.txt

LIMITES HONNÊTES : pas de simulation de spread/slippage ; un résultat positif
sur le passé ne garantit jamais une performance future.
"""

from __future__ import annotations
import time
import logging
from dataclasses import dataclass
from typing import Optional
import numpy as np
import pandas as pd

import config
import strategy
import position_manager
import data_fetcher

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("macbot.backtest")

# Nombre de bougies M15 max qu'une position reste ouverte avant expiration
# forcée (cohérent avec config.MAX_POSITION_HOURS, 1h = 4 bougies M15).
DUREE_MAX_BOUGIES = int(config.MAX_POSITION_HOURS * 4)

# Pas d'avancement entre deux vérifications de signal (voir backtester_actif) :
# on ne réanalyse pas à chaque bougie, mais tous les N, pour rester représentatif
# d'un cron qui tourne toutes les 10 min sur du M15 (une nouvelle bougie M15 ne se
# forme que toutes les 15 min de toute façon).
PAS_VERIFICATION = 1


@dataclass
class TradeSimule:
    symbol: str
    strategie: str
    direction: str
    prix_entree: float
    resultat: str  # "TP", "SL", "EXPIRE"
    pips_resultat: float
    bougies_tenues: int


def _simuler_issue_trade(df: pd.DataFrame, index_entree: int, niveaux, asset_type: str,
                          symbol: str) -> TradeSimule:
    """
    Simule le suivi d'un trade bougie par bougie après son entrée. En cas de
    bougie touchant SL et TP à la fois (mèche large), on suppose le pire cas
    (SL en premier) par prudence, faute de données tick-by-tick pour trancher.
    """
    direction = niveaux.direction
    fin_recherche = min(index_entree + 1 + DUREE_MAX_BOUGIES, len(df))

    for i in range(index_entree + 1, fin_recherche):
        bougie = df.iloc[i]
        haut, bas = bougie["High"], bougie["Low"]

        if direction == "ACHAT":
            sl_touche = bas <= niveaux.stop_loss
            tp_touche = haut >= niveaux.take_profit
        else:
            sl_touche = haut >= niveaux.stop_loss
            tp_touche = bas <= niveaux.take_profit

        if sl_touche:
            return TradeSimule(symbol, niveaux.direction, direction, niveaux.prix_entree,
                                "SL", -niveaux.pips_risque, i - index_entree)
        if tp_touche:
            return TradeSimule(symbol, niveaux.direction, direction, niveaux.prix_entree,
                                "TP", niveaux.pips_recompense, i - index_entree)

    prix_final = df.iloc[fin_recherche - 1]["Close"]
    import risk_management
    pips_flottants = risk_management.calculer_pips(niveaux.prix_entree, prix_final, asset_type, symbol)
    if direction == "VENTE":
        pips_flottants = -pips_flottants
    return TradeSimule(symbol, niveaux.direction, direction, niveaux.prix_entree,
                        "EXPIRE", pips_flottants, fin_recherche - 1 - index_entree)


def backtester_actif(nom_actif: str, infos: dict) -> list[TradeSimule]:
    """Backteste un actif sur tout l'historique disponible (jusqu'à 1000 bougies M15)."""
    symbol = infos["symbol"]
    trades: list[TradeSimule] = []

    try:
        df = data_fetcher.recuperer_bougies(
            symbol, config.TIMEFRAME, config.CANDLES_REQUESTED, config.MIN_CANDLES_REQUIRED
        )
    except (data_fetcher.DonneesInsuffisantesError, data_fetcher.ToutesLesClesEpuiseesError) as e:
        print(f"  [ignoré] {nom_actif}: {e}")
        return trades

    index_derniere_position_fermee = config.MIN_CANDLES_REQUIRED

    for i in range(config.MIN_CANDLES_REQUIRED, len(df), PAS_VERIFICATION):
        if i <= index_derniere_position_fermee:
            continue  # une position est déjà "ouverte" jusqu'à cet index dans la simulation

        df_visible = df.iloc[:i + 1]  # uniquement les bougies déjà "connues" à cet instant

        try:
            signal = strategy.analyser_actif(symbol, infos["type"], df_visible)
        except Exception as e:  # noqa: BLE001 - une erreur ponctuelle ne doit jamais arrêter tout le backtest
            print(f"  [erreur analyse] {nom_actif} à l'index {i}: {e}")
            continue

        if signal is None:
            continue

        trade = _simuler_issue_trade(df, i, signal.niveaux, infos["type"], symbol)
        trade.strategie = signal.strategie
        trades.append(trade)
        index_derniere_position_fermee = i + trade.bougies_tenues

    return trades


def generer_rapport(tous_les_trades: list[TradeSimule]) -> str:
    lignes = ["=" * 70, "MAC BOT — RAPPORT DE BACKTEST", "=" * 70, ""]

    n_total = len(tous_les_trades)
    if n_total == 0:
        lignes.append("Aucun trade généré sur la période testée.")
        return "\n".join(lignes)

    gagnants = [t for t in tous_les_trades if t.pips_resultat > 0]
    perdants = [t for t in tous_les_trades if t.pips_resultat <= 0]
    win_rate = len(gagnants) / n_total * 100
    gain_total = sum(t.pips_resultat for t in gagnants)
    perte_totale = abs(sum(t.pips_resultat for t in perdants))
    profit_factor = (gain_total / perte_totale) if perte_totale > 0 else float("inf")
    pips_net = sum(t.pips_resultat for t in tous_les_trades)

    lignes.append(f"Nombre total de trades : {n_total}")
    lignes.append(f"Trades gagnants        : {len(gagnants)} ({win_rate:.1f}%)")
    lignes.append(f"Trades perdants        : {len(perdants)} ({100 - win_rate:.1f}%)")
    lignes.append(f"Profit factor          : {profit_factor:.2f}" +
                   ("  (>1.0 = rentable sur cette période, <1.0 = perdant)" if profit_factor != float('inf') else ""))
    lignes.append(f"Pips/USD nets cumulés   : {pips_net:+.1f}")
    lignes.append("")

    lignes.append("Répartition des issues :")
    repartition: dict[str, int] = {}
    for t in tous_les_trades:
        repartition[t.resultat] = repartition.get(t.resultat, 0) + 1
    for issue, count in sorted(repartition.items()):
        lignes.append(f"  {issue:8s} : {count} ({count/n_total*100:.1f}%)")
    lignes.append("")

    lignes.append("-" * 70)
    lignes.append("Détail par stratégie interne :")
    lignes.append("-" * 70)
    par_strategie: dict[str, list[TradeSimule]] = {}
    for t in tous_les_trades:
        par_strategie.setdefault(t.strategie, []).append(t)
    for strat, trades_strat in sorted(par_strategie.items()):
        n = len(trades_strat)
        g = sum(1 for t in trades_strat if t.pips_resultat > 0)
        pips = sum(t.pips_resultat for t in trades_strat)
        lignes.append(f"  {strat:22s} : {n:3d} trades | {g}/{n} gagnants | {pips:+.1f} pips")
    lignes.append("")

    lignes.append("-" * 70)
    lignes.append("Détail par actif :")
    lignes.append("-" * 70)
    par_actif: dict[str, list[TradeSimule]] = {}
    for t in tous_les_trades:
        par_actif.setdefault(t.symbol, []).append(t)
    for symbol, trades_actif in sorted(par_actif.items()):
        n = len(trades_actif)
        g = sum(1 for t in trades_actif if t.pips_resultat > 0)
        pips = sum(t.pips_resultat for t in trades_actif)
        lignes.append(f"  {symbol:12s} : {n:3d} trades | {g}/{n} gagnants | {pips:+.1f} pips")

    lignes += [
        "", "=" * 70, "RAPPEL IMPORTANT :",
        "Ce backtest ne simule ni le spread ni le slippage (l'exécution réelle",
        "serait légèrement moins favorable). Un résultat positif ici ne garantit",
        "PAS une performance future, il décrit seulement le passé récent testé.",
        "=" * 70,
    ]
    return "\n".join(lignes)


def main():
    print(f"Démarrage du backtest sur {len(config.ASSETS)} actifs...")
    print("(Peut prendre plusieurs minutes selon la disponibilité des 4 clés Twelve Data.)\n")

    tous_les_trades: list[TradeSimule] = []

    for i, (nom_actif, infos) in enumerate(config.ASSETS.items(), 1):
        print(f"[{i}/{len(config.ASSETS)}] Backtest en cours : {nom_actif} ({infos['symbol']})...")
        trades = backtester_actif(nom_actif, infos)
        print(f"  -> {len(trades)} trade(s) généré(s)")
        tous_les_trades.extend(trades)

    rapport = generer_rapport(tous_les_trades)
    print("\n" + rapport)

    import os
    os.makedirs("data", exist_ok=True)
    with open("data/rapport_backtest.txt", "w", encoding="utf-8") as f:
        f.write(rapport)
    print("\nRapport sauvegardé dans : data/rapport_backtest.txt")


if __name__ == "__main__":
    main()
