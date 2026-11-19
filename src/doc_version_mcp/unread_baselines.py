"""
unread_baselines.py — Stockage unique « Dirty-Baselines Only » (_agents/unread_baselines.json).

Invariant Solution B (Rasoir d'Ockham) :
- Une note ou sous-note lue/inchangée occupe 0 octet dans ce fichier.
- Seules les notes/sous-notes modifiées depuis la dernière lecture d'Henri y conservent leur
  état initial (`baseline`) + le registre par slide consultée (`seenSlides`) géré par SlideFlow.
- Dès que toutes les slides modifiées d'une note ont été consultées > 1s (ou lors d'une
  validation explicite author="henri"), son entrée est supprimée (retour à 0 octet).
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

BASELINES_REL_PATH = "_agents/unread_baselines.json"
EXCLUDED_PREFIXES = (
    "_agents/",
    ".obsidian/",
    ".git/",
    ".trash/",
    "virtual:",
    "scratch:",
    "~/",
)


def _strip_frontmatter(text: str) -> str:
    return re.sub(r"\A---\r?\n[\s\S]*?\r?\n---\r?\n*", "", text.lstrip())


def is_trackable_vault_note(rel_path: str) -> bool:
    if not rel_path:
        return False
    norm = rel_path.replace("\\", "/").lstrip("/")
    lower = norm.lower()
    if not lower.endswith(".md"):
        return False
    if Path(norm).is_absolute() or ":" in norm:
        return False
    for pref in EXCLUDED_PREFIXES:
        if lower.startswith(pref):
            return False
    return True


def get_baselines_path(vault_root: Path) -> Path:
    return (Path(vault_root).resolve() / BASELINES_REL_PATH).resolve()


def load_unread_baselines(vault_root: Path) -> Dict[str, Any]:
    path = get_baselines_path(vault_root)
    if not path.exists():
        return {"version": 1, "notes": {}}
    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("notes"), dict):
        raise ValueError(f"Format invalide dans {path}: clé 'notes' attendue.")
    data.setdefault("version", 1)
    return data


def save_unread_baselines(vault_root: Path, data: Dict[str, Any]) -> Path:
    path = get_baselines_path(vault_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp_path.replace(path)
    return path


def record_baseline_if_clean(
    vault_root: Path,
    rel_path: str,
    baseline_text: str,
    current_text: Optional[str] = None,
    updated_by: str = "agent",
    summary: str = "",
) -> bool:
    """
    Enregistre la baseline d'une note/sous-note si elle n'est pas déjà présente.
    - Si déjà présente : préserve `baseline` et `seenSlides` (invariant diff cumulatif).
    - Si `current_text` (hors frontmatter) est identique à la baseline : purge l'entrée (0 octet).
    Retourne True si le fichier JSON a été modifié.
    """
    norm = rel_path.replace("\\", "/").lstrip("/")
    if not is_trackable_vault_note(norm):
        return False

    data = load_unread_baselines(vault_root)
    notes = data["notes"]
    now_iso = datetime.now(timezone.utc).isoformat()

    existing = notes.get(norm)
    effective_baseline = existing["baseline"] if existing else baseline_text

    if current_text is not None:
        if _strip_frontmatter(current_text).strip() == _strip_frontmatter(effective_baseline).strip():
            if norm in notes:
                del notes[norm]
                save_unread_baselines(vault_root, data)
                return True
            return False

    if existing is None:
        notes[norm] = {
            "baseline": baseline_text,
            "updatedAt": now_iso,
            "updatedBy": updated_by,
            "summary": summary[:200] if summary else "",
            "seenSlides": {},
        }
    else:
        existing["updatedAt"] = now_iso
        existing["updatedBy"] = updated_by
        if summary:
            existing["summary"] = summary[:200]
        existing.setdefault("seenSlides", {})

    save_unread_baselines(vault_root, data)
    return True


def record_pre_edit_snapshot(
    vault_root: Path,
    target_path: str,
    summary: str = "",
    updated_by: str = "agent",
) -> Dict[str, Any]:
    """
    À appeler par un agent AVANT de modifier une note ou sous-note propre :
    capture son contenu actuel sur disque comme baseline si elle n'est pas déjà sale.
    """
    from .cas_engine import normalize_target_key

    norm = normalize_target_key(target_path)
    if not is_trackable_vault_note(norm):
        raise ValueError(f"Cible non suivie dans unread_baselines.json : {target_path!r} (norm={norm!r})")

    abs_file = (Path(vault_root).resolve() / norm).resolve()
    if not abs_file.is_file():
        raise FileNotFoundError(f"Note introuvable pour capture baseline : {abs_file}")

    disk_text = abs_file.read_text(encoding="utf-8")
    data = load_unread_baselines(vault_root)
    notes = data["notes"]
    already_dirty = norm in notes
    now_iso = datetime.now(timezone.utc).isoformat()

    if not already_dirty:
        notes[norm] = {
            "baseline": disk_text,
            "updatedAt": now_iso,
            "updatedBy": updated_by,
            "summary": summary[:200] if summary else "",
            "seenSlides": {},
        }
        save_unread_baselines(vault_root, data)

    return {
        "status": "already_dirty" if already_dirty else "recorded",
        "target": norm,
        "baselines_file": str(get_baselines_path(vault_root)),
    }


def mark_note_read(vault_root: Path, rel_path: str) -> bool:
    """Supprime une note de unread_baselines.json (retour à 0 octet)."""
    norm = rel_path.replace("\\", "/").lstrip("/")
    if not norm:
        return False
    data = load_unread_baselines(vault_root)
    notes = data["notes"]
    if norm in notes:
        del notes[norm]
        save_unread_baselines(vault_root, data)
        return True
    return False


def seed_from_cas(vault_root: Path, cas_engine: Any) -> Dict[str, Any]:
    """
    Initialise _agents/unread_baselines.json depuis les baselines author='henri' du CAS
    pour toutes les notes du coffre dont le contenu disque diffère de la baseline Henri.
    """
    vault_root = Path(vault_root).resolve()
    data = load_unread_baselines(vault_root)
    notes = data["notes"]
    now_iso = datetime.now(timezone.utc).isoformat()

    all_commits = cas_engine.list_snapshots(limit=100000)
    by_target: Dict[str, List[Dict[str, Any]]] = {}
    for c in all_commits:
        t = cas_engine.normalize_target_key(c.get("target", ""))
        if is_trackable_vault_note(t):
            by_target.setdefault(t, []).append(c)

    added = 0
    cleaned = 0
    skipped_same = 0
    missing_disk = 0
    missing_cas_blobs: List[Dict[str, str]] = []

    for norm_t, commits in by_target.items():
        disk_path = vault_root / norm_t
        if not disk_path.is_file():
            missing_disk += 1
            continue

        henri_snap = next(
            (c for c in commits if str(c.get("author", "")).strip().lower() == "henri"),
            None,
        )
        baseline_snap = henri_snap or commits[-1]
        blob_hash = baseline_snap.get("blob_hash", "")
        blob_file = cas_engine.objects_dir / blob_hash[:2] / blob_hash[2:] if len(blob_hash) >= 3 else None
        if not blob_file or not blob_file.is_file():
            missing_cas_blobs.append({"target": norm_t, "commit_id": baseline_snap.get("commit_id", "")[:12], "blob_hash": blob_hash[:12]})
            continue
        baseline_text = cas_engine.restore_snapshot(baseline_snap["commit_id"])
        disk_text = disk_path.read_text(encoding="utf-8", errors="replace")

        if _strip_frontmatter(disk_text).strip() == _strip_frontmatter(baseline_text).strip():
            if norm_t in notes:
                del notes[norm_t]
                cleaned += 1
            else:
                skipped_same += 1
            continue

        if norm_t not in notes:
            latest_msg = commits[0].get("message", "") if commits else ""
            latest_ts = commits[0].get("timestamp", now_iso) if commits else now_iso
            notes[norm_t] = {
                "baseline": baseline_text,
                "updatedAt": latest_ts,
                "updatedBy": commits[0].get("author", "agent") if commits else "agent",
                "summary": latest_msg[:200],
                "seenSlides": {},
            }
            added += 1

    out_path = save_unread_baselines(vault_root, data)
    return {
        "status": "success",
        "baselines_file": str(out_path),
        "total_unread_notes": len(notes),
        "added": added,
        "cleaned": cleaned,
        "skipped_same": skipped_same,
        "missing_disk": missing_disk,
        "missing_cas_blobs": missing_cas_blobs,
        "file_size_bytes": out_path.stat().st_size if out_path.exists() else 0,
    }
