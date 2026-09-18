"""
draft_engine.py — Moteur d'audit syntaxique des balises <...>, qualification typologique, contrôle de rétention >=90% et tableau de traçabilité.
"""

import re
import difflib
from typing import Dict, List, Tuple, Optional, Any


class DraftEngine:
    """Moteur de contrôle et validation chirurgicale de brouillons selon le protocole /draft."""

    FACTUAL_KEYWORDS = {
        "date", "chiffre", "montant", "prix", "stat", "heure", "h", "min",
        "pourcent", "%", "taux", "score", "délai", "delai", "quota", "seuil",
        "unil", "cours", "recteur", "doyen", "ects", "euro", "chf", "$"
    }

    @classmethod
    def extract_tags(cls, text: str) -> List[Dict[str, Any]]:
        """
        Détecte toutes les balises délimitées par des chevrons <...> dans le texte brut.
        Qualifie chaque balise : 'lexical' (hésitation synonymique) ou 'factual' (donnée manquante / indice).
        """
        # Ne pas matcher les balises HTML usuelles ou balises de diff
        html_tags = {"del", "ins", "span", "br", "p", "div", "b", "i", "strong", "em", "code", "table", "tr", "td", "th"}
        
        raw_matches = re.finditer(r'<([^<>]+)>', text)
        tags = []

        for m in raw_matches:
            content = m.group(1).strip()
            # Ignorer balises HTML fermantes ou simples
            tag_name = content.split()[0].lower().lstrip('/')
            if tag_name in html_tags:
                continue

            # Qualification typologique
            is_factual = False
            # Présence de chiffres ou ?
            if re.search(r'\d', content) or '?' in content:
                is_factual = True
            else:
                words = set(re.findall(r'\b\w+\b', content.lower()))
                if words & cls.FACTUAL_KEYWORDS:
                    is_factual = True

            typology = "factual" if is_factual else "lexical"
            tags.append({
                "raw_tag": m.group(0),
                "inner_content": content,
                "typology": typology,
                "start": m.start(),
                "end": m.end()
            })

        return tags

    @classmethod
    def calculate_retention(cls, original: str, revised: str, ignore_tags: bool = True) -> float:
        """
        Calcule le taux de rétention mot à mot entre le texte original et le texte retouché.
        Si ignore_tags=True, exclut les balises <...> d'origine (placeholders voués à être résolus)
        pour mesurer la fidélité réelle au texte stable d'Henri.
        Retourne un pourcentage entre 0.0 et 100.0.
        """
        if not original.strip():
            return 100.0 if not revised.strip() else 0.0

        clean_orig = original
        if ignore_tags:
            # Remplacer les balises <...> par des espaces pour ne pas pénaliser la résolution de placeholders
            clean_orig = re.sub(r'<[^<>]+>', ' ', clean_orig)

        # Normalisation des tokens de mots
        orig_words = re.findall(r'\b\w+\b', clean_orig.lower())
        rev_words = re.findall(r'\b\w+\b', revised.lower())

        if not orig_words:
            return 100.0

        matcher = difflib.SequenceMatcher(None, orig_words, rev_words, autojunk=False)
        matching_words = sum(match.size for match in matcher.get_matching_blocks())
        retention = (matching_words / len(orig_words)) * 100.0
        return round(retention, 2)

    @classmethod
    def verify_retention_threshold(
        cls,
        original: str,
        revised: str,
        threshold: float = 90.0,
        ignore_tags: bool = True
    ) -> Tuple[bool, float]:
        """Vérifie si le seuil contractuel de rétention (>= 90%) est respecté."""
        retention = cls.calculate_retention(original, revised, ignore_tags=ignore_tags)
        is_valid = retention >= threshold
        return is_valid, retention

    @classmethod
    def generate_diff_table(
        cls,
        original: str,
        revised: str,
        tag_resolutions: Optional[List[Dict[str, str]]] = None
    ) -> str:
        """
        Génère le tableau comparatif normé du skill /draft :
        | Segment Original (Avant) | Segment Corrigé (Après) | Justification Chirurgicale |
        """
        table_rows: List[str] = [
            "| Segment Original (Avant) | Segment Corrigé (Après) | Justification Chirurgicale |",
            "| :--- | :--- | :--- |"
        ]

        # 1. Traçabilité des balises résolues si fournies
        if tag_resolutions:
            for item in tag_resolutions:
                before = item.get("before", "").replace("|", "\\|")
                after = item.get("after", "").replace("|", "\\|")
                justif = item.get("justification", "Résolution chirurgicale de balise").replace("|", "\\|")
                table_rows.append(f"| *« {before} »* | *« {after} »* | {justif} |")

        # 2. Analyse différentielle par difflib des micro-changements
        orig_tokens = re.findall(r'\S+|\s+', original)
        rev_tokens = re.findall(r'\S+|\s+', revised)

        matcher = difflib.SequenceMatcher(None, orig_tokens, rev_tokens, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag in ('replace', 'delete', 'insert'):
                del_part = "".join(orig_tokens[i1:i2]).strip()
                ins_part = "".join(rev_tokens[j1:j2]).strip()

                if not del_part and not ins_part:
                    continue

                # Éviter de dupliquer ce qui a déjà été noté dans tag_resolutions
                if tag_resolutions:
                    already_tracked = any(item.get("before") == del_part or item.get("after") == ins_part for item in tag_resolutions)
                    if already_tracked:
                        continue

                del_clean = del_part.replace("|", "\\|").replace("\n", " ")
                ins_clean = ins_part.replace("|", "\\|").replace("\n", " ")

                justif = "Retouche chirurgicale de surface"
                if not del_clean and ins_clean:
                    justif = "Ajout de précision contextuelle"
                elif del_clean and not ins_clean:
                    if any(k in del_clean.lower() for k in ("désolé", "excuse", "pardon")):
                        justif = "Suppression de la sur-excusite / attaque directe"
                    else:
                        justif = "Élagage de concision sans perte de substance"
                elif del_clean and ins_clean:
                    if del_clean.rstrip("s") == ins_clean.rstrip("s"):
                        justif = "Correction de l'accord en nombre / orthographe"
                    else:
                        justif = "Ajustement syntaxique & fluidité"

                table_rows.append(f"| *« {del_clean or '—'} »* | *« {ins_clean or '—'} »* | {justif} |")

        if len(table_rows) <= 2:
            return ""

        return "\n".join(table_rows)

    @classmethod
    def audit_draft(
        cls,
        original: str,
        revised: str,
        tag_resolutions: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Audit complet d'une révision de brouillon."""
        tags = cls.extract_tags(original)
        is_compliant, retention_rate = cls.verify_retention_threshold(original, revised)
        diff_table = cls.generate_diff_table(original, revised, tag_resolutions)

        # Vérification des marqueurs IA bannis (ex: tirets cadratins —)
        has_em_dash = ("—" in revised) or ("–" in revised)

        return {
            "retention_percent": retention_rate,
            "is_retention_compliant": is_compliant,
            "detected_tags": tags,
            "tags_count": len(tags),
            "banned_markers_found": {
                "em_dash": has_em_dash
            },
            "diff_table_markdown": diff_table
        }
