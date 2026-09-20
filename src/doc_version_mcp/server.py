"""
server.py — Serveur FastMCP doc-version exposant les 6 outils décorés en stdio pur.
"""

import os
import sys
import re
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

from fastmcp import FastMCP

from .cas_engine import CASEngine
from .diff_engine import DiffEngine
from .latex_resolver import LatexToMarkdownConverter, BibTexParser
from .draft_engine import DraftEngine
from .artifact_builder import ArtifactBuilder

# Instanciation du serveur FastMCP
mcp = FastMCP(
    "doc-version"
)

# Moteur CAS global
cas = CASEngine()


@mcp.tool()
def commit_document(
    target: str,
    message: str,
    content: str = "",
    author: str = "agent",
    mode: str = "paper",
    is_pinned: bool = False
) -> str:
    """
    Crée un instantané horodaté d'un document dans le Content-Addressable Storage (CAS).
    Supporte les fichiers sur disque et les mémoires virtuelles (drafts sans fichier).
    """
    try:
        commit_record = cas.create_snapshot(
            target=target,
            message=message,
            author=author,
            is_pinned=is_pinned,
            content=content if content else None,
            mode=mode
        )
        return json.dumps({
            "status": "success",
            "commit_id": commit_record["commit_id"],
            "short_id": commit_record["commit_id"][:8],
            "target": commit_record["target"],
            "message": commit_record["message"],
            "author": commit_record["author"],
            "timestamp": commit_record["timestamp"],
            "byte_size": commit_record["byte_size"],
            "compressed_size": commit_record["compressed_size"],
            "is_pinned": commit_record["is_pinned"],
            "mode": commit_record["mode"]
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def get_diff_artifact(
    target: str,
    diff_explanation: str = "",
    content: str = "",
    from_commit_id: str = "",
    to_commit_id: str = "",
    mode: str = "paper",
    brain_dir: str = "",
    artifact_name: str = ""
) -> str:
    """
    Génère la vue différentielle chirurgicale AST et produit l'artéfact Markdown Antigravity.
    Supporte le mode paper (LaTeX/Markdown avec KaTeX) et le mode draft (audit syntaxique balises, rétention >=90%).
    """
    try:
        old_text = ""
        new_text = ""
        baseline_commit_id = from_commit_id

        # 1. Résolution de old_text
        if from_commit_id:
            old_text = cas.restore_snapshot(from_commit_id)
        else:
            # Chercher le dernier snapshot pour target
            snaps = cas.list_snapshots(target=target, limit=2)
            if snaps:
                old_text = cas.restore_snapshot(snaps[0]["commit_id"])
                baseline_commit_id = snaps[0]["commit_id"]

        # 2. Résolution de new_text
        if to_commit_id:
            new_text = cas.restore_snapshot(to_commit_id)
        elif content:
            new_text = content
        else:
            # Lire depuis le fichier cible sur disque
            p = Path(target)
            if not p.is_absolute():
                p = p.resolve()
            if p.exists() and p.is_file():
                if p.suffix.lower() == ".tex":
                    converter = LatexToMarkdownConverter(p)
                    new_text = converter.convert()
                else:
                    new_text = p.read_text(encoding="utf-8", errors="replace")
            else:
                new_text = old_text

        # Si pas d'ancienne version, considérer baseline vide ou identique
        if not old_text:
            old_text = new_text

        # Normalisation automatique LaTeX -> Markdown propre si fichier .tex ou contenu LaTeX détecté
        target_path = Path(target) if target else None
        base_dir = target_path.parent if (target_path and target_path.exists()) else None

        def is_latex_doc(t: str) -> bool:
            if not t:
                return False
            return bool(re.search(r'\\(?:documentclass|begin\{document\}|section|subsection|begin\{minipage\}|usepackage|begin\{table|fontsize|selectfont|hrule|vspace)\b', t))

        if is_latex_doc(old_text) or (target_path and target_path.suffix.lower() == ".tex" and "\\" in old_text):
            old_text = LatexToMarkdownConverter.convert_text(old_text, base_dir=base_dir)

        if is_latex_doc(new_text) or (target_path and target_path.suffix.lower() == ".tex" and "\\" in new_text):
            new_text = LatexToMarkdownConverter.convert_text(new_text, base_dir=base_dir)

        # Détermination du nom cible propre
        if artifact_name and artifact_name.strip():
            raw_target_name = artifact_name.strip()
            if raw_target_name.lower().endswith(".md"):
                raw_target_name = raw_target_name[:-3]
        else:
            raw_target_name = Path(target).stem or "document"
        target_name = re.sub(r'[^a-zA-Z0-9_\-]+', '_', raw_target_name).strip('_') or "document"

        retention = None
        is_compliant = None
        if mode == "draft":
            retention = DraftEngine.calculate_retention(old_text, new_text)
            is_compliant = retention >= 90.0

        annotated_body, tree_toc, diff_count, mod_sections = DiffEngine.generate_diff_annotated_body(
            old_text=old_text,
            new_text=new_text,
            is_collab=False,
            author_name="agent"
        )

        # Récupération des 5 derniers commits depuis le CAS
        recent_commits = cas.list_snapshots(target=target, limit=5)
        if not recent_commits:
            recent_commits = cas.list_snapshots(limit=5)

        artifact_content = ArtifactBuilder.assemble_brain_artifact(
            target_name=target_name,
            annotated_body=annotated_body,
            tree_toc=tree_toc,
            diff_count=diff_count,
            diff_explanation=diff_explanation,
            source_file=target,
            baseline_commit=baseline_commit_id,
            recent_commits=recent_commits,
            enable_ai_score=True,
            final_content=new_text,
            mode=mode
        )

        # Sauvegarde dans brain_dir si fourni
        saved_path = None
        if brain_dir:
            b_dir = Path(brain_dir)
            if b_dir.exists() and b_dir.is_dir():
                art_file = b_dir / f"{target_name}.md"
                art_file.write_text(artifact_content, encoding="utf-8")
                saved_path = art_file.as_posix()

        res_data = {
            "status": "success",
            "diff_count": diff_count,
            "modified_sections": mod_sections,
            "baseline_commit": baseline_commit_id[:8] if baseline_commit_id else None,
            "saved_artifact_path": saved_path,
            "artifact_content": artifact_content
        }
        if retention is not None:
            res_data["retention_percent"] = retention
            res_data["is_retention_compliant"] = is_compliant

        return json.dumps(res_data, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def restore_commit(
    commit_id: str,
    target: str = "",
    dry_run: bool = False
) -> str:
    """
    Restaure un document depuis son commit ID dans le CAS.
    Si dry_run=True, prévisualise sans modifier le disque.
    """
    try:
        commit_data = cas.get_commit(commit_id)
        content = cas.restore_snapshot(commit_id, target_file=target if not dry_run else None)

        return json.dumps({
            "status": "success",
            "commit_id": commit_data["commit_id"],
            "target": target or commit_data["target"],
            "dry_run": dry_run,
            "restored_bytes": len(content.encode("utf-8")),
            "content_preview": content[:300] + ("..." if len(content) > 300 else "")
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def list_commits(
    target: str = "",
    limit: int = 10,
    mode: str = ""
) -> str:
    """
    Liste les commits stockés dans le CAS avec métadonnées d'horodatage et auteur.
    """
    try:
        commits = cas.list_snapshots(target=target, limit=limit, mode=mode)
        summary = []
        for c in commits:
            summary.append({
                "commit_id": c["commit_id"],
                "short_id": c["commit_id"][:8],
                "target": c["target"],
                "message": c["message"],
                "author": c["author"],
                "timestamp": c["timestamp"],
                "mode": c.get("mode", "paper"),
                "is_pinned": c.get("is_pinned", False),
                "byte_size": c.get("byte_size", 0)
            })
        return json.dumps({
            "status": "success",
            "count": len(summary),
            "commits": summary
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def prune_commits(
    ttl_days: int = 14,
    max_size_mb: int = 500,
    keep_baselines: bool = True
) -> str:
    """
    Purge les snapshots expirés selon le TTL et régule la taille totale sous max_size_mb.
    Protège les baselines épinglées (is_pinned) si keep_baselines=True.
    """
    try:
        prune_stats = cas.prune_expired(
            ttl_days=ttl_days,
            max_mb=max_size_mb,
            keep_baselines=keep_baselines
        )
        return json.dumps({
            "status": "success",
            "stats": prune_stats
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


@mcp.tool()
def record_git_pull_event(
    repo_path: str,
    autostash: bool = True
) -> str:
    """
    Synchronise un dépôt Git via git pull --rebase (--autostash),
    détecte les conflits et enregistre un snapshot CAS horodaté de l'état récupéré.
    """
    r_path = Path(repo_path).resolve()
    if not r_path.exists() or not (r_path / ".git").exists():
        return json.dumps({
            "status": "error",
            "error": f"Dépôt Git invalide : {repo_path}"
        }, ensure_ascii=False)

    try:
        # Récupération du HEAD avant pull
        res_before = subprocess.run(
            ["git", "-C", str(r_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        head_before = res_before.stdout.strip() if res_before.returncode == 0 else ""

        # Exécution du pull
        pull_cmd = ["git", "-C", str(r_path), "pull", "--rebase"]
        if autostash:
            pull_cmd.append("--autostash")

        pull_res = subprocess.run(pull_cmd, capture_output=True, text=True, timeout=60)
        pull_out = (pull_res.stdout + "\n" + pull_res.stderr).strip()

        # Détection de conflits
        st_res = subprocess.run(
            ["git", "-C", str(r_path), "status", "--porcelain"],
            capture_output=True, text=True, timeout=10
        )
        unmerged = [
            line[3:].strip() for line in st_res.stdout.splitlines()
            if line[:2] in ("UU", "AA", "UD", "DU", "DD", "AU", "UA")
        ]

        if pull_res.returncode != 0 or unmerged:
            return json.dumps({
                "status": "conflict_detected",
                "message": "Conflit Git détecté lors du pull. Règle d'or : modifications collaborateurs prioritaires !",
                "unmerged_files": unmerged,
                "git_output": pull_out
            }, indent=2, ensure_ascii=False)

        # Récupération du HEAD après pull
        res_after = subprocess.run(
            ["git", "-C", str(r_path), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        head_after = res_after.stdout.strip() if res_after.returncode == 0 else ""

        new_commits = []
        if head_before and head_after and head_before != head_after:
            log_res = subprocess.run(
                ["git", "-C", str(r_path), "log", f"{head_before}..{head_after}", "--format=%h|%an|%s"],
                capture_output=True, text=True, timeout=10
            )
            for l in log_res.stdout.splitlines():
                parts = l.split("|", 2)
                if len(parts) == 3:
                    new_commits.append({"hash": parts[0], "author": parts[1], "subject": parts[2]})

        return json.dumps({
            "status": "success",
            "head_before": head_before[:8] if head_before else "",
            "head_after": head_after[:8] if head_after else "",
            "has_updates": (head_before != head_after),
            "new_commits": new_commits,
            "git_output": pull_out
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"status": "error", "error": str(e)}, ensure_ascii=False)


def main():
    """Point d'entrée du serveur FastMCP en mode stdio ou CLI si sous-commande fournie."""
    if len(sys.argv) > 1 and sys.argv[1] in ("list", "commit", "diff", "restore", "prune"):
        import argparse

        if sys.platform == "win32":
            try:
                sys.stdout.reconfigure(encoding="utf-8")
                sys.stderr.reconfigure(encoding="utf-8")
            except Exception:
                pass

        parser = argparse.ArgumentParser(prog="doc-version", description="FastMCP doc-version CLI bridge")
        subparsers = parser.add_subparsers(dest="subcommand", required=True)

        # list
        p_list = subparsers.add_parser("list", help="List CAS commits")
        p_list.add_argument("--target", default="", help="Target file path or virtual identifier filter")
        p_list.add_argument("--limit", type=int, default=10, help="Maximum number of commits")
        p_list.add_argument("--mode", default="", help="Filter by mode (paper/draft)")

        # commit
        p_commit = subparsers.add_parser("commit", help="Commit document to CAS")
        p_commit.add_argument("--target", required=True, help="Target file path or virtual identifier")
        p_commit.add_argument("--message", required=True, help="Commit message")
        p_commit.add_argument("--content", default="", help="Literal content")
        p_commit.add_argument("--content-file", default="", help="Path to content file")
        p_commit.add_argument("--author", default="agent", help="Author name")
        p_commit.add_argument("--mode", default="paper", choices=["paper", "draft"], help="Operating mode")
        p_commit.add_argument("--pinned", action="store_true", help="Pin snapshot")

        # diff
        p_diff = subparsers.add_parser("diff", help="Generate diff artifact")
        p_diff.add_argument("--target", required=True, help="Target file path or virtual identifier")
        p_diff.add_argument("--explanation", default="", help="Concise diff explanation")
        p_diff.add_argument("--content", default="", help="New literal content")
        p_diff.add_argument("--content-file", default="", help="Path to new content file")
        p_diff.add_argument("--from-commit", default="", help="Base commit ID")
        p_diff.add_argument("--to-commit", default="", help="Target commit ID")
        p_diff.add_argument("--mode", default="paper", choices=["paper", "draft"], help="Operating mode")
        p_diff.add_argument("--brain-dir", default="", help="Brain directory to write artifact")
        p_diff.add_argument("--artifact-name", default="", help="Base name of output artifact")

        # restore
        p_restore = subparsers.add_parser("restore", help="Restore snapshot from CAS")
        p_restore.add_argument("--commit-id", required=True, help="Commit ID to restore")
        p_restore.add_argument("--target", default="", help="Target destination file path")
        p_restore.add_argument("--dry-run", action="store_true", help="Dry run preview")

        # prune
        p_prune = subparsers.add_parser("prune", help="Prune expired CAS commits")
        p_prune.add_argument("--ttl-days", type=int, default=14, help="TTL in days")
        p_prune.add_argument("--max-size-mb", type=int, default=500, help="Max CAS cache size in MB")
        p_prune.add_argument("--no-keep-baselines", action="store_true", help="Do not protect pinned baselines")

        args = parser.parse_args()

        if args.subcommand == "list":
            print(list_commits(target=args.target, limit=args.limit, mode=args.mode))
        elif args.subcommand == "commit":
            c = ""
            if args.content_file:
                c = Path(args.content_file).read_text(encoding="utf-8", errors="replace")
            elif args.content:
                c = args.content
            print(commit_document(target=args.target, message=args.message, content=c, author=args.author, mode=args.mode, is_pinned=args.pinned))
        elif args.subcommand == "diff":
            c = ""
            if args.content_file:
                c = Path(args.content_file).read_text(encoding="utf-8", errors="replace")
            elif args.content:
                c = args.content
            print(get_diff_artifact(target=args.target, diff_explanation=args.explanation, content=c, from_commit_id=args.from_commit, to_commit_id=args.to_commit, mode=args.mode, brain_dir=args.brain_dir, artifact_name=args.artifact_name))
        elif args.subcommand == "restore":
            print(restore_commit(commit_id=args.commit_id, target=args.target, dry_run=args.dry_run))
        elif args.subcommand == "prune":
            print(prune_commits(ttl_days=args.ttl_days, max_size_mb=args.max_size_mb, keep_baselines=not args.no_keep_baselines))
        return

    # Rediriger stderr pour éviter de polluer le protocole stdio
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
