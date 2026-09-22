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
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple, Union


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

    def to_iteration_dict(self, iteration: int = 1) -> Dict[str, Any]:
        """Convertit le résultat en dictionnaire d'itération structuré pour le suivi."""
        tb: Dict[str, int] = {}
        for hb in self.hard_blockers:
            t = str(hb.get("type", "Hard Blocker"))
            if "tier1" in t.lower():
                tb["Tier 1"] = tb.get("Tier 1", 0) + 1
            elif "em-dash" in t.lower():
                tb["em-dash"] = tb.get("em-dash", 0) + 1
            elif "transition" in t.lower():
                tb["Transition"] = tb.get("Transition", 0) + 1
            else:
                tb["Hard Blocker"] = tb.get("Hard Blocker", 0) + 1

        for sw in self.soft_warnings:
            t = str(sw.get("type", "Soft Warning"))
            if "tier2" in t.lower():
                tb["Tier 2"] = tb.get("Tier 2", 0) + 1
            elif "tier3" in t.lower():
                tb["Tier 3"] = tb.get("Tier 3", 0) + 1
            else:
                tb["Soft Warning"] = tb.get("Soft Warning", 0) + 1

        total = len(self.hard_blockers) + len(self.soft_warnings)
        return {
            "iteration": iteration,
            "verdict": self.verdict,
            "total_issues": total,
            "hard_blockers": len(self.hard_blockers),
            "soft_warnings": len(self.soft_warnings),
            "tier_breakdown": tb,
            "issues": list(self.hard_blockers) + list(self.soft_warnings)
        }


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


def scan_deterministic_hard_blockers(
    text: str,
    language: str,
    allowed_terms: Optional[set] = None
) -> List[Dict[str, Any]]:
    """
    Exécute un scan déterministe absolu (Tolérance 0) pour :
    - em-dashes ('—', '--')
    - normalisation (ZWSP, homoglyphes cyrilliques/grecs)
    - transitions mécaniques strictes
    - Tier 1A stricts (sauf termes explicitement autorisés par l'utilisateur)
    """
    blockers = []
    lines = text.splitlines()
    in_code_block = False
    terms_whitelist = allowed_terms or set()

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
        if phrase.lower() in terms_whitelist:
            continue
        pattern = rf"\b{re.escape(phrase)}\b"
        matches = list(re.finditer(pattern, masked_text, re.IGNORECASE))
        for m in matches:
            matched_w = m.group(0).lower()
            if matched_w in terms_whitelist:
                continue
            line_num = text[:m.start()].count("\n") + 1
            blockers.append({
                "type": "Hard Blocker: Transition Mécanique",
                "line": line_num,
                "term": m.group(0),
                "suggestion": suggestion
            })

    # 3. Scanner les Tier 1A stricts
    for term, suggestion in TIER1A_TERMS.items():
        if term.lower() in terms_whitelist:
            continue
        pattern = rf"\b{re.escape(term)}\b"
        matches = list(re.finditer(pattern, masked_text, re.IGNORECASE))
        for m in matches:
            matched_w = m.group(0).lower()
            if matched_w in terms_whitelist:
                continue
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
    context_mode: str = "technical",
    allowed_terms: Optional[Union[List[str], set]] = None
) -> StyleCheckResult:
    """
    Point d'entrée principal du Style Guard.
    Évalue le document, applique la classification stricte des alertes et le budget gradué.
    Supporte les exemptions explicites arbitrées par l'auteur (allowed_terms ou DOC_VERSION_ALLOWED_TERMS).
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

    # Détection de désactivation explicite via variable d'environnement
    if os.environ.get("DOC_VERSION_DISABLE_STYLE_GUARD") in ("1", "true", "True"):
        w_cnt = len(re.findall(r"\b\w+\b", text))
        return StyleCheckResult(
            verdict="PASS",
            word_count=w_cnt,
            budget_max=2,
            hard_blockers=[],
            soft_warnings=[],
            detected_language="en"
        )

    # Résolution des termes autorisés / arbitrés par l'utilisateur
    allowed_set = set()
    if allowed_terms:
        for t in allowed_terms:
            if isinstance(t, str) and t.strip():
                allowed_set.add(t.strip().lower())
    env_allowed = os.environ.get("DOC_VERSION_ALLOWED_TERMS", "") or os.environ.get("DOC_VERSION_ALLOW_TERMS", "")
    if env_allowed:
        for t in env_allowed.split(","):
            if t.strip():
                allowed_set.add(t.strip().lower())


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

    # Masquage de la section bibliographique pour éviter les faux positifs sur les titres et actes tiers
    def mask_bib_section(m):
        return m.group(1) + "\n" * m.group(2).count("\n")

    text_for_audit = re.sub(
        r"(^#{1,3}\s+(?:📚\s*)?(?:References|Références|Bibliographie|Bibliography)\b.*?\n)(.*)",
        mask_bib_section,
        text,
        flags=re.DOTALL | re.IGNORECASE | re.MULTILINE
    )

    # 1. Exécution du scan déterministe local
    hard_blockers = scan_deterministic_hard_blockers(text_for_audit, language=effective_lang, allowed_terms=allowed_set)
    soft_warnings = []

    # 2. Exécution du moteur detect.js
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".md", delete=False) as tmp:
        tmp.write(text_for_audit)
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

        # Si le terme détecté fait partie des termes autorisés par l'utilisateur
        if allowed_set and (iss_text.lower() in allowed_set or any(re.search(rf"\b{re.escape(a)}\b", iss_text, re.I) for a in allowed_set)):
            continue

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


def format_style_audit_summary(audit_data: Any) -> str:
    """
    Formate le libellé synthétique d'audit de style pour le tableau des commits :
    Ex:
    - '2 itérations (T1: 3 pb ➔ T2: 0 pb - PASS)'
    - '1 tour (0 pb - Conforme)'
    - 'N/A (commit Overleaf)'
    """
    if not audit_data:
        return "N/A"

    if isinstance(audit_data, str):
        return audit_data.strip()

    if isinstance(audit_data, dict):
        if audit_data.get("summary"):
            return str(audit_data["summary"]).strip()
        if audit_data.get("is_overleaf"):
            return "N/A (commit Overleaf)"

        iterations = audit_data.get("iterations", [])
        if not iterations:
            final_v = audit_data.get("final_verdict") or audit_data.get("verdict")
            if final_v == "PASS":
                return "1 tour (0 pb - Conforme)"
            return "N/A"

        k = len(iterations)
        if k == 1:
            it0 = iterations[0]
            total = it0.get("total_issues", 0)
            verdict = it0.get("verdict", "PASS")
            if total == 0 or verdict == "PASS":
                return "1 tour (0 pb - Conforme)"
            else:
                tb = it0.get("tier_breakdown", {})
                if tb:
                    tb_items = [f"{k}: {v}" for k, v in tb.items()]
                    return f"1 tour ({total} pb ({', '.join(tb_items)}) - {verdict})"
                return f"1 tour ({total} pb - {verdict})"
        else:
            steps = []
            for it in iterations:
                it_num = it.get("iteration", len(steps) + 1)
                total = it.get("total_issues", 0)
                verdict = it.get("verdict", "")
                if total == 0 or verdict == "PASS":
                    steps.append(f"T{it_num}: 0 pb - PASS")
                else:
                    tb = it.get("tier_breakdown", {})
                    if tb:
                        tb_items = [f"{k}: {v}" for k, v in tb.items()]
                        steps.append(f"T{it_num}: {total} pb ({', '.join(tb_items)})")
                    else:
                        steps.append(f"T{it_num}: {total} pb")
            return f"{k} itérations (" + " ➔ ".join(steps) + ")"

    return "N/A"


def save_style_audit(
    commit_id: str,
    audit_data: Dict[str, Any],
    target: Optional[str] = None,
    storage_dir: Optional[Path] = None
) -> None:
    """
    Sauvegarde l'audit de style pour un commit_id de manière persistante.
    1. Dans storage_dir / style_audit.json (ou CAS par défaut).
    2. Dans .doc_version / style_audit.json du projet si le dossier .doc_version existe.
    3. Met à jour le commit json dans commits/<commit_id>.json s'il existe.
    """
    if not commit_id:
        raise ValueError("commit_id ne peut pas être vide pour enregistrer l'audit de style.")

    # 1. Résolution du storage_dir
    cas_dir = None
    if storage_dir is not None:
        cas_dir = Path(storage_dir)
    else:
        env_dir = os.environ.get("DOC_VERSION_COMMITS_DIR")
        if env_dir:
            cas_dir = Path(env_dir)
        else:
            default_cas = Path.home() / ".gemini" / "antigravity" / "cas_commits"
            if default_cas.exists():
                cas_dir = default_cas
            else:
                cas_dir = Path(tempfile.gettempdir()) / "doc_version_commits"

    if cas_dir:
        cas_dir.mkdir(parents=True, exist_ok=True)
        audit_file = cas_dir / "style_audit.json"
        store: Dict[str, Any] = {"commits": {}}
        if audit_file.exists():
            try:
                store = json.loads(audit_file.read_text(encoding="utf-8"))
                if "commits" not in store:
                    store["commits"] = {}
            except Exception:
                store = {"commits": {}}
        store["commits"][commit_id] = audit_data
        tmp_f = cas_dir / f"audit_{os.getpid()}_{datetime.now().timestamp()}.tmp"
        tmp_f.write_text(json.dumps(store, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_f.replace(audit_file)

        # Si le commit JSON existe dans commits/, mise à jour directe
        commit_f = cas_dir / "commits" / f"{commit_id}.json"
        if not commit_f.exists():
            matches = list((cas_dir / "commits").glob(f"{commit_id}*.json"))
            if len(matches) == 1:
                commit_f = matches[0]
        if commit_f.exists():
            try:
                c_data = json.loads(commit_f.read_text(encoding="utf-8"))
                c_data["style_audit"] = audit_data
                commit_f.write_text(json.dumps(c_data, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception:
                pass

    # 2. Persistance locale dans .doc_version si présent
    if target:
        tp = Path(target)
        target_dir = tp.parent if (tp.is_file() or not tp.exists()) else tp
        local_doc_ver = None
        for cand in [target_dir / ".doc_version", target_dir.parent / ".doc_version"]:
            if cand.exists():
                local_doc_ver = cand
                break
        if local_doc_ver and local_doc_ver.exists():
            loc_audit_f = local_doc_ver / "style_audit.json"
            loc_store: Dict[str, Any] = {"commits": {}}
            if loc_audit_f.exists():
                try:
                    loc_store = json.loads(loc_audit_f.read_text(encoding="utf-8"))
                    if "commits" not in loc_store:
                        loc_store["commits"] = {}
                except Exception:
                    loc_store = {"commits": {}}
            loc_store["commits"][commit_id] = audit_data
            tmp_loc = local_doc_ver / f"audit_{os.getpid()}_{datetime.now().timestamp()}.tmp"
            tmp_loc.write_text(json.dumps(loc_store, indent=2, ensure_ascii=False), encoding="utf-8")
            tmp_loc.replace(loc_audit_f)


def load_style_audit(
    commit_id: str,
    target: Optional[str] = None,
    storage_dir: Optional[Path] = None
) -> Optional[Dict[str, Any]]:
    """
    Charge l'audit de style pour un commit_id (ou préfixe de commit).
    """
    if not commit_id:
        return None

    # 1. Vérifier local .doc_version si target
    if target:
        tp = Path(target)
        target_dir = tp.parent if (tp.is_file() or not tp.exists()) else tp
        for cand_dir in [target_dir / ".doc_version", target_dir.parent / ".doc_version"]:
            if cand_dir.exists():
                loc_audit_f = cand_dir / "style_audit.json"
                if loc_audit_f.exists():
                    try:
                        data = json.loads(loc_audit_f.read_text(encoding="utf-8"))
                        commits = data.get("commits", {})
                        if commit_id in commits:
                            return commits[commit_id]
                        for cid, audit in commits.items():
                            if cid.startswith(commit_id) or commit_id.startswith(cid):
                                return audit
                    except Exception:
                        pass

    # 2. Vérifier storage_dir
    cas_dir = None
    if storage_dir is not None:
        cas_dir = Path(storage_dir)
    else:
        env_dir = os.environ.get("DOC_VERSION_COMMITS_DIR")
        if env_dir:
            cas_dir = Path(env_dir)
        else:
            default_cas = Path.home() / ".gemini" / "antigravity" / "cas_commits"
            if default_cas.exists():
                cas_dir = default_cas
            else:
                cas_dir = Path(tempfile.gettempdir()) / "doc_version_commits"

    if cas_dir:
        audit_file = cas_dir / "style_audit.json"
        if audit_file.exists():
            try:
                store = json.loads(audit_file.read_text(encoding="utf-8"))
                commits = store.get("commits", {})
                if commit_id in commits:
                    return commits[commit_id]
                for cid, audit in commits.items():
                    if cid.startswith(commit_id) or commit_id.startswith(cid):
                        return audit
            except Exception:
                pass

        # Vérifier dans le commit JSON lui-même
        commit_f = cas_dir / "commits" / f"{commit_id}.json"
        if not commit_f.exists():
            matches = list((cas_dir / "commits").glob(f"{commit_id}*.json"))
            if len(matches) == 1:
                commit_f = matches[0]
        if commit_f.exists():
            try:
                c_data = json.loads(commit_f.read_text(encoding="utf-8"))
                if c_data.get("style_audit"):
                    return c_data["style_audit"]
            except Exception:
                pass

    return None


def check_is_overleaf_commit(
    repo_root: Optional[Path],
    commit_id: str,
    upstream_id: Optional[str] = None
) -> bool:
    """Détecte si un commit provient du dépôt Overleaf distant."""
    if not repo_root or not commit_id:
        return False
    try:
        res_remote = subprocess.run(
            ["git", "-C", str(repo_root), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=5
        )
        if res_remote.returncode != 0 or "overleaf.com" not in res_remote.stdout:
            return False

        target_ref = upstream_id if upstream_id else "origin/main"
        res_anc = subprocess.run(
            ["git", "-C", str(repo_root), "merge-base", "--is-ancestor", commit_id, target_ref],
            capture_output=True, text=True, timeout=5
        )
        return res_anc.returncode == 0
    except Exception:
        return False

