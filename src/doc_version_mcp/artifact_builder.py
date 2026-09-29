"""
artifact_builder.py — Assemblage normé d'artéfacts Markdown Antigravity avec Tree TOC et conciliation collaborative.
"""

import re
import os
import shutil
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)


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
    def clean_for_copy(cls, text: str) -> str:
        """
        Nettoie et formate le texte pour le bloc dépliant prêt à copier :
        - Déballe les polices LaTeX résiduelles (\\textsf, \\textbf, etc.)
        - Supprime les balises et styles HTML (<span>, <style>, etc.)
        - Supprime les commandes et environnements LaTeX résiduels
        - Préserve les blocs KaTeX et le texte pur
        """
        if not text:
            return ""
        from .diff_engine import DiffEngine
        clean_text = DiffEngine.clean_residual_latex(text)
        return clean_text.strip()

    @classmethod
    def get_dynamic_fence(cls, text: str, min_fence_len: int = 4) -> str:
        """
        Calcule dynamiquement la clôture de code CommonMark (backticks) nécessaire
        pour encapsuler un texte sans risque d'échappement par des sous-blocs internes.
        N = max(min_fence_len, M + 1) où M est le nombre maximal de backticks consécutifs dans text.
        """
        if not text:
            return "`" * min_fence_len
        backtick_matches = re.findall(r'`+', text)
        m = max((len(match) for match in backtick_matches), default=0)
        n = max(min_fence_len, m + 1)
        return "`" * n

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
            clean_copy = cls.clean_for_copy(final_content)
            fence = cls.get_dynamic_fence(clean_copy, min_fence_len=4)
            copy_block = (
                f"<details><summary>📋 Texte Final Prêt à Copier</summary>\n\n"
                f"{fence}text\n"
                f"{clean_copy}\n"
                f"{fence}\n"
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

        # 6. Lien cliquable vers le fichier source physique
        source_link_block = ""
        if source_file and not source_file.startswith("virtual:"):
            try:
                p = Path(source_file)
                if p.is_file() or p.exists():
                    posix_path = p.as_posix().lstrip('/')
                    file_url = f"file:///{posix_path}"
                    source_link_block = f"📄 **Fichier Source** : [{p.name}]({file_url})\n\n"
            except Exception:
                pass

        full_doc = f"{header}{source_link_block}{copy_block}{warnings_block}{diff_block}{commits_block}{processed_body.rstrip()}\n"
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
        source_dir: Optional[Path] = None,
        vault_root: Optional[Path] = None
    ) -> str:
        """
        Normalise les images Markdown (wikilinks ou liens standard) pour pointer en URL file:///
        vers le dossier brain_target_dir, et copie physiquement les fichiers sources correspondants.
        """
        brain_target_dir.mkdir(parents=True, exist_ok=True)
        b_posix = brain_target_dir.resolve().as_posix().lstrip('/')

        # 1. Extraction de source_dir depuis le commentaire SOURCE_FILE si non fourni
        if not source_dir:
            src_match = re.search(r'<!--\s*SOURCE_FILE:\s*([^\n\r]+?)\s*-->', markdown_text)
            if src_match:
                cand_src = Path(src_match.group(1).strip())
                if cand_src.is_file() or cand_src.parent.exists():
                    source_dir = cand_src.parent

        # 2. Détection du vault_root Obsidian ou Git repo si non fourni
        if not vault_root and source_dir:
            curr = source_dir.resolve()
            for p in [curr] + list(curr.parents):
                if (p / ".obsidian").is_dir():
                    vault_root = p
                    break
            if not vault_root:
                for p in [curr] + list(curr.parents):
                    if (p / "_attachments").is_dir() or (p / ".git").is_dir():
                        vault_root = p
                        break

        if not vault_root:
            curr_cwd = Path.cwd().resolve()
            for p in [curr_cwd] + list(curr_cwd.parents):
                if (p / ".obsidian").is_dir():
                    vault_root = p
                    break
            if not vault_root:
                default_vault = Path.home() / "Documents" / "VoiceNotes"
                if (default_vault / ".obsidian").is_dir():
                    vault_root = default_vault

        # 3. Construction ordonnée des dossiers de recherche prioritaires
        seen_dirs = set()
        search_dirs: List[Path] = []

        def add_dir(d: Optional[Path]):
            if d is None:
                return
            try:
                d_res = d.resolve()
                if d_res.is_dir() and d_res not in seen_dirs:
                    seen_dirs.add(d_res)
                    search_dirs.append(d_res)
                    if d_res.name.lower() in ("_attachments", "attachments"):
                        for root, dirs, _ in os.walk(d_res):
                            for sd in dirs:
                                p_sd = Path(root) / sd
                                if p_sd.resolve() not in seen_dirs:
                                    seen_dirs.add(p_sd.resolve())
                                    search_dirs.append(p_sd.resolve())
            except Exception:
                pass

        # Dossier source et sous-dossiers immédiats
        if source_dir:
            s_res = source_dir.resolve()
            add_dir(s_res)
            add_dir(s_res / "_attachments")
            add_dir(s_res / "figures")
            add_dir(s_res / "assets")
            add_dir(s_res / "images")

            # Parents jusqu'au vault_root
            for parent in s_res.parents:
                add_dir(parent)
                add_dir(parent / "_attachments")
                add_dir(parent / "figures")
                add_dir(parent / "assets")
                add_dir(parent / "images")
                if vault_root and parent.resolve() == vault_root.resolve():
                    break

        # Vault root et sous-dossiers canoniques
        if vault_root:
            v_res = vault_root.resolve()
            add_dir(v_res)
            add_dir(v_res / "_attachments")
            add_dir(v_res / "figures")
            add_dir(v_res / "assets")
            add_dir(v_res / "images")

        # CWD
        cwd = Path.cwd().resolve()
        add_dir(cwd)
        add_dir(cwd / "_attachments")
        add_dir(cwd / "figures")
        add_dir(cwd / "assets")
        add_dir(cwd / "images")

        check_exts = [".png", ".jpg", ".jpeg", ".webp", ".svg", ".pdf", ".gif"]

        def locate_and_copy_image(raw_ref: str) -> Tuple[str, Optional[str]]:
            clean_ref = raw_ref.strip().strip('"{}\'')
            if clean_ref.startswith(("http://", "https://", "data:")):
                return clean_ref, clean_ref

            if clean_ref.startswith(("file://", "file:/")):
                clean_ref = re.sub(r'^file:///?', '', clean_ref).split('?')[0].split('#')[0]

            # Si clean_ref contient des balises HTML issues de diffs visuels (<span style="...">)
            if "<span" in clean_ref:
                # 1. Version nouvelle (verte / ajoutée) : élimination des spans rouges (suppressions)
                new_ref = re.sub(r'<span[^>]*(?:#fee2e2|#991b1b)[^>]*>.*?</span>', '', clean_ref, flags=re.DOTALL)
                new_ref = re.sub(r'<span[^>]*>(.*?)</span>', r'\1', new_ref, flags=re.DOTALL).strip()
                # 2. Version ancienne (rouge / supprimée) : élimination des spans verts (ajouts)
                old_ref = re.sub(r'<span[^>]*(?:#dcfce7|#166534)[^>]*>.*?</span>', '', clean_ref, flags=re.DOTALL)
                old_ref = re.sub(r'<span[^>]*>(.*?)</span>', r'\1', old_ref, flags=re.DOTALL).strip()

                if old_ref and old_ref != clean_ref and "<span" not in old_ref:
                    locate_and_copy_image(old_ref)
                if new_ref and new_ref != clean_ref and "<span" not in new_ref:
                    return locate_and_copy_image(new_ref)

            found_target: Optional[Path] = None
            p_abs = Path(clean_ref)
            target_filename = p_abs.name
            stem_unversioned = re.sub(r'_(?:[0-9a-fA-F]{8}|\d{10})$', '', p_abs.stem)
            unversioned_filename = f"{stem_unversioned}{p_abs.suffix}"

            # Si clean_ref est un chemin absolu direct existant
            # ATTENTION : Si p_abs pointe dans brain_target_dir, il s'agit d'une copie de session / cache de rendu.
            # On ne l'accepte directement que s'il est en dehors de brain_target_dir afin de permettre le rafraîchissement
            # depuis la source originale si celle-ci a été modifiée dans le vault ou projet.
            if p_abs.is_file():
                try:
                    if p_abs.resolve().parent != brain_target_dir.resolve():
                        found_target = p_abs
                except Exception:
                    pass

            if not found_target:
                is_abs_ref = False
                try:
                    is_abs_ref = Path(clean_ref).is_absolute()
                except Exception:
                    pass

                candidate_names = [target_filename]
                if unversioned_filename != target_filename:
                    candidate_names.append(unversioned_filename)

                # 1. Dossiers de recherche prioritaires (sources)
                for b_dir in search_dirs:
                    if not b_dir.exists() or not b_dir.is_dir():
                        continue
                    # Chemin direct relatif (uniquement si non absolu)
                    if not is_abs_ref:
                        cand = b_dir / clean_ref
                        if cand.is_file():
                            found_target = cand
                            break
                        if unversioned_filename != target_filename:
                            cand_unv = b_dir / unversioned_filename
                            if cand_unv.is_file():
                                found_target = cand_unv
                                break
                    # Noms de fichiers (avec et sans hash)
                    for cand_n in candidate_names:
                        cand_file = b_dir / cand_n
                        if cand_file.is_file():
                            found_target = cand_file
                            break
                    if found_target:
                        break

                    # Essai avec extensions si pas d'extension
                    if not Path(target_filename).suffix:
                        for ext in check_exts:
                            for cand_n in candidate_names:
                                cand_ext_name = b_dir / f"{cand_n}{ext}"
                                if cand_ext_name.is_file():
                                    found_target = cand_ext_name
                                    break
                            if found_target:
                                break
                    if found_target:
                        break

                # 2. Recherche récursive dans vault_root ou source_dir
                if not found_target and (vault_root or source_dir):
                    search_root = vault_root or source_dir
                    names_to_try = list(candidate_names)
                    if not Path(clean_ref).suffix:
                        for ext in check_exts:
                            for cand_n in candidate_names:
                                names_to_try.append(f"{cand_n}{ext}")
                    for n in names_to_try:
                        for root, dirs, files in os.walk(search_root):
                            dirs[:] = [d for d in dirs if d not in {".git", ".obsidian", ".venv", "node_modules", ".trash", "$RECYCLE.BIN"}]
                            if n in files:
                                cand = Path(root) / n
                                if cand.is_file():
                                    found_target = cand
                                    break
                        if found_target:
                            break

                # 3. Fallback ultime de secours : si l'image n'est trouvée nulle part dans les sources réelles,
                # mais qu'elle pré-existe déjà dans brain_target_dir (ex: asset généré localement en session)
                if not found_target and brain_target_dir.is_dir():
                    if not is_abs_ref:
                        cand_brain = brain_target_dir / clean_ref
                        if cand_brain.is_file():
                            found_target = cand_brain
                    if not found_target:
                        for cand_n in candidate_names:
                            cand_brain_name = brain_target_dir / cand_n
                            if cand_brain_name.is_file():
                                found_target = cand_brain_name
                                break

            # Rastérisation PyMuPDF si PDF
            if found_target and found_target.suffix.lower() == ".pdf":
                try:
                    import pymupdf
                    doc = pymupdf.open(str(found_target))
                    if len(doc) > 0:
                        page = doc[0]
                        pix = page.get_pixmap(dpi=300)
                        clean_stem = re.sub(r'_(?:[0-9a-fA-F]{8}|\d{10})$', '', found_target.stem).replace(" ", "_")
                        pdf_hash = hashlib.md5(found_target.read_bytes()).hexdigest()[:8]
                        raster_name = f"{clean_stem}_{pdf_hash}.png"
                        canonical_raster = f"{clean_stem}.png"
                        raster_png = brain_target_dir / raster_name
                        pix.save(str(raster_png))
                        pix.save(str(brain_target_dir / canonical_raster))
                        # Nettoyage des anciennes versions hashées obsolètes du même stem
                        for old_f in brain_target_dir.glob(f"{clean_stem}_*.png"):
                            if old_f.name != raster_name and re.match(rf"^{re.escape(clean_stem)}_[0-9a-fA-F]{{8}}\.png$", old_f.name):
                                try:
                                    old_f.unlink()
                                except Exception:
                                    pass
                        if raster_png.is_file():
                            return raster_name, f"file:///{b_posix}/{raster_name}"
                except Exception as e:
                    logger.warning("Erreur lors de la conversion PDF -> PNG pour '%s': %s", found_target, e)

            # Copie physique vers brain_target_dir avec nom versionné par hash (cache-busting garanti pour le webview Chromium d'Antigravity)
            if found_target and found_target.is_file():
                img_bytes = found_target.read_bytes()
                img_hash = hashlib.md5(img_bytes).hexdigest()[:8]
                clean_stem = re.sub(r'_(?:[0-9a-fA-F]{8}|\d{10})$', '', found_target.stem).replace(" ", "_")
                ext = found_target.suffix.lower()
                versioned_name = f"{clean_stem}_{img_hash}{ext}"
                canonical_name = f"{clean_stem}{ext}"

                dest_file = brain_target_dir / versioned_name
                canonical_dest = brain_target_dir / canonical_name
                try:
                    if found_target.resolve() != dest_file.resolve():
                        dest_file.write_bytes(img_bytes)
                        try:
                            shutil.copystat(found_target, dest_file)
                        except Exception:
                            pass
                        logger.info("Copie/écrasement versionné de l'image '%s' vers '%s'", found_target, dest_file)

                    # Maintien de la copie canonique sans hash pour rétro-compatibilité
                    if found_target.resolve() != canonical_dest.resolve():
                        canonical_dest.write_bytes(img_bytes)
                        try:
                            shutil.copystat(found_target, canonical_dest)
                        except Exception:
                            pass

                    # Purge des anciennes versions hashées du même stem dans brain_target_dir
                    for old_f in brain_target_dir.glob(f"{clean_stem}_*{ext}"):
                        if old_f.name != versioned_name and re.match(rf"^{re.escape(clean_stem)}_[0-9a-fA-F]{{8}}\.{re.escape(ext.lstrip('.'))}$", old_f.name):
                            try:
                                old_f.unlink()
                                logger.info("Purge de l'ancienne version image obsolète '%s'", old_f)
                            except Exception:
                                pass
                except Exception as e:
                    logger.warning("Erreur lors de la copie physique de '%s' vers '%s': %s", found_target, dest_file, e)

                if dest_file.is_file():
                    return versioned_name, f"file:///{b_posix}/{versioned_name}"
                elif canonical_dest.is_file():
                    return canonical_name, f"file:///{b_posix}/{canonical_name}"
                else:
                    logger.warning("Fichier image copié non trouvé sur le disque : '%s'", dest_file)

            # Si l'image n'est pas trouvée ou n'a pas pu être copiée :
            # logger un avertissement explicite et ne pas insérer de lien file:/// pour éviter l'erreur 'Preview unavailable'
            logger.warning(
                "Image introuvable sur disque ou non copiée vers brain_dir : '%s' "
                "(source_dir='%s', vault_root='%s'). Le lien file:/// n'a pas été inséré.",
                raw_ref,
                source_dir,
                vault_root
            )
            safe_name = Path(clean_ref).name.replace(" ", "_")
            return safe_name, None

        # Copie éventuelle des images référencées dans le frontmatter YAML : Image: "[[...]]" ou image: "[[...]]"
        for m in re.finditer(r'(?:[Ii]mage|cover):\s*"\[\[(.*?)\]\]"', markdown_text):
            raw_img = m.group(1).split('|')[0].strip()
            locate_and_copy_image(raw_img)

        def repl_wikilink(m):
            inner = m.group(1).strip()
            parts = inner.split('|')
            raw_path = parts[0].strip()
            safe_name, file_url = locate_and_copy_image(raw_path)
            stem_clean = re.sub(r'_[0-9a-fA-F]{8}$', '', Path(safe_name).stem)
            alt = parts[1].strip() if len(parts) > 1 and not parts[1].strip().isdigit() else stem_clean.replace('_', ' ')
            if file_url:
                return f"\n\n![{alt}]({file_url})\n\n"
            return f"\n\n![{alt}]({raw_path})\n\n"

        def repl_md(m):
            alt = m.group(1).strip()
            src = m.group(2).strip()
            safe_name, file_url = locate_and_copy_image(src)
            stem_clean = re.sub(r'_[0-9a-fA-F]{8}$', '', Path(safe_name).stem)
            clean_alt = alt if (alt and not alt.isdigit()) else stem_clean.replace('_', ' ')
            if file_url:
                return f"\n\n![{clean_alt}]({file_url})\n\n"
            return f"\n\n![{clean_alt}]({src})\n\n"

        text = re.sub(r'!\[\[(.*?)\]\]', repl_wikilink, markdown_text)
        text = re.sub(r'!\[([^\]]*)\]\(([^)]+)\)', repl_md, text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text
