# doc-version — Serveur MCP de Versionnage Documentaire & CAS

Le serveur MCP `doc-version` gère le cycle de vie documentaire, le versionnage déclaratif local via Content-Addressable Storage (CAS), le calcul de diffs syntaxiques et l'intégration collaborative déterministe.

---

## 🏛️ Architecture Fondamentale

1. **Content-Addressable Storage (CAS)** :
   - Stockage immuable adressé par le contenu (hachage SHA-256, compression zlib niveau 9).
   - Répertoire standard : `~/.gemini/antigravity/cas_commits/` avec sous-arborescences `commits/` et `objects/`.
   - Snapshots atomiques horodatés avec séparation stricte des auteurs (`collaborateur`, `agent`).

2. **Double Mode d'Analyse Différentielle** :
   - **Mode `paper`** : Adapté aux manuscrits scientifiques LaTeX et Markdown académique. Intègre la projection AST, la détection des blocs de formules KaTeX, et l'évaluation de conformité stylistique / anti-IA ($P(\text{AI}) < 0.10$).
   - **Mode `draft`** : Adapté à la relecture chirurgicale de brouillons. Traque les balises d'incertitude `<XXX>`, calcule le mot-à-mot différentiel coloré (`<span>` vert / rouge) et surveille le seuil de rétention textuelle ($\ge 90\%$).

3. **Garantie Zéro Conflit Non Résolu** :
   - Synchronisation amont avant édition (`record_git_pull_event`) avec `git pull --rebase` et autostash.
   - En cas de conflit, arrêt immédiat et signalement pour conciliation manuelle sans perte d'information.

---

## 🛠️ Suite des 7 Outils MCP

| Outil | Rôle Principal | Paramètres Clés |
|---|---|---|
| `commit_document` | Fige un instantané horodaté dans le CAS | `target` (str), `message` (str), `author` ("agent" / "collaborateur"), `content` (opt), `is_pinned` (bool), `mode` ("paper" / "draft"), `style_audit` (opt) |
| `record_style_audit` | Enregistre les métadonnées d'audit de style (itérations, résolutions) | `commit_id` (str), `target` (opt), `iterations` (opt), `summary` (opt) |
| `get_diff_artifact` | Calcule le diff mot-à-mot et génère l'artéfact Markdown | `target` (str), `diff_explanation` (str), `brain_dir` (str), `mode` ("paper" / "draft"), `from_commit_id` (opt), `to_commit_id` (opt) |
| `restore_commit` | Restaure l'état d'un fichier depuis un commit CAS | `commit_id` (str), `target` (opt), `dry_run` (bool, default False) |
| `list_commits` | Liste l'historique chronologique des snapshots CAS | `target` (opt), `limit` (int, default 10), `mode` (opt) |
| `prune_commits` | Purge les snapshots expirés selon le TTL et la taille max | `ttl_days` (int, default 14), `max_size_mb` (int, default 500), `keep_baselines` (bool, default True) |
| `record_git_pull_event` | Synchronise le dépôt Git avec autostash et snapshot | `repo_path` (str), `autostash` (bool, default True) |

---

## 🔄 Cycle Collaboratif Déterministe (4 Temps)

1. **Pull & Autostash (`record_git_pull_event`)** :
   Toujours synchroniser l'état distant avant d'entamer une session de révision.
2. **Scellement de la Baseline (`commit_document`)** :
   Geler l'état d'origine validé avec `author="collaborateur"` avant toute modification chirurgicale.
3. **Édition Chirurgicale & Scellement Agent (`commit_document`)** :
   Appliquer les retouches bloc par bloc (sans écrasement global) puis enregistrer le snapshot avec `author="agent"`.
4. **Projection Différentielle (`get_diff_artifact`)** :
   Produire l'artéfact Markdown interactif dans le répertoire de session (`brain_dir`) et partager exclusivement son lien cliquable en tête de réponse.

---

## ⚠️ Invariants et Règles Strictes

- **Zéro Écrasement Global** : Ne jamais écraser un fichier entier sans diff traçable. L'édition s'effectue bloc par bloc.
- **Préservation des Collaborateurs** : Les contributions des co-auteurs sont strictement prioritaires. Interdiction absolue du `git push -f` et du merge aveugle.
- **Anti-Simulation Machine** : Ne jamais rédiger manuellement un commit CAS ou un diff. Utiliser exclusivement les outils déclaratifs `doc-version`.
- **Restitution Chat** : Partager systématiquement le lien cliquable vers l'artéfact Brain (`file:///<appDataDir>/brain/<conversation-id>/<nom>.md`) en première ligne.
