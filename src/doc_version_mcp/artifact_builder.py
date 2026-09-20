"""
artifact_builder.py — Assemblage normé d'artéfacts Markdown Antigravity avec badges Anti-IA, Tree TOC et conciliation collaborative.
"""

import re
import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple


def format_ai_score_badge(score_before: Optional[float], score_after: Optional[float]) -> str:
    """
    Génère un badge pill HTML compatible avec les styles du chat Antigravity et d'Obsidian :
    - Vert/Emerald si score_after <= 10.0% : Conforme (< 10%)
    - Ambre si score_after entre 10.0% et 30.0%
    - Rouge si score_after > 30.0%
    """
    if score_before is not None and score_after is not None:
        delta = score_after - score_before
        delta_sign = '+' if delta > 0 else ''
        delta_str = f"{delta_sign}{delta:.1f}%"
        evolution_text = f"🛡️ Score IA : {score_before:.1f}% ➔ {score_after:.1f}% ({delta_str})"
        ref_score = score_after
    elif score_after is not None:
        evolution_text = f"🛡️ Score IA : {score_after:.1f}%"
        ref_score = score_after
    elif score_before is not None:
        evolution_text = f"🛡️ Score IA : {score_before:.1f}% (Supprimé)"
        ref_score = score_before
    else:
        return ""

    if ref_score <= 10.0:
        style = 'display:inline-block;margin-top:6px;padding:2px 8px;border-radius:4px;font-size:0.78rem;font-weight:500;background-color:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;'
        mention = ' — ✅ Conforme (&lt; 10%)'
    elif ref_score <= 30.0:
        style = 'display:inline-block;margin-top:6px;padding:2px 8px;border-radius:4px;font-size:0.78rem;font-weight:500;background-color:#fffbeb;color:#b45309;border:1px solid #fde68a;'
        mention = ''
    else:
        style = 'display:inline-block;margin-top:6px;padding:2px 8px;border-radius:4px;font-size:0.78rem;font-weight:500;background-color:#fef2f2;color:#b91c1c;border:1px solid #fecaca;'
        mention = ''

    return f'<span style="{style}">{evolution_text}{mention}</span>'


def clean_prose_for_ai_detection(text: str) -> str:
    """
    Extrait et nettoie la prose propre d'un fragment textuel avant soumission à ai_detector.py.
    Élimine rigoureusement :
    - Balises HTML (<span...>, <del...>, <ins...>, etc.)
    - Environnements structuraux LaTeX (\\begin{minipage}...\\end{minipage}, \\begin{center}, etc.)
    - Commandes de mise en page et polices LaTeX (\\fontsize{...}{...}, \\selectfont, \\vspace, \\hspace, \\setlength, etc.)
    - Macros, citations et labels (\\cite{...}, \\label{...}, \\ref{...}, \\item, etc.)
    - Blocs mathématiques et symboles LaTeX ($...$, $$...$$, \\[...\\])
    - Accolades et commandes résiduelles
    """
    if not text or not text.strip():
        return ""

    from .diff_engine import DiffEngine

    # 1. Suppression des balises HTML
    cleaned = re.sub(r'<[^>]+>', ' ', text)

    # 2. Nettoyage via les règles de base de DiffEngine
    cleaned = DiffEngine.clean_residual_latex(cleaned)

    # 3. Élimination exhaustive des environnements de mise en page LaTeX
    layout_envs = (
        r'minipage|center|flushleft|flushright|abstract|quote|quotation|verse|'
        r'figure|table|tabular|table\*|figure\*|tikzpicture|tcolorbox'
    )
    cleaned = re.sub(rf'\\begin\{{(?:{layout_envs})\}}.*?(?:\\end\{{(?:{layout_envs})\}}|$)', ' ', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\\(?:begin|end)\{[^}]+\}', ' ', cleaned)

    # Commandes de taille, police et mise en forme
    cleaned = re.sub(r'\\fontsize\{[^{}]*\}\{[^{}]*\}\s*(?:\\selectfont)?', ' ', cleaned)
    cleaned = re.sub(r'\\selectfont\b', ' ', cleaned)
    cleaned = re.sub(r'\\(?:small|footnotesize|scriptsize|normalsize|large|Large|LARGE|huge|Huge)\b', ' ', cleaned)
    cleaned = re.sub(r'\\(?:normalfont|bfseries|itshape|slshape|scshape|sffamily|ttfamily|rmfamily)\b', ' ', cleaned)

    # Dimensions, espacements et règles
    cleaned = re.sub(r'\\(?:vspace|hspace|setlength|addtolength)\*?\{[^}]*\}(?:\{[^}]*\})?', ' ', cleaned)
    cleaned = re.sub(r'\\(?:textwidth|linewidth|columnsep|columnwidth|parindent|parskip)\b', ' ', cleaned)
    cleaned = re.sub(r'\\(?:centering|noindent|frenchspacing|medskip|bigskip|smallskip|clearpage|newpage|vfill|hfill|raggedleft|raggedright)\b', ' ', cleaned)
    cleaned = re.sub(r'\\(?:toprule|midrule|bottomrule|hline|addlinespace|cmidrule(?:\[[^\]]*\])?\{[^}]*\})', ' ', cleaned)
    cleaned = re.sub(r'\\(?:rule|hrule)(?:\[[^\]]*\])?\{[^{}]*\}\{[^{}]*\}', ' ', cleaned)

    # Macros, citations, labels, refs
    cleaned = re.sub(r'\\(?:cite|citep|citet|ref|eqref|label|pageref|nocite)\*?(?:\[[^\]]*\])?\{[^}]*\}', ' ', cleaned)
    cleaned = re.sub(r'\\(?:item|caption|footnote)\*?(?:\[[^\]]*\])?', ' ', cleaned)
    cleaned = re.sub(r'\\(?:title|author|affiliation|institution|email|date|def|newcommand|renewcommand)\{[^}]*\}', ' ', cleaned)

    # Maths $...$, $$...$$, \\[...\\]
    cleaned = re.sub(r'\$\$.*?\$\$', ' ', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'\\\[.*?\\\]', ' ', cleaned, flags=re.DOTALL)
    cleaned = re.sub(r'(?<!\\)\$(.*?)(?<!\\)\$', ' ', cleaned)

    # Commandes LaTeX résiduelles \\cmd
    cleaned = re.sub(r'\\[a-zA-Z]+', ' ', cleaned)

    # Accolades isolées et nettoyages de ponctuation résiduelle
    cleaned = re.sub(r'[{}]', ' ', cleaned)
    cleaned = re.sub(r'[ \t]{2,}', ' ', cleaned)
    cleaned = re.sub(r'\n{2,}', '\n', cleaned)

    return cleaned.strip()


def resolve_ai_detector_path() -> Path:
    """
    Localise le script canonique ai_detector.py selon la doctrine Fail-Fast.
    Lève immédiatement FileNotFoundError si introuvable.
    """
    env_path = os.environ.get("AI_DETECTOR_PATH")
    if env_path:
        p = Path(env_path)
        if p.is_file():
            return p.resolve()
        raise FileNotFoundError(
            f"❌ [FAIL-FAST] Script 'ai_detector.py' spécifié dans AI_DETECTOR_PATH introuvable : '{env_path}'."
        )

    candidates = [
        Path(r"C:\Users\Jamet\Documents\VoiceNotes\_agents\scripts-for-skills\ai_detector.py"),
        Path.home() / "Documents" / "VoiceNotes" / "_agents" / "scripts-for-skills" / "ai_detector.py",
        Path(__file__).resolve().parents[3] / "VoiceNotes" / "_agents" / "scripts-for-skills" / "ai_detector.py"
    ]

    for cand in candidates:
        if cand.is_file():
            return cand.resolve()

    raise FileNotFoundError(
        f"❌ [FAIL-FAST] Script canonique 'ai_detector.py' introuvable.\n"
        f"Emplacements vérifiés : {[str(c) for c in candidates]}.\n"
        f"Le score IA ne peut pas être simulé conformément aux directives Fail-Fast d'Henri."
    )


def resolve_ai_detector_python() -> Path:
    """
    Localise l'interpréteur Python configuré avec PyTorch et CUDA selon la doctrine Fail-Fast.
    Lève immédiatement RuntimeError si introuvable.
    """
    env_py = os.environ.get("AI_DETECTOR_PYTHON")
    if env_py:
        p = Path(env_py)
        if p.is_file():
            return p.resolve()
        raise RuntimeError(
            f"❌ [FAIL-FAST] Interpréteur spécifié dans AI_DETECTOR_PYTHON introuvable : '{env_py}'."
        )

    # 1. Vérification dans l'interpréteur courant
    try:
        import torch  # type: ignore # noqa: F401
        return Path(sys.executable).resolve()
    except ImportError:
        pass

    # 2. Interpréteurs canoniques PyTorch CUDA du système
    candidates = [
        Path(r"C:\Users\Jamet\.pyenv\pyenv-win\versions\3.11.9\python.exe"),
        Path.home() / ".pyenv" / "pyenv-win" / "versions" / "3.11.9" / "python.exe",
    ]

    # Détection dynamique dans pyenv
    pyenv_dir = Path.home() / ".pyenv" / "pyenv-win" / "versions"
    if pyenv_dir.is_dir():
        for sub in pyenv_dir.iterdir():
            p_exe = sub / "python.exe"
            if p_exe.is_file() and p_exe not in candidates:
                candidates.append(p_exe)

    for cand in candidates:
        if cand.is_file():
            return cand.resolve()

    # Repli sur shutil.which("python") hors venv si présent
    sys_py = shutil.which("python")
    if sys_py:
        p_which = Path(sys_py).resolve()
        if p_which != Path(sys.executable).resolve():
            return p_which

    raise RuntimeError(
        f"❌ [FAIL-FAST] Aucun interpréteur Python équipé de PyTorch/CUDA n'a été trouvé pour exécuter ai_detector.py.\n"
        f"Candidats testés : {[str(c) for c in candidates]}.\n"
        f"Veuillez définir la variable AI_DETECTOR_PYTHON ou installer PyTorch dans l'environnement."
    )


def estimate_ai_score(text: str) -> float:
    """
    Calcule le score de probabilité IA P(AI) en pourcentage [0.0 - 100.0] via ai_detector.py.
    Doctrine Fail-Fast absolue d'Henri :
    - Débarrasse intégralement le texte des commandes et balises LaTeX de mise en page.
    - Appelle le véritable moteur SOTA ai_detector.py (Gemma-4-E2B Binoculars, DeBERTa RAID, etc.).
    - Zéro fallback heuristique silencieux, zéro score factice codé en dur (les 5.0% sont éradiqués).
    - Tout échec (script introuvable, GPU/dépendance manquante, crash d'inférence) lève immédiatement une exception explicite.
    """
    clean_text = clean_prose_for_ai_detection(text)
    words = re.findall(r'\b[a-zA-ZÀ-ÿ-]+\b', clean_text)
    if not clean_text or len(words) == 0:
        raise ValueError("❌ [FAIL-FAST] Impossible de calculer le score IA sur un segment vide ou dépourvu de prose.")

    detector_script = resolve_ai_detector_path()

    # Si l'environnement courant possède PyTorch et peut exécuter directement ai_detector en mémoire
    try:
        import torch  # type: ignore # noqa: F401
        import importlib.util

        spec = importlib.util.spec_from_file_location("ai_detector", str(detector_script))
        if spec and spec.loader:
            ai_mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(ai_mod)
            res = ai_mod.analyze_text(
                clean_text,
                device_override="auto",
                allow_partial=False,
                offline=False,
                keep_loaded=True
            )
            return float(res["global_score"]["p_ai_percent"])
    except ImportError:
        # PyTorch n'est pas dans l'environnement courant (cas normal dans le venv doc-version-mcp)
        pass
    except Exception as e:
        # En cas d'erreur lors de l'exécution interne directe, lève immédiatement l'exception Fail-Fast
        raise RuntimeError(f"❌ [FAIL-FAST] Erreur lors de l'exécution in-memory de ai_detector : {e}") from e

    # Exécution via l'interpréteur Python système équipé de PyTorch / CUDA
    python_exe = resolve_ai_detector_python()
    clean_env = os.environ.copy()
    clean_env.pop("VIRTUAL_ENV", None)
    clean_env.pop("PYTHONHOME", None)
    clean_env.pop("PYTHONPATH", None)

    cmd = [
        str(python_exe),
        str(detector_script),
        "--device", "auto",
        "--json"
    ]

    proc = subprocess.run(
        cmd,
        input=clean_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=clean_env,
        check=False
    )

    if proc.returncode != 0:
        raise RuntimeError(
            f"❌ [FAIL-FAST] Échec d'exécution de ai_detector.py (code {proc.returncode}) :\n"
            f"STDERR :\n{proc.stderr}\nSTDOUT :\n{proc.stdout}"
        )

    try:
        data = json.loads(proc.stdout)
        return float(data["global_score"]["p_ai_percent"])
    except (KeyError, ValueError, json.JSONDecodeError) as e:
        raise RuntimeError(
            f"❌ [FAIL-FAST] Réponse JSON invalide reçue de ai_detector.py : {e}\n"
            f"STDOUT brut :\n{proc.stdout}"
        ) from e


def extract_paragraph_diff_texts(para: str) -> Tuple[str, str]:
    """
    Extrait text_before (texte d'origine sans ajouts) et text_after (texte révisé sans suppressions)
    d'un paragraphe contenant des balises de diff inline.
    """
    cleaned = re.sub(
        r'(?:^>*\s*)?<span\b[^>]*>(?:🛡️|🚨|⚠️)\s*(?:Score IA|P\(AI\))\s*:?.*?</span>\s*',
        '',
        para,
        flags=re.MULTILINE
    )

    # tb : Baseline avant modification
    tb = cleaned
    tb = re.sub(r'<ins\b[^>]*>.*?</ins>', '', tb, flags=re.DOTALL)
    tb = re.sub(r'<span\b[^>]*style="[^"]*#dcfce7[^"]*"[^>]*>.*?</span>', '', tb, flags=re.DOTALL)
    tb = re.sub(r'<span\b[^>]*#dcfce7[^>]*>.*?</span>', '', tb, flags=re.DOTALL)
    tb = re.sub(r'<del\b[^>]*>(.*?)</del>', r'\1', tb, flags=re.DOTALL)
    tb = re.sub(r'<span\b[^>]*style="[^"]*#fee2e2[^"]*"[^>]*>(.*?)</span>', r'\1', tb, flags=re.DOTALL)
    tb = re.sub(r'<span\b[^>]*#fee2e2[^>]*>(.*?)</span>', '', tb, flags=re.DOTALL)
    tb = re.sub(r'</?(?:span|del|ins|br)\b[^>]*>', '', tb)
    tb = re.sub(r'(?m)^\s*(?:[-*+]|\d+\.)\s*$', '', tb)
    tb = re.sub(r'\n+', ' ', tb)
    tb = re.sub(r'[ \t]{2,}', ' ', tb).strip()

    # ta : Révision après modification
    ta = cleaned
    ta = re.sub(r'<del\b[^>]*>.*?</del>', '', ta, flags=re.DOTALL)
    ta = re.sub(r'<span\b[^>]*style="[^"]*#fee2e2[^"]*"[^>]*>.*?</span>', '', ta, flags=re.DOTALL)
    ta = re.sub(r'<span\b[^>]*#fee2e2[^>]*>(.*?)</span>', '', ta, flags=re.DOTALL)
    ta = re.sub(r'<ins\b[^>]*>(.*?)</ins>', r'\1', ta, flags=re.DOTALL)
    ta = re.sub(r'<span\b[^>]*style="[^"]*#dcfce7[^"]*"[^>]*>(.*?)</span>', r'\1', ta, flags=re.DOTALL)
    ta = re.sub(r'<span\b[^>]*#dcfce7[^>]*>(.*?)</span>', '', ta, flags=re.DOTALL)
    ta = re.sub(r'</?(?:span|del|ins|br)\b[^>]*>', '', ta)
    ta = re.sub(r'(?m)^\s*(?:[-*+]|\d+\.)\s*$', '', ta)
    ta = re.sub(r'\n+', ' ', ta)
    ta = re.sub(r'[ \t]{2,}', ' ', ta).strip()

    return tb, ta


def attach_badge_to_block(block: str, badge: str) -> str:
    """Attache le badge HTML sous le bloc Markdown en respectant les citations ou listes."""
    lines = block.splitlines()
    if not lines:
        return block
    if all(l.strip().startswith('>') for l in lines):
        return f"{block}\n>\n> {badge}"
    if re.match(r'^\s*[-*+]\s+', block) or re.match(r'^\s*\d+\.\s+', block):
        return f"{block}\n  {badge}"
    return f"{block}\n\n{badge}"


def attach_ai_score_badges(
    annotated_body: str,
    enable_ai_score: bool = True
) -> Tuple[str, int, Optional[float], Optional[float]]:
    """
    Analyse les blocs de texte modifiés, calcule les scores IA avant/après et attache
    les badges pill HTML. Retourne (updated_body, badges_count, score_before_avg, score_after_avg).
    """
    if not enable_ai_score or not annotated_body:
        return annotated_body, 0, None, None

    blocks = re.split(r'(\n\s*\n+)', annotated_body)
    badges_applied = 0
    all_scores_b: List[float] = []
    all_scores_a: List[float] = []

    for idx in range(0, len(blocks), 2):
        block = blocks[idx]
        if re.match(r'^\s*#{1,6}\s', block):
            continue
        if re.match(r'^\s*>\s*\[!', block):
            continue
        if block.strip().startswith('<!--') or block.strip().startswith('```') or block.strip().startswith('<style'):
            continue
        if block.strip().startswith('|') and '|' in block.strip()[1:]:
            continue

        has_diff = any(tag in block for tag in ('<del', '<ins', '#fee2e2', '#dcfce7'))
        if not has_diff:
            continue

        tb, ta = extract_paragraph_diff_texts(block)
        clean_tb = clean_prose_for_ai_detection(tb)
        clean_ta = clean_prose_for_ai_detection(ta)

        wb = len(re.findall(r'\b[a-zA-ZÀ-ÿ-]+\b', clean_tb))
        wa = len(re.findall(r'\b[a-zA-ZÀ-ÿ-]+\b', clean_ta))

        if wb < 5 and wa < 5:
            continue

        score_b = estimate_ai_score(clean_tb) if wb >= 5 else None
        score_a = estimate_ai_score(clean_ta) if wa >= 5 else None

        if score_b is not None:
            all_scores_b.append(score_b)
        if score_a is not None:
            all_scores_a.append(score_a)

        badge_html = format_ai_score_badge(score_b, score_a)
        if badge_html:
            blocks[idx] = attach_badge_to_block(block, badge_html)
            badges_applied += 1

    updated_body = "".join(blocks)
    avg_b = (sum(all_scores_b) / len(all_scores_b)) if all_scores_b else None
    avg_a = (sum(all_scores_a) / len(all_scores_a)) if all_scores_a else None

    return updated_body, badges_applied, avg_b, avg_a


class ArtifactBuilder:
    """Constructeur d'artéfacts Markdown Antigravity et de notes de synchronisation Obsidian."""

    DIFF_SUMMARY_HEADER = "## 🔄 Synthèse des Changements & Diffs Récents"

    @classmethod
    def inject_explanation_callout(cls, body: str, explanation: str) -> str:
        """
        Injecte le callout de conciliation collaborative tout en haut de la note,
        juste après le frontmatter YAML et les métadonnées d'en-tête s'ils existent.
        """
        if not explanation or not explanation.strip():
            return body

        lines = explanation.strip().splitlines()
        callout_lines = [
            "> [!NOTE]",
            "> **🔄 Synthèse des Travaux Récents & Conciliation Collaborative**",
            ">"
        ]
        for l in lines:
            if l.strip():
                callout_lines.append(f"> {l}")
            else:
                callout_lines.append(">")
        callout_str = "\n".join(callout_lines) + "\n\n"

        pattern = r'>\s*\[!NOTE\]\s*\n>\s*\*\*🔄\s*Synthèse des Travaux Récents & Conciliation Collaborative\*\*.*?(?=(?:\n(?!>))|\Z)'
        clean_body = re.sub(pattern, '', body, flags=re.DOTALL)
        clean_body = re.sub(r'\n{3,}', '\n\n', clean_body).strip()

        fm_match = re.match(r'^(---\n.*?\n---\n*)', clean_body, re.DOTALL)
        if fm_match:
            frontmatter_part = fm_match.group(1).rstrip() + "\n\n"
            rest = clean_body[fm_match.end():].lstrip()
            meta_match = re.match(r'^((?:<!--.*?-->\n*)+)', rest, re.DOTALL)
            if meta_match:
                meta_part = meta_match.group(1).rstrip() + "\n\n"
                content_after = rest[meta_match.end():].lstrip()
                return f"{frontmatter_part}{meta_part}{callout_str}{content_after}"
            else:
                return f"{frontmatter_part}{callout_str}{rest}"
        else:
            meta_match = re.match(r'^((?:<!--.*?-->\n*)+)', clean_body, re.DOTALL)
            if meta_match:
                meta_part = meta_match.group(1).rstrip() + "\n\n"
                content_after = clean_body[meta_match.end():].lstrip()
                return f"{meta_part}{callout_str}{content_after}"
            else:
                return f"{callout_str}{clean_body}"

    @classmethod
    def build_artifact_header(
        cls,
        target_name: str,
        source_file: Optional[str] = None,
        baseline_commit: Optional[str] = None,
        image_rel: Optional[str] = None
    ) -> str:
        """Construit le bloc YAML frontmatter et métadonnées HTML en tête d'artéfact."""
        parts = []
        if image_rel:
            parts.append(f"---\nImage: \"[[{image_rel}]]\"\n---\n")

        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        slug = re.sub(r'[^a-zA-Z0-9_]+', '_', target_name).upper()
        meta = [f"<!-- ARTIFACT: {slug}_MANUSCRIPT -->"]
        if source_file:
            meta.append(f"<!-- SOURCE_FILE: {source_file} -->")
        if baseline_commit:
            meta.append(f"<!-- BASELINE_COMMIT: {baseline_commit[:8]} -->")
        meta.append(f"<!-- Generated at: {now_str} -->\n")
        meta.append("<style>\nins { text-decoration: none !important; -webkit-text-decoration: none !important; text-decoration-line: none !important; }\ndel { text-decoration: line-through !important; }\n</style>\n\n")

        parts.append("\n".join(meta))
        return "".join(parts)

    @classmethod
    def build_recent_commits_table(
        cls,
        commits: Optional[List[Dict[str, Any]]] = None,
        limit: int = 5
    ) -> str:
        """
        Génère le tableau Markdown canonique des N derniers commits CAS :
        | Commit ID | Date | Auteur | Message / Titre |
        """
        if not commits:
            return ""

        rows = [
            "### 🕒 Historique Récent (5 Derniers Commits)\n",
            "| Commit ID | Date | Auteur | Message / Titre |",
            "| :--- | :--- | :--- | :--- |"
        ]

        for c in commits[:limit]:
            c_id = c.get("commit_id", "")
            short_id = f"`{c_id[:8]}`" if c_id else "`—`"
            raw_ts = c.get("timestamp", "")
            formatted_date = raw_ts
            if raw_ts:
                try:
                    dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
                    formatted_date = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                except Exception:
                    formatted_date = raw_ts[:19].replace("T", " ")

            author = str(c.get("author", "agent")).replace("|", "\\|")
            msg = str(c.get("message", "")).replace("|", "\\|").strip()
            rows.append(f"| {short_id} | {formatted_date} | {author} | {msg} |")

        return "\n".join(rows) + "\n\n---\n\n"

    @classmethod
    def assemble_brain_artifact(
        cls,
        target_name: str,
        annotated_body: str,
        tree_toc: str,
        diff_count: int,
        diff_explanation: str = "",
        source_file: Optional[str] = None,
        baseline_commit: Optional[str] = None,
        image_rel: Optional[str] = None,
        recent_commits: Optional[List[Dict[str, Any]]] = None,
        enable_ai_score: bool = True,
        final_content: Optional[str] = None,
        mode: str = "paper"
    ) -> str:
        """Assemble l'artéfact complet destiné à Antigravity Brain."""
        header = cls.build_artifact_header(
            target_name=target_name,
            source_file=source_file,
            baseline_commit=baseline_commit,
            image_rel=image_rel
        )

        doc_title = target_name.replace('_', ' ').upper()
        exp_note = f">\n> 💬 **Note de révision :** {diff_explanation.strip()}\n>" if diff_explanation.strip() else ""

        # 1. Attacher les badges pill de score IA sous chaque paragraphe modifié
        processed_body, badges_count, avg_b, avg_a = attach_ai_score_badges(
            annotated_body=annotated_body,
            enable_ai_score=enable_ai_score
        )

        # 2. Préparer le badge global pour le sommaire/header si des scores sont calculés
        global_ai_badge = ""
        if avg_a is not None or avg_b is not None:
            badge_span = format_ai_score_badge(avg_b, avg_a)
            global_ai_badge = f">\n> 🛡️ **Conformité Anti-IA :** {badge_span}\n>"

        if diff_count > 0:
            diff_block = (
                f"{cls.DIFF_SUMMARY_HEADER}\n\n"
                f"> [!IMPORTANT]\n"
                f"> **🌳 Arborescence des Modifications Détectées ({diff_count} deltas) :**\n"
                f"{exp_note}\n"
                f"> 📂 **{doc_title}**<br>\n"
                f"{tree_toc}\n"
                f"{global_ai_badge}\n\n"
                f"---\n\n"
            )
        else:
            diff_block = (
                f"## 📑 Structure & Sommaire AST du Manuscrit\n\n"
                f"> [!NOTE]\n"
                f"> **🌳 Arborescence des Sections AST (État Actuel) :**\n"
                f"{exp_note}\n"
                f"> 📂 **{doc_title}**<br>\n"
                f"{tree_toc}\n"
                f"{global_ai_badge}\n\n"
                f"---\n\n"
            )

        # 3. Tableau des 5 derniers commits CAS
        commits_block = cls.build_recent_commits_table(recent_commits, limit=5)

        # 4. Bloc dépliant de texte final prêt à copier (mode draft)
        copy_block = ""
        if mode == "draft" and final_content and final_content.strip():
            copy_block = (
                f"<details><summary>📋 Texte Final Prêt à Copier</summary>\n\n"
                f"```text\n"
                f"{final_content.strip()}\n"
                f"```\n"
                f"</details>\n\n"
                f"---\n\n"
            )

        full_doc = f"{header}{copy_block}{diff_block}{commits_block}{processed_body.rstrip()}\n"
        if diff_explanation.strip():
            full_doc = cls.inject_explanation_callout(full_doc, diff_explanation.strip())

        return full_doc

    @classmethod
    def format_images_for_brain(
        cls,
        markdown_text: str,
        brain_target_dir: Path
    ) -> str:
        """Normalise les images Markdown pour pointer en URL file:/// vers le dossier brain."""
        b_posix = brain_target_dir.resolve().as_posix().lstrip('/')

        def repl_wikilink(m):
            inner = m.group(1).strip()
            parts = inner.split('|')
            img_path = parts[0].strip()
            img_name = Path(img_path).name
            alt = parts[1].strip() if len(parts) > 1 else Path(img_name).stem.replace('_', ' ')
            return f"\n\n![{alt}](file:///{b_posix}/{img_name})\n\n"

        def repl_md(m):
            alt = m.group(1).strip()
            src = m.group(2).strip()
            clean_src = re.sub(r'^file:///?', '', src).split('?')[0].split('#')[0]
            img_name = Path(clean_src).name
            return f"\n\n![{alt}](file:///{b_posix}/{img_name})\n\n"

        text = re.sub(r'!\[\[(.*?)\]\]', repl_wikilink, markdown_text)
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', repl_md, text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text
