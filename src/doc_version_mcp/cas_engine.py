"""
cas_engine.py — Moteur Content-Addressable Storage (CAS) pour snapshots de documents compressés zlib.
"""

import os
import sys
import json
import zlib
import hashlib
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple


class CASEngine:
    """
    Gestionnaire de stockage adressable par contenu (CAS) pour versions et snapshots de documents.
    Stocke les blobs dédupliqués et compressés avec zlib et hash SHA-256.
    """

    def __init__(self, storage_dir: Optional[Path] = None):
        if storage_dir is not None:
            self.storage_dir = Path(storage_dir).resolve()
        else:
            env_dir = os.environ.get("DOC_VERSION_COMMITS_DIR")
            if env_dir:
                self.storage_dir = Path(env_dir).resolve()
            else:
                default_cas = Path.home() / ".gemini" / "antigravity" / "cas_commits"
                if default_cas.exists():
                    self.storage_dir = default_cas.resolve()
                else:
                    self.storage_dir = Path(tempfile.gettempdir()) / "doc_version_commits"

        self.objects_dir = self.storage_dir / "objects"
        self.commits_dir = self.storage_dir / "commits"
        self.index_file = self.storage_dir / "index.json"
        self.style_audit_file = self.storage_dir / "style_audit.json"

        self.objects_dir.mkdir(parents=True, exist_ok=True)
        self.commits_dir.mkdir(parents=True, exist_ok=True)

    def _hash_content(self, data: bytes) -> str:
        """Calcule le SHA-256 d'un flux binaire."""
        return hashlib.sha256(data).hexdigest()

    def _store_blob(self, content_bytes: bytes) -> Tuple[str, int]:
        """
        Compresse et stocke un blob dans objects/<hash[:2]>/<hash[2:]>.
        Retourne (blob_hash, compressed_size).
        """
        blob_hash = self._hash_content(content_bytes)
        obj_subdir = self.objects_dir / blob_hash[:2]
        obj_subdir.mkdir(parents=True, exist_ok=True)
        obj_file = obj_subdir / blob_hash[2:]

        if not obj_file.exists():
            compressed = zlib.compress(content_bytes, level=9)
            obj_file.write_bytes(compressed)
            return blob_hash, len(compressed)
        else:
            return blob_hash, obj_file.stat().st_size

    def _read_blob(self, blob_hash: str) -> bytes:
        """Lit et décompresse un blob à partir de son hash SHA-256."""
        obj_file = self.objects_dir / blob_hash[:2] / blob_hash[2:]
        if not obj_file.exists():
            raise FileNotFoundError(f"Blob introuvable dans le CAS : {blob_hash}")
        compressed = obj_file.read_bytes()
        return zlib.decompress(compressed)

    def _load_index(self) -> Dict[str, Any]:
        """Charge l'index des cibles vers commits."""
        if not self.index_file.exists():
            return {"targets": {}}
        try:
            return json.loads(self.index_file.read_text(encoding="utf-8"))
        except Exception:
            return {"targets": {}}

    def _save_index(self, index_data: Dict[str, Any]) -> None:
        """Sauvegarde l'index de manière atomique."""
        tmp_file = self.storage_dir / f"index_{os.getpid()}_{datetime.now().timestamp()}.tmp"
        tmp_file.write_text(json.dumps(index_data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp_file.replace(self.index_file)

    def _find_commit_path(self, commit_id: str) -> Optional[Path]:
        """Retrouve le fichier de commit exact ou par préfixe."""
        exact = self.commits_dir / f"{commit_id}.json"
        if exact.exists():
            return exact

        # Recherche par préfixe
        matches = list(self.commits_dir.glob(f"{commit_id}*.json"))
        if len(matches) == 1:
            return matches[0]
        elif len(matches) > 1:
            raise ValueError(f"Identifiant de commit ambigu '{commit_id}' ({len(matches)} correspondances).")
        return None

    def create_snapshot(
        self,
        target: str,
        message: str,
        author: str = "agent",
        is_pinned: bool = False,
        content: Optional[str] = None,
        mode: str = "paper",
        commit_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        style_audit: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Crée un instantané dans le CAS.
        Si content n'est pas fourni, le lit depuis le fichier cible sur le disque.
        """
        target_path_str = target.strip()
        if content is None or content == "":
            p = Path(target_path_str)
            if not p.is_absolute():
                p = p.resolve()
            if not p.exists() or not p.is_file():
                raise FileNotFoundError(f"Fichier cible introuvable pour snapshot : {target_path_str}")
            raw_text = p.read_text(encoding="utf-8", errors="replace")
            norm_target = p.as_posix()
        else:
            raw_text = content
            norm_target = target_path_str.replace("\\", "/")

        content_bytes = raw_text.encode("utf-8")
        blob_hash, compressed_size = self._store_blob(content_bytes)

        # Récupération du parent commit s'il existe
        index_data = self._load_index()
        targets_map = index_data.setdefault("targets", {})
        parent_id = targets_map.get(norm_target)

        now_utc = timestamp if timestamp else datetime.now(timezone.utc).isoformat()

        # Construction du commit ID
        if commit_id:
            actual_commit_id = commit_id
        else:
            commit_seed = f"{norm_target}|{now_utc}|{blob_hash}|{message}|{author}|{parent_id or ''}".encode("utf-8")
            actual_commit_id = hashlib.sha256(commit_seed).hexdigest()

        commit_record = {
            "commit_id": actual_commit_id,
            "target": norm_target,
            "message": message,
            "author": author,
            "timestamp": now_utc,
            "is_pinned": bool(is_pinned),
            "mode": mode,
            "blob_hash": blob_hash,
            "byte_size": len(content_bytes),
            "compressed_size": compressed_size,
            "parent_commit_id": parent_id
        }
        if style_audit is not None:
            commit_record["style_audit"] = style_audit

        commit_file = self.commits_dir / f"{actual_commit_id}.json"
        commit_file.write_text(json.dumps(commit_record, indent=2, ensure_ascii=False), encoding="utf-8")

        # Sauvegarde persistante de l'audit de style si présent
        if style_audit is not None:
            self.save_style_audit(actual_commit_id, style_audit, target=norm_target)

        # Mise à jour de l'index
        targets_map[norm_target] = actual_commit_id
        self._save_index(index_data)

        return commit_record

    def save_style_audit(self, commit_id: str, audit_data: Dict[str, Any], target: Optional[str] = None) -> None:
        """Enregistre un audit de style dans le stockage CAS."""
        from .style_guard import save_style_audit as sg_save_audit
        sg_save_audit(commit_id, audit_data, target=target, storage_dir=self.storage_dir)

    def load_style_audit(self, commit_id: str, target: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Charge un audit de style depuis le stockage CAS."""
        from .style_guard import load_style_audit as sg_load_audit
        return sg_load_audit(commit_id, target=target, storage_dir=self.storage_dir)

    def get_commit(self, commit_id: str) -> Dict[str, Any]:
        """Charge les métadonnées d'un commit."""
        c_path = self._find_commit_path(commit_id)
        if not c_path or not c_path.exists():
            raise FileNotFoundError(f"Commit introuvable : {commit_id}")
        data = json.loads(c_path.read_text(encoding="utf-8"))
        if "style_audit" not in data:
            audit = self.load_style_audit(commit_id, target=data.get("target"))
            if audit:
                data["style_audit"] = audit
        return data

    def restore_snapshot(self, commit_id: str, target_file: Optional[str] = None) -> str:
        """
        Restaure le contenu d'un commit.
        Si target_file est spécifié, écrit également le contenu sur le disque.
        Retourne le texte restauré en UTF-8.
        """
        commit_data = self.get_commit(commit_id)
        blob_hash = commit_data["blob_hash"]
        raw_bytes = self._read_blob(blob_hash)
        text_content = raw_bytes.decode("utf-8", errors="replace")

        if target_file:
            dest_p = Path(target_file)
            # Ne pas écrire sur disque si c'est un nom virtuel sans dossier et qui n'existe pas
            if dest_p.is_absolute() or "/" in target_file or "\\" in target_file:
                dest_p.parent.mkdir(parents=True, exist_ok=True)
                dest_p.write_text(text_content, encoding="utf-8")

        return text_content

    def get_commit_tree(self, commit_id: str) -> Dict[str, Any]:
        """Retourne la chaîne d'ascendance d'un commit."""
        chain: List[Dict[str, Any]] = []
        curr_id: Optional[str] = commit_id

        visited = set()
        while curr_id and curr_id not in visited:
            visited.add(curr_id)
            try:
                c_data = self.get_commit(curr_id)
                chain.append(c_data)
                curr_id = c_data.get("parent_commit_id")
            except Exception:
                break

        return {
            "root_commit_id": commit_id,
            "depth": len(chain),
            "history": chain
        }

    def list_snapshots(
        self,
        target: str = "",
        limit: int = 10,
        mode: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Liste les snapshots ordonnés par date décroissante,
        avec filtrage optionnel par cible et mode.
        """
        commits: List[Dict[str, Any]] = []
        norm_target = target.strip().replace("\\", "/").lower() if target else ""

        for f in self.commits_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                c_target = data.get("target", "").replace("\\", "/").lower()
                c_mode = data.get("mode", "").lower()

                if norm_target:
                    if "/" in norm_target:
                        matches_path = (
                            norm_target == c_target or
                            norm_target in c_target or
                            c_target in norm_target
                        )
                        if not matches_path:
                            continue
                    else:
                        if Path(c_target).name.lower() != norm_target:
                            continue
                if mode and (mode.lower() != c_mode):
                    continue

                if "style_audit" not in data:
                    audit = self.load_style_audit(data.get("commit_id", ""), target=data.get("target"))
                    if audit:
                        data["style_audit"] = audit

                commits.append(data)
            except Exception:
                continue

        # Tri par timestamp décroissant avec profondeur parentale pour départager les timestamps identiques
        parent_map = {c.get("commit_id"): c.get("parent_commit_id") for c in commits if c.get("commit_id")}
        depth_memo: Dict[str, int] = {}

        def get_depth(cid: str) -> int:
            if not cid or cid not in parent_map:
                return 0
            if cid in depth_memo:
                return depth_memo[cid]
            p = parent_map.get(cid)
            if p and p != cid and p in parent_map:
                depth_memo[cid] = 1 + get_depth(p)
            else:
                depth_memo[cid] = 0
            return depth_memo[cid]

        commits.sort(
            key=lambda c: (c.get("timestamp", ""), get_depth(c.get("commit_id", ""))),
            reverse=True
        )
        return commits[:limit]

    def prune_expired(
        self,
        ttl_days: int = 14,
        max_mb: int = 500,
        keep_baselines: bool = True
    ) -> Dict[str, Any]:
        """
        Purge les commits expirés selon le TTL (sauf is_pinned si keep_baselines),
        régule la taille totale sous max_mb et supprime les blobs orphelins.
        """
        now = datetime.now(timezone.utc)
        all_commits = self.list_snapshots(limit=100000)

        pruned_commit_ids: List[str] = []
        kept_commit_ids: Set[str] = set()

        for c in all_commits:
            cid = c["commit_id"]
            is_pinned = c.get("is_pinned", False)
            ts_str = c.get("timestamp")
            is_expired = False

            if ts_str:
                try:
                    dt = datetime.fromisoformat(ts_str)
                    age_days = (now - dt).total_seconds() / 86400.0
                    if age_days > ttl_days:
                        is_expired = True
                except Exception:
                    pass

            if is_expired and not (is_pinned and keep_baselines):
                pruned_commit_ids.append(cid)
            else:
                kept_commit_ids.add(cid)

        # Vérification de quota max_mb
        def calculate_cas_size_bytes() -> int:
            total = 0
            for root, _, files in os.walk(self.storage_dir):
                for f in files:
                    total += os.path.getsize(os.path.join(root, f))
            return total

        max_bytes = max_mb * 1024 * 1024

        # Suppression des commits expirés
        for cid in pruned_commit_ids:
            c_file = self.commits_dir / f"{cid}.json"
            if c_file.exists():
                try:
                    c_file.unlink()
                except Exception:
                    pass

        # Si l'espace dépasse encore max_mb, purger les plus anciens non-pinned
        current_size = calculate_cas_size_bytes()
        if current_size > max_bytes:
            remaining_commits = [c for c in all_commits if c["commit_id"] in kept_commit_ids]
            # Tri ascendant pour supprimer les plus vieux d'abord
            remaining_commits.sort(key=lambda c: c.get("timestamp", ""))
            for c in remaining_commits:
                if current_size <= max_bytes:
                    break
                cid = c["commit_id"]
                if keep_baselines and c.get("is_pinned", False):
                    continue
                c_file = self.commits_dir / f"{cid}.json"
                if c_file.exists():
                    try:
                        c_file.unlink()
                        pruned_commit_ids.append(cid)
                        kept_commit_ids.discard(cid)
                        current_size = calculate_cas_size_bytes()
                    except Exception:
                        pass

        # Nettoyage des blobs orphelins
        active_blob_hashes: Set[str] = set()
        for f in self.commits_dir.glob("*.json"):
            try:
                c_data = json.loads(f.read_text(encoding="utf-8"))
                bh = c_data.get("blob_hash")
                if bh:
                    active_blob_hashes.add(bh)
            except Exception:
                pass

        pruned_blobs_count = 0
        freed_blob_bytes = 0

        for obj_subdir in self.objects_dir.iterdir():
            if obj_subdir.is_dir():
                prefix = obj_subdir.name
                for obj_file in obj_subdir.iterdir():
                    if obj_file.is_file():
                        full_hash = prefix + obj_file.name
                        if full_hash not in active_blob_hashes:
                            sz = obj_file.stat().st_size
                            try:
                                obj_file.unlink()
                                pruned_blobs_count += 1
                                freed_blob_bytes += sz
                            except Exception:
                                pass

        # Réajuster l'index
        index_data = self._load_index()
        targets_map = index_data.get("targets", {})
        cleaned_targets = {}
        for tgt, cid in targets_map.items():
            if cid in kept_commit_ids:
                cleaned_targets[tgt] = cid
        index_data["targets"] = cleaned_targets
        self._save_index(index_data)

        return {
            "pruned_commits_count": len(pruned_commit_ids),
            "pruned_blobs_count": pruned_blobs_count,
            "freed_bytes": freed_blob_bytes,
            "remaining_commits_count": len(kept_commit_ids),
            "current_cas_size_bytes": calculate_cas_size_bytes()
        }
