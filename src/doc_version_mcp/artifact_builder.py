"""
artifact_builder.py — Assemblage normé d'artéfacts Markdown Antigravity avec badges Anti-IA, Tree TOC et conciliation collaborative.
"""

import re
import math
import shutil
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from typing import Dict, List, Optional, Any, Tuple


AI_BUZZWORDS = {
    "delve", "delves", "delving", "tapestry", "crucial", "testament",
    "foster", "fostering", "paramount", "pivotal", "underscores",
    "beacon", "unwavering", "rich", "intricate", "vital", "multifaceted",
    "holistic", "seamless", "seamlessly", "furthermore", "moreover",
    "in conclusion", "it is worth noting", "it is important to note",
    "landscape", "realm", "harness", "harnessing", "unleash", "unleashing"
}


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


def calculate_pure_stylometric_score(text: str, words: List[str]) -> float:
    """Calcule une estimation stylométrique rapide de la probabilité IA (0 à 100%)."""
    sentences = [s.strip() for s in re.split(r'[.!?]+', text) if s.strip()]
    n_words = len(words)
    if n_words < 6 or not sentences:
        return 5.0

    # 1. Burstiness (variation longueur des phrases)
    sent_lens = [len(re.findall(r'\b[a-zA-ZÀ-ÿ-]+\b', s)) for s in sentences]
    sent_lens = [l for l in sent_lens if l > 0]
    if not sent_lens:
        sent_lens = [n_words]
    mean_len = sum(sent_lens) / len(sent_lens)
    variance = sum((l - mean_len) ** 2 for l in sent_lens) / len(sent_lens)
    cv_len = (math.sqrt(variance) / mean_len) if mean_len > 0 else 0.0

    # 2. Entropie de Shannon
    counts = Counter(words)
    probs = [c / n_words for c in counts.values()]
    word_entropy = -sum(p * math.log2(p) for p in probs)
    max_entropy = math.log2(n_words) if n_words > 1 else 1.0
    norm_entropy = word_entropy / max_entropy if max_entropy > 0 else 1.0

    # 3. Buzzwords IA
    found_buzz = [w for w in words if w in AI_BUZZWORDS]
    text_lower = text.lower()
    for phrase in ["in conclusion", "it is important to note", "it is worth noting"]:
        if phrase in text_lower:
            found_buzz.append(phrase)
    buzzword_ratio = len(found_buzz) / n_words

    # Évaluation stylométrique calibrée
    s_burst = max(0.0, min(1.0, (0.70 - cv_len) / 0.50))
    s_buzz = min(1.0, buzzword_ratio * 40.0)
    s_unif = 1.0 if (14.0 <= mean_len <= 26.0 and cv_len < 0.30) else 0.0
    s_ent = max(0.0, min(1.0, 1.0 - abs(norm_entropy - 0.85) * 5.0)) if cv_len < 0.35 else 0.0

    s_stylo = 0.40 * s_burst + 0.35 * s_buzz + 0.15 * s_unif + 0.10 * s_ent
    s_stylo = max(0.0, min(1.0, s_stylo))
    return float(round(s_stylo * 100.0, 1))


def estimate_ai_score(text: str) -> float:
    """
    Estime la probabilité IA P(AI) en pourcentage [0.0 - 100.0].
    Tente d'utiliser le module SOTA ai_detector s'il est présent, avec repli stylométrique robuste.
    """
    if not text or not text.strip():
        return 0.0

    clean_text = re.sub(r'<[^>]+>', ' ', text).strip()
    words = re.findall(r'\b[a-zA-ZÀ-ÿ-]+\b', clean_text.lower())
    if len(words) < 5:
        return 5.0

    # Tentative d'import dynamique de ai_detector
    try:
        ai_mod = None
        try:
            import ai_detector
            ai_mod = ai_detector
        except ImportError:
            candidates = [
                Path(r"C:\Users\hjamet\Documents\VoiceNotes\_agents\scripts\ai_detector.py"),
                Path.home() / "Documents" / "VoiceNotes" / "_agents" / "scripts" / "ai_detector.py",
            ]
            for cand in candidates:
                if cand.exists():
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("ai_detector", str(cand))
                    if spec and spec.loader:
                        ai_mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(ai_mod)
                        break

        if ai_mod is not None:
            try:
                res = ai_mod.analyze_text(clean_text, allow_partial=True, offline=True)
                return float(res["global_score"]["p_ai_percent"])
            except Exception:
                pass

            if hasattr(ai_mod, "score_stylometric"):
                res_stylo = ai_mod.score_stylometric(clean_text)
                return float(round(res_stylo["score"] * 100.0, 1))
    except Exception:
        pass

    return calculate_pure_stylometric_score(clean_text, words)


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
        wb = len(re.findall(r'\b\w+\b', tb))
        wa = len(re.findall(r'\b\w+\b', ta))

        if wb < 5 and wa < 5:
            continue

        score_b = estimate_ai_score(tb) if wb >= 5 else None
        score_a = estimate_ai_score(ta) if wa >= 5 else None

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
        meta.append(f"<!-- Generated at: {now_str} -->\n\n")

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
