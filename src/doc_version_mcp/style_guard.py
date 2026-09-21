"""
style_guard.py — Boucle bloquante déterministe avoid-ai-writing pour doc-version-mcp.
Intègre le détecteur Node.js avoid-ai-writing et applique une politique budgétaire graduée mais sévère.
"""

import os
import sys
import re
import json
import shutil
import tempfile
import subprocess
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple


DEFAULT_DETECT_JS_PATHS = [
    Path(r"C:\Users\Jamet\Documents\VoiceNotes\_agents\scripts-for-skills\avoid-ai-writing\skills\ai-writing-detector\scripts\detect.js"),
    Path(r"C:\Users\hjamet\Documents\VoiceNotes\_agents\scripts-for-skills\avoid-ai-writing\skills\ai-writing-detector\scripts\detect.js"),
]

# Stop-words pour la détection automatique de la langue
FR_STOPWORDS = {
    "le", "la", "les", "de", "des", "du", "un", "une", "et", "en", "dans", "pour",
    "qui", "que", "est", "sont", "avec", "sur", "ce", "cette", "ces", "mais", "ou",
    "donc", "or", "ni", "car", "nous", "vous", "ils", "elles", "leur", "comme", "aussi",
    "plus", "par", "au", "aux", "d'un", "d'une", "l'un", "l'une", "qu'il", "qu'elle"
}

EN_STOPWORDS = {
    "the", "of", "and", "in", "to", "a", "is", "that", "for", "it", "as", "was",
    "with", "be", "by", "on", "at", "from", "this", "which", "are", "have", "had",
    "not", "but", "what", "all", "were", "when", "can", "said", "there", "use", "an"
}

# Tier 1A canoniques (Hard Blockers - Tolérance 0)
TIER1A_TERMS = {
    "delve": "explore, dig into, look at",
    "tapestry": "describe the actual complexity",
    "paradigm": "model, approach, framework",
    "beacon": "rewrite entirely",
    "robust": "strong, reliable, solid",
    "comprehensive": "thorough, complete, full",
    "cutting-edge": "latest, newest, advanced",
    "pivotal": "important, key, critical",
    "meticulous": "careful, detailed, precise",
    "meticulously": "carefully, precisely",
    "seamless": "smooth, easy, without friction",
    "seamlessly": "smoothly, easily",
    "game-changer": "describe what changed",
    "game-changing": "describe what changed",
    "nestled": "is located, sits",
    "vibrant": "describe what makes it active",
    "thriving": "growing, active",
    "bustling": "busy, active",
    "intricate": "complex, detailed",
    "intricacies": "complexities, details",
    "ever-evolving": "changing, growing",
    "enduring": "lasting, long-running",
    "daunting": "hard, difficult",
    "holistic": "complete, full, whole",
    "holistically": "completely, fully",
    "actionable": "practical, useful, concrete",
    "impactful": "effective, significant",
    "learnings": "lessons, findings, takeaways",
    "synergy": "describe the combined effect",
    "synergies": "describe the combined effect",
    "interplay": "relationship, connection",
    "symphony": "describe the coordination",
    "embrace": "adopt, accept, use",
    "deep dive": "examine, investigate, look closely",
    "thought leadership": "expertise, proven track record",
    "best practices": "proven methods, standards"
}

# Transitions mécaniques anglaises (Hard Blockers - Tolérance 0)
EN_MECHANICAL_TRANSITIONS = {
    "moreover": "cut or integrate smoothly",
    "furthermore": "cut or integrate smoothly",
    "in conclusion": "cut or summarize key finding directly",
    "notably": "cut or state concrete fact",
    "additionally": "also, and, or cut",
    "in summary": "cut or state conclusion",
    "to summarize": "cut or state conclusion"
}

# Transitions mécaniques françaises (Hard Blockers - Tolérance 0)
FR_MECHANICAL_TRANSITIONS = {
    "en conclusion": "aller droit au fait ou supprimer",
    "par conséquent": "donc, ainsi",
    "de surcroît": "aussi, de plus, ou supprimer",
    "en outre": "aussi, de plus, ou supprimer",
    "il convient de noter": "supprimer ou énoncer directement",
    "il est important de noter": "supprimer ou énoncer directement",
    "notamment": "en particulier, ou citer directement les exemples"
}


@dataclass
class StyleCheckResult:
    verdict: str  # "PASS", "WARN", "FAIL"
    word_count: int
    budget_max: int
    hard_blockers: List[Dict[str, Any]] = field(default_factory=list)
    soft_warnings: List[Dict[str, Any]] = field(default_factory=list)
    error_report: str = ""
    detected_language: str = "en"


def detect_language(text: str) -> str:
    """Détecte la langue dominante (en ou fr) via un comptage de stop-words."""
    if not text:
        return "en"
    words = re.findall(r"\b[a-zA-ZàâäéèêëîïôöùûüçÀÂÄÉÈÊËÎÏÔÖÙÛÜÇ'-]+\b", text.lower())
    if not words:
        return "en"

    fr_count = sum(1 for w in words if w in FR_STOPWORDS)
    en_count = sum(1 for w in words if w in EN_STOPWORDS)

    if fr_count > en_count:
        return "fr"
    return "en"


def find_detect_js_script() -> Path:
    """Résout le chemin canonique vers detect.js."""
    env_override = os.environ.get("AVOID_AI_WRITING_DETECT_JS")
    if env_override and Path(env_override).is_file():
        return Path(env_override).resolve()

    for cand in DEFAULT_DETECT_JS_PATHS:
        if cand.is_file():
            return cand.resolve()

    # Recherche heuristique depuis le profil utilisateur
    user_home = Path.home()
    cand_dyn = user_home / "Documents" / "VoiceNotes" / "_agents" / "scripts-for-skills" / "avoid-ai-writing" / "skills" / "ai-writing-detector" / "scripts" / "detect.js"
    if cand_dyn.is_file():
        return cand_dyn.resolve()

    raise FileNotFoundError(
        "Script detect.js de avoid-ai-writing introuvable. "
        "Veuillez vérifier l'emplacement de avoid-ai-writing ou définir AVOID_AI_WRITING_DETECT_JS."
    )


def mask_markdown_code_and_comments(text: str) -> str:
    """Masque les blocs de code et commentaires pour éviter les faux positifs d'analyse."""
    # Masquage des blocs ```...```
    def mask_code_block(m):
        return "\n" * m.group(0).count("\n")

    masked = re.sub(r"```.*?```", mask_code_block, text, flags=re.DOTALL)
    # Masquage des inline code `...`
    masked = re.sub(r"`[^`\n]+`", lambda m: " " * len(m.group(0)), masked)
    # Masquage des commentaires HTML <!-- ... -->
    masked = re.sub(r"<!--.*?-->", mask_code_block, masked, flags=re.DOTALL)
    return masked


def locate_line_in_text(text: str, pattern_or_term: str, is_regex: bool = False) -> int:
    """Trouve la ligne (1-indexée) d'une occurrence dans le texte hors blocs de code."""
    lines = text.splitlines()
    in_code_block = False

    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        if is_regex:
            if re.search(pattern_or_term, line, re.IGNORECASE):
                return idx
        else:
            if pattern_or_term.lower() in line.lower():
                return idx

    # Si non trouvé précisément, renvoyer la ligne 1 par défaut
    return 1


def scan_deterministic_hard_blockers(text: str, language: str) -> List[Dict[str, Any]]:
    """
    Exécute un scan déterministe absolu (Tolérance 0) pour :
    - em-dashes ('—', '--')
    - normalisation (ZWSP, homoglyphes cyrilliques/grecs)
    - transitions mécaniques strictes
    - Tier 1A stricts
    """
    blockers = []
    lines = text.splitlines()
    in_code_block = False

    # 1. Scanner les em-dashes ligne par ligne
    for idx, line in enumerate(lines, start=1):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Ignorer les lignes de frontmatter YAML (---) ou séparateurs de tableau (|---|)
        if re.match(r"^---+$", stripped) or re.match(r"^\|?\s*[-:]+\s*\|", stripped):
            continue

        # Em-dash littéral '—' (U+2014)
        if "—" in line:
            blockers.append({
                "type": "Hard Blocker: em-dash",
                "line": idx,
                "term": "—",
                "suggestion": "Remplacer par une virgule, deux points, ou reformuler sans incise artificielle"
            })

        # Double tiret '--' utilisé comme tiret d'incise (hors drapeaux CLI --arg)
        dash_match = re.search(r"(?<=\s)--(?=\s)|(?<=\w)--(?=\w)|(?<=\s)--(?!-)", line)
        if dash_match and not re.search(r"--[a-zA-Z0-9_\-]+", line):
            blockers.append({
                "type": "Hard Blocker: em-dash ('--')",
                "line": idx,
                "term": "--",
                "suggestion": "Remplacer par une virgule ou des parenthèses sobres"
            })

        # Caractères ZWSP (Zero-Width Space & joiners)
        zwsp_match = re.search(r"[\u200B\u200C\u200D\uFEFF\u2060]", line)
        if zwsp_match:
            blockers.append({
                "type": "Hard Blocker: Normalisation (ZWSP)",
                "line": idx,
                "term": repr(zwsp_match.group(0)),
                "suggestion": "Supprimer les caractères invisibles ou les balises zero-width"
            })

        # Homoglyphes Cyrilliques / Grecs dans du texte latin
        homoglyph_match = re.search(r"[аеорсхукмнвтАЕОРСХУКМНВТοΟαρΡ]", line)
        if homoglyph_match and not re.search(r"[\u0400-\u04FF\u0370-\u03FF]{4,}", line):
            # Si le texte n'est pas intégralement en cyrillique ou grec
            blockers.append({
                "type": "Hard Blocker: Normalisation (Homoglyphe)",
                "line": idx,
                "term": homoglyph_match.group(0),
                "suggestion": "Remplacer par le caractère latin standard ASCII/UTF-8"
            })

    # 2. Scanner les transitions mécaniques
    masked_text = mask_markdown_code_and_comments(text)
    trans_dict = EN_MECHANICAL_TRANSITIONS if language == "en" else FR_MECHANICAL_TRANSITIONS

    for phrase, suggestion in trans_dict.items():
        pattern = rf"\b{re.escape(phrase)}\b"
        matches = list(re.finditer(pattern, masked_text, re.IGNORECASE))
        for m in matches:
            line_num = text[:m.start()].count("\n") + 1
            blockers.append({
                "type": "Hard Blocker: Transition Mécanique",
                "line": line_num,
                "term": m.group(0),
                "suggestion": suggestion
            })

    # 3. Scanner les Tier 1A stricts
    for term, suggestion in TIER1A_TERMS.items():
        pattern = rf"\b{re.escape(term)}\b"
        matches = list(re.finditer(pattern, masked_text, re.IGNORECASE))
        for m in matches:
            line_num = text[:m.start()].count("\n") + 1
            blockers.append({
                "type": "Hard Blocker: Vocabulaire IA Tier 1A",
                "line": line_num,
                "term": m.group(0),
                "suggestion": suggestion
            })

    return blockers


def run_node_detector(file_path: Path, context_mode: str = "technical") -> Dict[str, Any]:
    """Exécute detect.js en sous-processus Node.js et retourne le résultat JSON brut."""
    detect_script = find_detect_js_script()
    node_cmd = shutil.which("node")
    if not node_cmd:
        raise RuntimeError("Node.js est introuvable dans le PATH système. L'évaluation de style requiert Node.js.")

    cmd = [
        node_cmd,
        str(detect_script),
        "--file", str(file_path),
        "--context", context_mode,
        "--json"
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(f"Erreur d'exécution de detect.js (code {res.returncode}): {res.stderr}")

    try:
        return json.loads(res.stdout)
    except Exception as e:
        raise RuntimeError(f"Sortie JSON invalide renvoyée par detect.js: {e}\nSortie brute:\n{res.stdout}")


def check_style(
    text: str,
    language: str = "auto",
    context_mode: str = "technical"
) -> StyleCheckResult:
    """
    Point d'entrée principal du Style Guard.
    Évalue le document, applique la classification stricte des alertes et le budget gradué.
    """
    if not text or not text.strip():
        return StyleCheckResult(
            verdict="PASS",
            word_count=0,
            budget_max=0,
            hard_blockers=[],
            soft_warnings=[],
            detected_language="en"
        )

    # Résolution de la langue
    detected_lang = detect_language(text)
    effective_lang = detected_lang if language == "auto" else language.lower()
    if effective_lang not in ("en", "fr"):
        effective_lang = "en"

    # Calcul du nombre de mots
    word_count = len(re.findall(r"\b\w+\b", text))

    # Calcul du budget max de soft warnings selon la politique graduée mais sévère
    if word_count < 500:
        budget_max = 0
    elif word_count <= 1500:
        budget_max = 1
    else:
        budget_max = 2

    # 1. Exécution du scan déterministe local
    hard_blockers = scan_deterministic_hard_blockers(text, language=effective_lang)
    soft_warnings = []

    # 2. Exécution du moteur detect.js
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as tmp:
        tmp.write(text)
        tmp_path = Path(tmp.name)

    try:
        raw_result = run_node_detector(tmp_path, context_mode=context_mode)
    finally:
        try:
            tmp_path.unlink()
        except Exception:
            pass

    # Traitement des alertes renvoyées par detect.js
    node_issues = raw_result.get("issues", [])
    for iss in node_issues:
        iss_type = str(iss.get("type", "")).lower()
        iss_text = str(iss.get("text", "")).strip()
        iss_sug = str(iss.get("suggestion", "")).strip()
        line_num = locate_line_in_text(text, iss_text)

        # Classification Hard Blockers (Tolérance 0)
        if iss_type in ("tier1", "em-dash", "transition", "generic-conclusion",
                        "normalization-flag", "chatbot", "reasoning-artifact",
                        "cutoff-disclaimer", "ai-placeholder", "ai-citation-markup"):
            hard_blockers.append({
                "type": f"Hard Blocker ({iss_type})",
                "line": line_num,
                "term": iss_text,
                "suggestion": iss_sug
            })
        # Classification Soft Warnings (Tier 1B, Tier 2 clusters, Tier 3 densité)
        elif iss_type in ("tier1-clarity", "tier2", "tier3", "tier3-phrase",
                          "tier3-phrase-cluster", "filler", "hollow-intensifier",
                          "template-phrase", "sycophantic"):
            soft_warnings.append({
                "type": f"Soft Warning ({iss_type})",
                "line": line_num,
                "term": iss_text,
                "suggestion": iss_sug
            })

    # Normalisation reportée dans les stats de detect.js
    stats = raw_result.get("stats", {})
    norm_info = stats.get("normalization", {})
    if norm_info.get("zeroWidth", 0) > 0 or norm_info.get("homoglyph", 0) > 0:
        hard_blockers.append({
            "type": "Hard Blocker (Bypass Normalization)",
            "line": 1,
            "term": f"zeroWidth: {norm_info.get('zeroWidth')}, homoglyph: {norm_info.get('homoglyph')}",
            "suggestion": "Purger tous les caractères de contournement ZWSP et homoglyphes"
        })

    # Déduplication des alertes par (ligne, terme)
    def dedup_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = set()
        deduped = []
        for it in items:
            key = (it.get("line"), str(it.get("term", "")).lower())
            if key not in seen:
                seen.add(key)
                deduped.append(it)
        return deduped

    hard_blockers = dedup_list(hard_blockers)
    soft_warnings = dedup_list(soft_warnings)

    # Décision du verdict
    has_hard_blockers = len(hard_blockers) > 0
    budget_exceeded = len(soft_warnings) > budget_max

    if has_hard_blockers or budget_exceeded:
        verdict = "FAIL"
    elif len(soft_warnings) > 0:
        verdict = "WARN"
    else:
        verdict = "PASS"

    # Construction du rapport d'erreur en cas de FAIL
    error_report = ""
    if verdict == "FAIL":
        report_lines = [
            f"[AVOID-AI-WRITING] Style Guard Bloquant (Verdict: FAIL)",
            f"Document : {word_count} mots | Langue : {effective_lang.upper()} | Budget Soft Warnings autorisé : {budget_max}",
            f"Hard Blockers (Tolérance 0) : {len(hard_blockers)} | Soft Warnings : {len(soft_warnings)} (Budget max : {budget_max})"
        ]

        if hard_blockers:
            report_lines.append("\n[HARD BLOCKERS DETECTES - TOLERANCE 0] :")
            for hb in hard_blockers:
                report_lines.append(f"  - [Ligne {hb['line']}] {hb['type']} : '{hb['term']}' -> {hb['suggestion']}")

        if budget_exceeded:
            report_lines.append(f"\n[SOFT WARNINGS HORS-BUDGET ({len(soft_warnings)} > {budget_max})] :")
            for sw in soft_warnings:
                report_lines.append(f"  - [Ligne {sw['line']}] {sw['type']} : '{sw['term']}' -> {sw['suggestion']}")

        report_lines.append("\nVeuillez corriger ces tournures artificielles dans le document avant de régénérer le diff CAS.")
        error_report = "\n".join(report_lines)

    return StyleCheckResult(
        verdict=verdict,
        word_count=word_count,
        budget_max=budget_max,
        hard_blockers=hard_blockers,
        soft_warnings=soft_warnings,
        error_report=error_report,
        detected_language=effective_lang
    )
