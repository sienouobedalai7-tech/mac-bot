"""
MAC Bot (version GitHub Actions) - Point d'entrée principal

Adapté depuis la version originale (serveur Flask permanent sur Render avec
endpoint /cron/<secret> + webhook Telegram) : ce fichier fait tout en un seul
passage (suivi des positions, analyse, messages programmés) puis se termine -
exactement le modèle qui a fonctionné pour Sentinel et MR EMA sur GitHub
Actions. Pas de webhook : les commandes interactives (/inscrire, /signaux
via clic, etc.) ne sont pas disponibles dans cette version (voir le README
pour le choix qui a mené à ce compromis).
"""

from __future__ import annotations
import os
import logging
from datetime import datetime, date
from zoneinfo import ZoneInfo

import config
import data_fetcher
import strategy
import position_manager
import telegram_sender
import chart_generator
import indicators

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("macbot.main")

DOSSIER_GRAPHIQUES_TEMP = "data/graphiques_temp"


def _heure_actuelle_burkina() -> datetime:
    return datetime.now(ZoneInfo(config.TIMEZONE_BF))


def _charger_marqueurs() -> dict:
    import json
    if not os.path.exists(config.MARQUEURS_FILE):
        return {}
    try:
        with open(config.MARQUEURS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _sauvegarder_marqueurs(marqueurs: dict) -> None:
    import json
    os.makedirs(os.path.dirname(config.MARQUEURS_FILE), exist_ok=True)
    with open(config.MARQUEURS_FILE, "w", encoding="utf-8") as f:
        json.dump(marqueurs, f, ensure_ascii=False, indent=2)


def _deja_envoye_aujourdhui(nom_evenement: str, marqueurs: dict) -> bool:
    aujourdhui = date.today().isoformat()
    return marqueurs.get(nom_evenement) == aujourdhui


def _marquer_envoye(nom_evenement: str, marqueurs: dict) -> None:
    marqueurs[nom_evenement] = date.today().isoformat()


def _traiter_messages_programmes(marqueurs: dict) -> None:
    maintenant_bf = _heure_actuelle_burkina()

    if maintenant_bf.hour == config.MORNING_HOUR_BF and not _deja_envoye_aujourdhui("matin", marqueurs):
        logger.info("Envoi du message du matin")
        telegram_sender.envoyer_message(telegram_sender.formater_message_matin())
        _marquer_envoye("matin", marqueurs)

    if maintenant_bf.hour == config.EVENING_HOUR_BF and not _deja_envoye_aujourdhui("soir", marqueurs):
        logger.info("Envoi du bilan du soir")
        fermees = position_manager.positions_fermees_aujourdhui()
        ouvertes = position_manager.charger_positions_ouvertes()
        telegram_sender.envoyer_message(telegram_sender.formater_bilan_soir(fermees, ouvertes))
        _marquer_envoye("soir", marqueurs)


def _suivre_positions_ouvertes(positions: list) -> list:
    """Vérifie chaque position ouverte (SL/TP touché, expiration). Retourne la liste mise à jour."""
    positions_restantes = list(positions)

    for position in list(positions_restantes):
        try:
            prix = data_fetcher.prix_actuel(position.symbol)
        except (data_fetcher.DonneesInsuffisantesError, data_fetcher.ToutesLesClesEpuiseesError) as e:
            logger.warning(f"Impossible de vérifier {position.symbol}: {e}")
            continue

        if position_manager.verifier_expiration_day_trading(position):
            resultat = round((prix - position.prix_entree) if position.direction == "ACHAT"
                              else (position.prix_entree - prix), 5)
            positions_restantes = position_manager.cloturer_position(
                position, resultat, "FERMEE_EXPIREE", positions_restantes
            )
            telegram_sender.envoyer_message(
                f"⏰ *{position.display}* — Position clôturée (durée max atteinte)"
            )
            continue

        evenement, resultat_pips = position_manager.verifier_position(position, prix)

        if evenement == "SL_TOUCHE":
            telegram_sender.envoyer_message(
                telegram_sender.formater_message_evenement(position.display, "SL_TOUCHE", position.stop_loss)
            )
            positions_restantes = position_manager.cloturer_position(
                position, resultat_pips, "FERMEE_SL", positions_restantes
            )

        elif evenement == "TP_TOUCHE":
            telegram_sender.envoyer_message(
                telegram_sender.formater_message_evenement(position.display, "TP_TOUCHE", position.take_profit)
            )
            positions_restantes = position_manager.cloturer_position(
                position, resultat_pips, "FERMEE_TP", positions_restantes
            )

    return positions_restantes


def _analyser_et_signaler(positions_ouvertes: list) -> list:
    """
    Analyse tous les actifs, envoie les signaux validés. Retourne la liste des
    positions ouvertes mise à jour (avec les nouvelles positions ajoutées).

    Limite anti-spam : au maximum config.MAX_SIGNAUX_PAR_CYCLE nouveaux signaux
    envoyés par cycle (cohérence avec MR EMA) - les actifs non traités ce cycle
    seront réévalués au cycle suivant.
    """
    os.makedirs(DOSSIER_GRAPHIQUES_TEMP, exist_ok=True)
    signaux_envoyes_ce_cycle = 0

    for nom_actif, infos in config.ASSETS.items():
        if signaux_envoyes_ce_cycle >= config.MAX_SIGNAUX_PAR_CYCLE:
            logger.info(f"Limite de {config.MAX_SIGNAUX_PAR_CYCLE} signaux atteinte pour ce cycle.")
            break

        symbol = infos["symbol"]

        if position_manager.symbole_a_deja_une_position_ouverte(symbol, positions_ouvertes):
            continue

        try:
            df = data_fetcher.recuperer_bougies(
                symbol, config.TIMEFRAME, config.CANDLES_REQUESTED, config.MIN_CANDLES_REQUIRED
            )
        except data_fetcher.ToutesLesClesEpuiseesError as e:
            logger.warning(f"Toutes les clés API épuisées, arrêt du cycle d'analyse: {e}")
            break
        except data_fetcher.DonneesInsuffisantesError as e:
            logger.warning(str(e))
            continue

        try:
            signal = strategy.analyser_actif(symbol, infos["type"], df)
        except Exception as e:  # noqa: BLE001 - un actif en erreur ne doit jamais arrêter le cycle
            logger.error(f"Erreur d'analyse sur {symbol}: {e}")
            continue

        if signal is None:
            continue

        logger.info(
            f"Signal validé sur {symbol}: {signal.direction} "
            f"(stratégie interne: {signal.strategie}, RR={signal.niveaux.ratio_rr})"
        )

        nouvelle_position = position_manager.ouvrir_position(symbol, infos["display"], infos["type"], signal)

        message = telegram_sender.formater_message_signal(infos["display"], signal.direction, signal.niveaux)

        df_ind = indicators.calculer_tous_indicateurs(
            df, config.EMA_FAST, config.EMA_SLOW, config.ATR_PERIOD,
            config.TDI_RSI_PERIOD, config.TDI_RSI_PRICE_LINE, config.TDI_TRADE_SIGNAL_LINE, config.TDI_VOLATILITY_BAND,
        )
        chemin_image = f"{DOSSIER_GRAPHIQUES_TEMP}/{nom_actif}.png"

        try:
            chart_generator.generer_graphique(
                df_ind, infos["display"], signal.direction,
                signal.niveaux.prix_entree, signal.niveaux.stop_loss, signal.niveaux.take_profit, chemin_image,
            )
            envoi_ok = telegram_sender.envoyer_photo(chemin_image, legende=message)
        except Exception as e:
            logger.error(f"Échec génération/envoi du graphique pour {symbol}: {e} - envoi du texte seul")
            envoi_ok = telegram_sender.envoyer_message(message)

        if envoi_ok.get("ok"):
            positions_ouvertes.append(nouvelle_position)
            signaux_envoyes_ce_cycle += 1
        else:
            logger.error(f"Échec envoi Telegram pour {symbol} - position non enregistrée, sera retentée.")

    return positions_ouvertes


def main() -> None:
    logger.info("=== MAC Bot — démarrage du run ===")

    positions_ouvertes = position_manager.charger_positions_ouvertes()
    marqueurs = _charger_marqueurs()

    positions_ouvertes = _suivre_positions_ouvertes(positions_ouvertes)
    positions_ouvertes = _analyser_et_signaler(positions_ouvertes)
    _traiter_messages_programmes(marqueurs)

    position_manager.sauvegarder_positions_ouvertes(positions_ouvertes)
    _sauvegarder_marqueurs(marqueurs)

    logger.info("=== MAC Bot — run terminé ===")


if __name__ == "__main__":
    main()
