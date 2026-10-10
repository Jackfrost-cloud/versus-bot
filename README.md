# Bot de versus sans IA

Un bot Discord qui répond en MP à « Naruto vs Luffy » avec une analyse argumentée, **sans aucune API d'IA ni clé API**.
Le moteur est déterministe : mêmes données + même question = même résultat. Il est indépendant de Discord (CLI, API ou site possibles).

```
Message → parser → alias/formes → base SQLite → scaling → matchup (routes de victoire) → simulation (5 scénarios) → confiance → réponse
```

## Lancer

```bash
pip install -r requirements.txt
python -m versus ask "Naruto vs Luffy detailed"     # en CLI, sans Discord
DISCORD_TOKEN=... python -m versus                   # bot Discord
python scripts/validate.py                           # valide les données
pip install -r requirements-dev.txt && pytest        # tests
```

Variables : `DISCORD_TOKEN` (obligatoire pour le bot), `ADMIN_IDS` (IDs Discord admins, séparés par des virgules),
`VERSUS_STATE_DIR` (base SQLite + données ajoutées par les admins, à monter sur un volume), `VERSUS_WEB_FALLBACK=0|1`.

## Utilisation

En MP : `Goku vs Saitama`, `Madara vs Aizen avec égalisation`, `Naruto baryon vs Goku ultra instinct`,
`Gojo vs Sukuna combat à mort`, `qui gagne entre X et Y ?`, options `bloodlusted`, `detailed`.
Commandes : `!versus [detailed]`, `!analyze`, `!feats`, `!abilities`, `!sources`, `!compare`, `!form`, `!help`.
Admin : `!admin validate | reload | list | add` (+ fichier JSON joint).

Si aucune forme n'est précisée, la forme par défaut est utilisée **et annoncée**. Si une donnée manque : « Information inconnue dans la base ».
Si un nom est inconnu, une recherche Wikipedia (API publique, sans IA) donne une piste, mais elle n'entre jamais dans le calcul.

## Comment le moteur décide

1. **Feats → statistiques.** Chaque stat (force, vitesse, réflexes, durabilité, puissance, endurance, portée, battle IQ, expérience, échelle relative 0-100) est agrégée depuis des feats. Poids d'un feat = type de preuve (direct 1.0, scaling 0.7, statement 0.6, interprétation 0.5, estimation 0.4, hypothèse 0.15) × priorité de la source (œuvre 10 … forum 3) × confiance. Valeur = moyenne pondérée des 3 meilleurs ; confiance = 1 − Π(1 − poids).
2. **Formes.** Chaque forme est distincte ; une forme enfant remplace les feats de son parent pour une catégorie, et hérite sinon (confiance décotée).
3. **Scaling par catégorie.** `A > B` en vitesse n'implique rien en force. Les relations transitives (3 sauts max) créent des feats implicites ; les cycles sont signalés.
4. **Hax.** Pour chaque capacité : potentiel × fiabilité × (1 − résistance de la cible + vulnérabilité), réduit par la probabilité de toucher si contact requis ; `bypasses` ignore une résistance (ex. le domaine de Sukuna vs Infinity).
5. **Matchup.** Routes de victoire par camp (dégâts bruts, usure, chaque capacité), combinées en ou-bruité. Score pondéré (force 10, vitesse 15, durabilité 10, puissance 10, endurance 5, battle IQ 8, expérience 5, hax 15, résistances 8, versatilité 5, matchup 9), pondérations modifiées par scénario.
6. **Simulation.** Standard, corps à corps, distance, tactique, bloodlusted ; résultat = moyenne pondérée selon les conditions.
7. **Confiance** = qualité des données × netteté du résultat, avec les bandes 95-100 très documenté … 0-19 insuffisant.

Égalisation : `stats` réduit de 60 % les écarts physiques ; `énergie` réduit de 50 % les écarts de puissance/endurance/portée. « Sans égalisation » = mode standard.

## Ajouter un personnage

Un fichier JSON suffit (modèle : `data/characters/*.json`) : `id`, `name`, `short`, `aliases`, `forms` (avec `inherits`), `feats` (catégorie, valeur 0-100, type, source, confiance), `abilities` (tags, `potency`, `reliability`, `win_type`, `hax`, `bypasses`), `resistances`, `weaknesses`. Les relations de scaling sont dans `data/relationships/`. Valide avec `python scripts/validate.py` ou `!admin add`.

## Limites à connaître (important)

- **Les données fournies sont un brouillon** : 14 personnages, valeurs d'auteur sur une échelle relative, références au niveau arc et non au chapitre (`verified: false`). Le bot l'indique dans ses réponses et sa confiance reste basse. La qualité du bot dépend de la qualité de la base.
- Pas de commandes slash `/admin` : l'admin passe par `!admin` + fichier JSON. Pas d'embeds : texte découpé en messages.
- Pas de simulation tour par tour : les scénarios sont des jeux de pondérations.

## Déploiement Railway

Le `Dockerfile` et `railway.json` sont prêts. Variables : `DISCORD_TOKEN`, `ADMIN_IDS`, `VERSUS_STATE_DIR=/data` + un volume monté sur `/data`.
Dans le portail développeur Discord, active « Message Content Intent » pour les commandes sur serveur (les MP fonctionnent sans).
