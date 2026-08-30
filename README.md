# MAC Bot — Robot d'analyse de marché (version GitHub Actions)

## ⚠️ À lire avant de déployer

1. **Ce robot n'exécute aucun trade.** Il analyse le marché et envoie des alertes sur Telegram. Toute décision de trading reste la tienne.
2. **Aucune stratégie technique ne garantit un gain.** Fais un backtest (voir plus bas) et observe en conditions réelles avant tout capital réel.
3. **Régénère tes tokens/clés API** s'ils ont déjà été partagés ailleurs qu'ici, avant de les mettre dans GitHub Secrets.

## Ce qui a changé par rapport à la version originale (Render)

Cette version a été adaptée pour tourner sur **GitHub Actions** (cron ponctuel) au lieu de **Render** (serveur web permanent). Changement de fond :

| | Version originale (Render) | Cette version (GitHub Actions) |
|---|---|---|
| Exécution | Serveur Flask permanent 24/24 | Script qui se lance, s'exécute, s'arrête, toutes les 10 min |
| Persistance | SQLite (`database.py`) | Fichiers JSON committés automatiquement |
| Commandes Telegram interactives | Oui (webhook : `/inscrire`, `/connexion`, `/signaux`, `/canaux`) | **Non** — un cron ne peut pas écouter les messages entrants en temps réel |
| Comptes utilisateurs | Oui (inscription email/mot de passe) | **Non** — nécessite le webhook, retiré |
| Signaux envoyés | Sur ton canal | Identique, sur ton canal |

**Pourquoi ce compromis :** un cron GitHub Actions exécute un script puis s'arrête — il ne peut jamais "écouter" en continu les messages Telegram entrants, contrairement à un serveur web permanent. Pour garder les commandes interactives, il faudrait héberger le bot sur un VPS ou sur Render (voir l'expérience équivalente avec MR EMA).

## Structure du projet

```
mac-bot/
├── .github/workflows/
│   ├── trading-bot.yml   ← cron 10 min : analyse le marché et envoie les signaux
│   └── backtest.yml       ← déclenchement manuel : teste la stratégie sur l'historique
├── config.py               ← tous les paramètres (actifs, indicateurs, risk management)
├── data_fetcher.py          ← récupération Twelve Data, rotation automatique de 4 clés API
├── indicators.py             ← calcul EMA50/200, ATR, TDI
├── risk_management.py         ← calcul des pips + validation stricte RR [1.50, 3.50]
├── strategy.py                 ← les 2 stratégies internes (retest EMA50+TDI, croisement+rejection)
├── position_manager.py          ← suivi des positions ouvertes (JSON, remplace SQLite)
├── telegram_sender.py            ← formatage et envoi des messages Telegram
├── chart_generator.py             ← génération des graphiques envoyés avec chaque signal
├── main.py                         ← point d'entrée, exécuté par le cron
├── backtest.py                      ← simulation de la stratégie sur données historiques réelles
├── requirements.txt
└── data/                             ← état persistant (committé automatiquement par le cron)
    ├── positions_ouvertes.json
    ├── historique_cloture.json
    └── marqueurs_messages.json        ← anti double-envoi du message du matin/soir
```

## Déploiement

### 1. Créer le repo GitHub

- Nom au choix (ex: `mac-bot`)
- **Visibilité : Public** obligatoire sur compte gratuit pour que le cron `schedule` se déclenche automatiquement (voir la section dédiée plus bas)
- Upload tous les fichiers en conservant la structure (`.github/workflows/` avec ses 2 fichiers)

### 2. Permissions du workflow

Settings → Actions → General → Workflow permissions → **Read and write permissions** → Save

### 3. Secrets à créer

Settings → Secrets and variables → Actions → New repository secret, pour chacun :

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `TWELVE_DATA_KEY_1`
- `TWELVE_DATA_KEY_2`
- `TWELVE_DATA_KEY_3`
- `TWELVE_DATA_KEY_4`

### 4. Ajouter le bot au canal Telegram

Le bot doit être administrateur du canal avec droit de publier des messages.

### 5. Premier test

Actions → "MAC Bot - Robot de Trading" → Run workflow → confirme. Vérifie les logs, puis le canal Telegram.

## Lancer un backtest

Actions → "MAC Bot - Backtest (manuel)" → Run workflow → attends la fin (plusieurs minutes) → clique sur le run terminé → section **Artifacts** en bas de page → télécharge **rapport-backtest**.

Le rapport contient : nombre de trades, win rate, profit factor, détail par stratégie interne et par actif.

## Repo privé et cron automatique : la limite à connaître

Sur un compte GitHub gratuit, les workflows `schedule` (cron automatique) ne se déclenchent **que sur les repos publics**. Un repo privé nécessite un plan payant pour que le cron fonctionne tout seul — sinon, seul `workflow_dispatch` (déclenchement manuel) fonctionnera.

## Twelve Data — rotation de 4 clés

Le plan gratuit Twelve Data est limité à 800 requêtes/jour et 8/minute par clé. Avec 4 clés en rotation automatique, le quota total grimpe à 3200 requêtes/jour. Le code passe automatiquement à la clé suivante dès qu'une limite est détectée (code 429 ou message d'erreur explicite).

## Limites connues (transparence technique)

- Les données Twelve Data ont un délai variable selon l'actif (documenté, pas du temps réel garanti)
- Le backtest ne simule ni spread ni slippage
- Les commandes Telegram interactives ne sont pas disponibles dans cette version (voir tableau plus haut)
- Aucune garantie de gain : ce robot est un outil d'aide à la décision
