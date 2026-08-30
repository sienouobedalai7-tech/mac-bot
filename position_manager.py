"""
MAC Bot (version GitHub Actions) - Gestion des positions ouvertes

Remplace la version originale SQLite (database.py + position_manager.py) par
des fichiers JSON committés automatiquement par le workflow GitHub Actions,
exactement comme Sentinel et MR EMA. Raison du changement : SQLite sur Render
persistait sur le disque du service tant qu'il ne redémarrait pas, mais
GitHub Actions n'a AUCUN disque persistant entre deux runs - seul ce qui est
committé dans le repo Git survit d'un cycle à l'autre.

Le système de comptes utilisateurs (table `utilisateurs` de l'original) a été
retiré : ce mode ne fonctionne qu'avec le webhook Telegram (serveur qui reçoit
les inscriptions en temps réel), qu'on a retiré pour repasser sur GitHub
Actions (voir main.py et le README pour le détail de ce choix).
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

import config

logger_data_dir = os.path.dirname(config.STATE_FILE)


@dataclass
class Position:
    id: str
    symbol: str
    display: str
    asset_type: str
    strategie: str  # gardé en interne pour analyse, jamais montré dans les messages Telegram
    direction: str
    prix_entree: float
    stop_loss: float
    take_profit: float
    ratio_rr: float
    pips_risque: float
    ouverte_le: str
    statut: str = "OUVERTE"
    resultat_pips: Optional[float] = None
    fermee_le: Optional[str] = None


def _charger_json(chemin: str, defaut):
    if not os.path.exists(chemin):
        return defaut
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return defaut


def _sauvegarder_json(chemin: str, data) -> None:
    os.makedirs(os.path.dirname(chemin), exist_ok=True)
    tmp = chemin + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, chemin)


# ============================================================
# POSITIONS OUVERTES
# ============================================================

def charger_positions_ouvertes() -> list[Position]:
    data = _charger_json(config.STATE_FILE, [])
    return [Position(**p) for p in data]


def sauvegarder_positions_ouvertes(positions: list[Position]) -> None:
    _sauvegarder_json(config.STATE_FILE, [asdict(p) for p in positions])


def symbole_a_deja_une_position_ouverte(symbol: str, positions_ouvertes: list[Position]) -> bool:
    return any(p.symbol == symbol for p in positions_ouvertes)


def ouvrir_position(symbol: str, display: str, asset_type: str, signal) -> Position:
    maintenant = datetime.now(timezone.utc).isoformat()
    position_id = f"{symbol.replace('/', '')}_{maintenant}"

    return Position(
        id=position_id,
        symbol=symbol,
        display=display,
        asset_type=asset_type,
        strategie=signal.strategie,
        direction=signal.direction,
        prix_entree=signal.niveaux.prix_entree,
        stop_loss=signal.niveaux.stop_loss,
        take_profit=signal.niveaux.take_profit,
        ratio_rr=signal.niveaux.ratio_rr,
        pips_risque=signal.niveaux.pips_risque,
        ouverte_le=maintenant,
        statut="OUVERTE",
    )


def _niveau_touche(direction: str, prix_actuel: float, niveau: float, est_tp: bool) -> bool:
    if direction == "ACHAT":
        return prix_actuel >= niveau if est_tp else prix_actuel <= niveau
    else:
        return prix_actuel <= niveau if est_tp else prix_actuel >= niveau


def verifier_position(position: Position, prix_actuel: float) -> tuple[Optional[str], Optional[float]]:
    """Retourne (evenement, resultat_pips) où evenement est "TP_TOUCHE", "SL_TOUCHE", ou None."""
    if _niveau_touche(position.direction, prix_actuel, position.stop_loss, est_tp=False):
        return ("SL_TOUCHE", -position.pips_risque)

    if _niveau_touche(position.direction, prix_actuel, position.take_profit, est_tp=True):
        return ("TP_TOUCHE", position.ratio_rr * position.pips_risque)

    return (None, None)


def verifier_expiration_day_trading(position: Position) -> bool:
    ouverte = datetime.fromisoformat(position.ouverte_le)
    maintenant = datetime.now(timezone.utc)
    duree_heures = (maintenant - ouverte).total_seconds() / 3600
    return duree_heures >= config.MAX_POSITION_HOURS


# ============================================================
# HISTORIQUE
# ============================================================

def charger_historique() -> list[dict]:
    return _charger_json(config.HISTORY_FILE, [])


def ajouter_a_historique(position: Position, resultat_pips: Optional[float], statut_final: str) -> None:
    historique = charger_historique()
    entree = asdict(position)
    entree["resultat_pips"] = resultat_pips
    entree["statut_final"] = statut_final
    entree["fermee_le"] = datetime.now(timezone.utc).isoformat()
    historique.append(entree)
    _sauvegarder_json(config.HISTORY_FILE, historique)


def positions_fermees_aujourdhui() -> list[dict]:
    aujourdhui = datetime.now(timezone.utc).date().isoformat()
    historique = charger_historique()
    return [p for p in historique if p.get("fermee_le", "").startswith(aujourdhui)]


def cloturer_position(position: Position, resultat_pips: Optional[float], statut_final: str,
                       positions_ouvertes: list[Position]) -> list[Position]:
    """Déplace une position de la liste des ouvertes vers l'historique. Retourne la liste mise à jour."""
    ajouter_a_historique(position, resultat_pips, statut_final)
    return [p for p in positions_ouvertes if p.id != position.id]
