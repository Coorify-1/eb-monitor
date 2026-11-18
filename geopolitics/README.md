# GEOPOLITICAL RISK MONITOR

Chaque **lundi à 06:15 (heure de New York)**, ce moteur mesure les grands risques géopolitiques
et publie `docs/eb-geopolitics.json`. Le composant Framer **Geopolitical Risk Monitor**
(`GeopoliticalRiskMonitor.tsx`) affiche ce fichier.

Coût : 0 €. GitHub Actions (dépôt public), sources publiques gratuites, et la même clé Gemini
gratuite que THE ANALYST (`GEMINI_API_KEY`, déjà en place).

## Ce qui est mesuré

| Mesure | Comment | Source |
|---|---|---|
| **Attention** | Part de l'actualité mondiale consacrée à chaque risque, chaque semaine, pondérée par le ton (plus négatif = plus de poids), comparée à son propre historique de 5 ans (les années récentes comptent davantage). 0 = niveau habituel, 1 = nettement au-dessus. Moyenne sur 2 semaines. | GDELT (depuis 2017) |
| **Market reaction** (−1 à +1) | Les 3 actifs liés à chaque risque : leur mouvement sur un mois, comparé à leur mouvement mensuel habituel (2 ans) et au sens attendu si le risque se réalisait. | FRED, Worker EB Metals |
| **Level** | High / Medium / Low à partir des deux mesures (même règle que le composant). Modifiable à la main. | — |
| **Short view** | Deux phrases par risque, sans chiffres, rédigées à partir des titres de la semaine et contrôlées (pas de conseil, pas de prévision). Sans clé ou en cas d'échec : phrases types. | Google News, Gemini |
| **Global attention** | Moyenne de tous les risques, lissée, depuis 2017. | GDELT |

## Mise en route

1. Envoyez le dossier `geopolitics/`, `tests/test_geopolitics.py` et
   `.github/workflows/geopolitics-weekly.yml` dans le dépôt `eb-monitor`.
2. **Actions → Geopolitical Risk Monitor weekly → Run workflow**. Le premier passage télécharge
   l'historique depuis 2017 (15 à 30 minutes). Les semaines suivantes prennent quelques minutes.
3. Framer : *Assets → Code → New file* `GeopoliticalRiskMonitor`, collez `GeopoliticalRiskMonitor.tsx`.
   Le **Data URL** est déjà rempli. Tant que le premier fichier n'est pas publié, le canevas Framer
   montre les données d'exemple.

## Modifier à la main (sur GitHub, le site suit en 2 minutes environ)

- `override.json` : fixer le **level** (`high`, `medium`, `low`) ou la **view** d'un risque.
  Laissez vide pour revenir aux données.
- `calendar.json` : les grandes dates géopolitiques (`date`, `end`, `title`, `region`, `risk`).
  Les dates passées disparaissent seules.
- `events.json` : les événements numérotés sur la courbe « Global attention over time ».
- `risks.json` : ajouter, retirer ou modifier un risque (requête d'actualité et 3 actifs).
  Si la requête change, l'historique de ce risque est recalculé au passage suivant.

Dans Framer, la liste **Risks** choisit les risques affichés et leur ordre, et permet aussi de
fixer un level ou un texte, qui passent avant ceux du fichier.

## Fichiers

- `config.py` : réglages (fenêtres, pondérations, horaire)
- `sources.py` : GDELT, FRED, EB Metals, Google News · `measure.py` : les calculs · `writer.py` : les vues
- `run.py` : la mise à jour, archive dans `docs/geopolitics/AAAA-Wnn.json`
- `data/attention.json` : historique hebdomadaire de l'attention (mis à jour par le moteur)
- `GeopoliticalRiskMonitor.tsx` : le composant Framer

*Information only, not investment advice.*
