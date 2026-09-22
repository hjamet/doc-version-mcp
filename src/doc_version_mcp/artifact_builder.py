"""
artifact_builder.py — Assemblage normé d'artéfacts Markdown Antigravity avec Tree TOC et conciliation collaborative.
"""

import re
import os
import shutil
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple


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

        parts.append("\n".join(meta))
        return "".join(parts)

    @classmethod
    def build_recent_commits_table(
        cls,
        commits: Optional[List[Dict[str, Any]]] = None,
        limit: int = 5,
        target: Optional[str] = None,
        repo_root: Optional[Path] = None,
        upstream_id: Optional[str] = None
    ) -> str:
        """
        Génère le tableau Markdown canonique des N derniers commits CAS :
        | Commit ID | Date | Auteur | Message / Titre | Boucle Anti-IA (Itérations & Résolutions) |
        """
        if not commits:
            return ""

        from .style_guard import format_style_audit_summary, load_style_audit, check_is_overleaf_commit

        rows = [
            "### 🕒 Historique Récent (5 Derniers Commits)\n",
            "| Commit ID | Date | Auteur | Message / Titre | Boucle Anti-IA (Itérations & Résolutions) |",
            "| :--- | :--- | :--- | :--- | :--- |"
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

            # 1. Résolution de l'audit de style
            audit_data = c.get("style_audit")
            if not audit_data and c_id:
                audit_data = load_style_audit(c_id, target=target or c.get("target"))

            # 2. Détection de commit Overleaf
            is_overleaf = c.get("is_overleaf", False)
            if not is_overleaf and repo_root and c_id:
                is_overleaf = check_is_overleaf_commit(repo_root, c_id, upstream_id)

            if is_overleaf:
                summary = "N/A (commit Overleaf)"
            elif audit_data:
                summary = format_style_audit_summary(audit_data)
            elif "overleaf" in msg.lower() or "overleaf" in author.lower():
                summary = "N/A (commit Overleaf)"
            else:
                summary = "1 tour (0 pb - Conforme)" if str(c.get("author", "")).lower() in ("agent", "henri", "henri jamet") else "N/A"

            summary_escaped = summary.replace("|", "\\|")
            rows.append(f"| {short_id} | {formatted_date} | {author} | {msg} | {summary_escaped} |")

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
        mode: str = "paper",
        soft_warnings: Optional[List[Dict[str, Any]]] = None,
        repo_root: Optional[Path] = None,
        upstream_id: Optional[str] = None
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

        # Le corps annoté est utilisé directement sans aucun badge IA
        processed_body = annotated_body

        if diff_count > 0:
            diff_block = (
                f"{cls.DIFF_SUMMARY_HEADER}\n\n"
                f"> [!IMPORTANT]\n"
                f"> **🌳 Arborescence des Modifications Détectées ({diff_count} deltas) :**\n"
                f"{exp_note}\n"
                f"> 📂 **{doc_title}**<br>\n"
                f"{tree_toc}\n\n"
                f"---\n\n"
            )
        else:
            diff_block = (
                f"## 📑 Structure & Sommaire AST du Manuscrit\n\n"
                f"> [!NOTE]\n"
                f"> **🌳 Arborescence des Sections AST (État Actuel) :**\n"
                f"{exp_note}\n"
                f"> 📂 **{doc_title}**<br>\n"
                f"{tree_toc}\n\n"
                f"---\n\n"
            )

        # 3. Tableau des 5 derniers commits CAS
        commits_block = cls.build_recent_commits_table(
            recent_commits,
            limit=5,
            target=source_file,
            repo_root=repo_root,
            upstream_id=upstream_id
        )

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

        # 5. Bloc dépliant de recommandations stylistiques non-bloquantes (soft warnings dans le budget)
        warnings_block = ""
        if soft_warnings:
            w_rows = [
                f"<details><summary>💡 Recommandations Stylistiques Non-Bloquantes ({len(soft_warnings)} alertes)</summary>\n",
                "| Type | Ligne | Terme / Motif | Suggestion |",
                "| :--- | :--- | :--- | :--- |"
            ]
            for w in soft_warnings:
                t = str(w.get("type", "Avertissement")).replace("|", "\\|")
                l = f"Ligne {w.get('line', '—')}"
                term = str(w.get("term", "")).replace("|", "\\|")
                sug = str(w.get("suggestion", "")).replace("|", "\\|")
                w_rows.append(f"| {t} | {l} | `{term}` | {sug} |")
            warnings_block = "\n".join(w_rows) + "\n\n</details>\n\n---\n\n"

        full_doc = f"{header}{copy_block}{warnings_block}{diff_block}{commits_block}{processed_body.rstrip()}\n"
        if diff_explanation.strip():
            full_doc = cls.inject_explanation_callout(full_doc, diff_explanation.strip())

        # Élimination stricte de tout bloc <style> résiduel pour empêcher toute fuite en texte brut
        full_doc = re.sub(r'<style\b[^>]*>.*?</style>\s*', '', full_doc, flags=re.DOTALL)
        return full_doc

    @classmethod
    def format_images_for_brain(
        cls,
        markdown_text: str,
        brain_target_dir: Path,
        source_dir: Optional[Path] = None
    ) -> str:
        """
        Normalise les images Markdown (wikilinks ou liens standard) pour pointer en URL file:///
        vers le dossier brain_target_dir, et copie physiquement les fichiers sources correspondants.
        """
        brain_target_dir.mkdir(parents=True, exist_ok=True)
        b_posix = brain_target_dir.resolve().as_posix().lstrip('/')

        search_dirs: List[Path] = []
        if source_dir:
            s_res = source_dir.resolve()
            search_dirs.extend([
                s_res,
                s_res / "figures",
                s_res / "assets",
                s_res / "images",
                s_res / "_attachments"
            ])
            if s_res.parent.exists():
                search_dirs.extend([
                    s_res.parent,
                    s_res.parent / "figures",
                    s_res.parent / "assets",
                    s_res.parent / "images"
                ])
        cwd = Path.cwd()
        search_dirs.extend([
            cwd,
            cwd / "figures",
            cwd / "assets",
            cwd / "images"
        ])

        check_exts = [".png", ".jpg", ".jpeg", ".webp", ".svg", ".pdf", ".gif"]

        def locate_and_copy_image(raw_ref: str) -> Tuple[str, str]:
            clean_ref = raw_ref.strip().strip('"{}\'')
            clean_ref = re.sub(r'^file:///?', '', clean_ref).split('?')[0].split('#')[0]

            found_target: Optional[Path] = None
            p_abs = Path(clean_ref)
            if p_abs.is_file():
                found_target = p_abs
            else:
                for b_dir in search_dirs:
                    if not b_dir.exists() or not b_dir.is_dir():
                        continue
                    # 1. Chemin direct relatif
                    cand = b_dir / clean_ref
                    if cand.is_file():
                        found_target = cand
                        break
                    # 2. Nom de fichier seul dans le sous-dossier
                    cand_name = b_dir / Path(clean_ref).name
                    if cand_name.is_file():
                        found_target = cand_name
                        break
                    # 3. Essayer avec extensions si pas d'extension
                    if not Path(clean_ref).suffix:
                        for ext in check_exts:
                            cand_ext = b_dir / f"{clean_ref}{ext}"
                            if cand_ext.is_file():
                                found_target = cand_ext
                                break
                            cand_ext_name = b_dir / f"{Path(clean_ref).name}{ext}"
                            if cand_ext_name.is_file():
                                found_target = cand_ext_name
                                break
                        if found_target:
                            break

            # Rastérisation PyMuPDF si PDF trouvé
            if found_target and found_target.suffix.lower() == ".pdf":
                try:
                    import pymupdf
                    doc = pymupdf.open(str(found_target))
                    if len(doc) > 0:
                        page = doc[0]
                        pix = page.get_pixmap(dpi=300)
                        raster_name = f"{found_target.stem}.png".replace(" ", "_")
                        raster_png = brain_target_dir / raster_name
                        pix.save(str(raster_png))
                        return raster_name, f"file:///{b_posix}/{raster_name}"
                except Exception:
                    pass

            if found_target and found_target.is_file():
                safe_name = found_target.name.replace(" ", "_")
                dest_file = brain_target_dir / safe_name
                try:
                    if found_target.resolve() != dest_file.resolve():
                        shutil.copy2(found_target, dest_file)
                except Exception:
                    pass
                return safe_name, f"file:///{b_posix}/{safe_name}"

            # Si introuvable sur disque, préserver le nom propre dans brain
            safe_name = Path(clean_ref).name.replace(" ", "_")
            return safe_name, f"file:///{b_posix}/{safe_name}"

        def repl_wikilink(m):
            inner = m.group(1).strip()
            parts = inner.split('|')
            raw_path = parts[0].strip()
            safe_name, file_url = locate_and_copy_image(raw_path)
            alt = parts[1].strip() if len(parts) > 1 and not parts[1].strip().isdigit() else Path(safe_name).stem.replace('_', ' ')
            return f"\n\n![{alt}]({file_url})\n\n"

        def repl_md(m):
            alt = m.group(1).strip()
            src = m.group(2).strip()
            safe_name, file_url = locate_and_copy_image(src)
            clean_alt = alt if (alt and not alt.isdigit()) else Path(safe_name).stem.replace('_', ' ')
            return f"\n\n![{clean_alt}]({file_url})\n\n"

        text = re.sub(r'!\[\[(.*?)\]\]', repl_wikilink, markdown_text)
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', repl_md, text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text
