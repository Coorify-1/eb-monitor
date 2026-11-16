# THE ANALYST — Daily Market Analysis & Intelligence

Chaque matin à **06:30 (heure de New York)**, ce moteur lit les données de toutes les pages
Economic Bearings, les analyse, fait rédiger un commentaire court en anglais par une IA
gratuite, vérifie chaque chiffre, puis publie `docs/eb-analyst.json`. Le composant Framer
**THE ANALYST** (`TheAnalyst.tsx`) affiche ce fichier.

Coût : 0 €. GitHub Actions (dépôt public), GitHub Models (IA gratuite avec le jeton du
workflow, aucune clé à créer), sources publiques et vos propres Workers.

## Ce que le moteur réutilise (sans rien modifier)

| Page | Source lue |
|---|---|
| Financial Markets `/market-data` | Worker `marketdata` → FRED : taux US 2/10/30 ans, VIX, Brent, WTI, gaz |
| Energy Terminal `/energy-terminal` | API CEII (actualités et calendrier énergie) + prix FRED |
| Crypto & Currencies `/crypto-currencies` | CoinGecko (Bitcoin, Ether) + BCE via Frankfurter (EUR, JPY, GBP, CHF, CNY) |
| Hard Assets `/hard-assets-terminal` | Worker `metals` : or, argent, platine, cuivre |
| Estate Index `/estate-index` | Worker `real-estates` : prix des logements par pays |
| Corporate Monitor `/corporate-monitor` | `docs/eb-monitor.json` |
| Market Outlook `/market-outlook` | `eb-outlook/docs/eb-outlook.json` |
| Islamic Investment `/islamic-investment` | `docs/eb-islamic.json` (EB US 100 et EB Shariah US 100) |
| Géopolitique | Google News (volume d’actualité par thème, 2 derniers jours vs 12 jours précédents) |

## Comment l'analyse est faite

1. **Mouvements** : chaque marché est comparé à son mouvement quotidien habituel (60 derniers jours).
   Un mouvement « net » dépasse 1 fois la normale, un mouvement « fort » 2 fois.
2. **Régime** : le schéma qui colle le mieux au jour (risk-off, risk-on, choc d'inflation,
   inquiétude sur la croissance, dollar fort ou faible).
3. **Thèmes** (`transmission.json`) : un thème d'actualité n'est présenté comme une cause que si
   son volume d'actualité dépasse 1,6 fois sa normale **et** si au moins deux marchés liés ont bougé
   dans le sens attendu. Sinon le texte reste prudent ou place le thème dans « What we're watching ».
4. **Rédaction** : l'IA reçoit uniquement ces faits. Le contrôle rejette tout chiffre absent des
   faits, tout lien inconnu, toute URL, tout conseil ou toute prévision. Deux échecs → texte
   rédigé par des phrases types. La page n'est jamais vide.

## Mise en route

1. Envoyez le dossier `analyst/` et `.github/workflows/analyst-daily.yml` dans le dépôt `eb-monitor`.
2. **Actions → THE ANALYST daily → Run workflow** pour publier une première édition tout de suite.
3. Framer : *Assets → Code → New file* `TheAnalyst`, collez `TheAnalyst.tsx`, glissez le composant
   sur la page. Le **Data URL** est déjà rempli. Les liens vers vos pages se règlent dans **Page links**.

Optionnel : si GitHub Models n'est pas disponible sur votre compte, créez une clé gratuite sur
Google AI Studio et ajoutez-la comme secret `GEMINI_API_KEY` (Settings → Secrets → Actions).

## Corriger une édition à la main

Ouvrez `analyst/override.json` sur GitHub, mettez la date de l'édition (`2026-11-17`), remplissez
seulement les champs à remplacer (`headline`, `tone`, `lead`, `briefs`, `watch`) et validez.
Le site est mis à jour en 2 minutes environ, avec la mention « Edited by the Economic Bearings newsroom ».
Liens vers vos pages : `[[energy|Brent crude]]` (clés : markets, energy, crypto, metals, estate,
corporate, outlook, islamic).

## Fichiers

- `config.py` : adresses des sources, marchés suivis, seuils, modèles d'IA
- `transmission.json` : thèmes géopolitiques et marchés qu'ils font bouger (modifiable)
- `sources.py` : lecture des sources · `analysis.py` : l'analyse · `writer.py` : rédaction et contrôle
- `run.py` : l'édition du jour, archive dans `docs/analyst/AAAA-MM-JJ.json`
- `TheAnalyst.tsx` : le composant Framer
