"""
stealth_bridge.py — Réécriture automatique StealthRL des paragraphes de prose modifiés avant génération d'un diff.

Le moteur `stealth_rewriter.py` (Qwen3-4B-Instruct-2507 + LoRA StealthRL, GPU CUDA) s'exécute dans un interpréteur
Python disposant de torch CUDA ou via un démon local persistant (--serve sur http://127.0.0.1:18777) :
- DOC_VERSION_STEALTH_SCRIPT : chemin absolu de stealth_rewriter.py.
- STEALTH_PYTHON_EXE / DOC_VERSION_STEALTH_PYTHON : interpréteur Python CUDA explicite.
- Sondage ordonné et mise en cache mémoire + disque pour une résolution en < 0.1 ms.
- Découpage chirurgical par fenêtres de phrases modifiées (<= 85 mots) préservant les phrases inchangées.
"""

import os
import re
import sys
import json
import time
import shutil
import difflib
import tempfile
import urllib.request
import urllib.error
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from .style_guard import check_style

# Environnements LaTeX dont le contenu est de la prose (tout autre environnement est ignoré : tableaux, figures, maths…)
PROSE_ENVIRONMENTS = {"document", "abstract", "quote", "quotation"}

# Lignes LaTeX structurelles (jamais réécrites)
STRUCTURAL_LINE_RE = re.compile(
    r'^\s*(?:%|\\(?:begin|end|section|subsection|subsubsection|paragraph|chapter|part|item|caption|label|'
    r'centering|includegraphics|vspace|hspace|maketitle|bibliography|bibliographystyle|input|include|'
    r'newcommand|renewcommand|def|usepackage|documentclass|title|author|affiliation|email|keywords|'
    r'ccsdesc|setcopyright|acm[A-Za-z]*|appendix|printbibliography|clearpage|newpage|footnotetext)\b)'
)
ENV_RE = re.compile(r'\\(begin|end)\{([^}]+)\}')
MIN_PROSE_WORDS = 5

# Cache mémoire et fichier cache disque pour la résolution du runtime CUDA (< 0.1 ms au 2e appel)
_RUNTIME_CACHE: Optional[Tuple[str, Path]] = None
_CACHE_FILE = Path(tempfile.gettempdir()) / "doc_version_stealth_runtime_v1.json"

PREFERRED_CUDA_CANDIDATES = [
    Path(r"C:\Users\Jamet\.pyenv\pyenv-win\versions\3.12.3\python.exe"),
    Path.home() / "AppData/Local/Programs/Python/Python312/python.exe",
    Path(r"C:\Users\Jamet\AppData\Local\Programs\Python\Python312\python.exe"),
    Path(r"C:\Users\hjamet\AppData\Local\Programs\Python\Python312\python.exe"),
    Path(r"C:\Users\Jamet\.pyenv\pyenv-win\versions\3.11.9\python.exe"),
]

DEFAULT_SCRIPT_CANDIDATES = [
    Path(r"c:\Users\Jamet\Documents\VoiceNotes\_agents\scripts-for-skills\stealth_rewriter.py"),
    Path(r"c:\Users\hjamet\Documents\VoiceNotes\_agents\scripts-for-skills\stealth_rewriter.py"),
    Path.home() / "Documents/VoiceNotes/_agents/scripts-for-skills/stealth_rewriter.py",
]

DEFAULT_DAEMON_HOST = "127.0.0.1"
DEFAULT_DAEMON_PORT = 18777

ACADEMIC_ABBREVIATIONS = (
    "et al.", "e.g.", "i.e.", "Fig.", "Eq.", "Sec.", "vs.", "p.", "Prof.", "Dr.", "cf.", "etc.", "al."
)


def _clear_runtime_cache() -> None:
    """Réinitialise le cache mémoire et supprime le fichier de cache disque."""
    global _RUNTIME_CACHE
    _RUNTIME_CACHE = None
    if _CACHE_FILE.exists():
        try:
            _CACHE_FILE.unlink()
        except OSError:
            pass


def _is_latex(raw_text: str, target_path: Optional[Path]) -> bool:
    return (target_path is not None and target_path.suffix.lower() == ".tex") or "\\begin{document}" in raw_text


def _word_count_outside_macros(text: str) -> int:
    no_math = re.sub(r'\$[^$]*\$', ' ', text)
    no_cmd = re.sub(r'\\[a-zA-Z@]+\*?(?:\[[^\]]*\])*(?:\{[^{}]*\})*', ' ', no_math)
    return len(re.findall(r'\b[A-Za-zÀ-ÿ]{2,}\b', no_cmd))


def _normalize(t: str) -> str:
    return re.sub(r'\s+', ' ', t).strip()


def split_sentences(text: str) -> List[str]:
    """
    Découpe un texte en phrases en protégeant les abréviations académiques
    (et al., e.g., i.e., Fig., Eq., Sec., vs., p., Prof., Dr., etc.) et formules.
    """
    t = text
    for idx, ab in enumerate(ACADEMIC_ABBREVIATIONS):
        t = re.sub(rf'\b{re.escape(ab)}', f"\x00AB{idx}\x00", t, flags=re.IGNORECASE)
    chunks = re.split(r'(?:(?<=[.!?])|(?<=:D)|(?<=:\))|(?<=\^\^))\s+(?=[A-Z$\\\(\x00])', t)
    sentences: List[str] = []
    for c in chunks:
        clean_c = c.strip()
        if not clean_c:
            continue
        for idx, ab in enumerate(ACADEMIC_ABBREVIATIONS):
            clean_c = clean_c.replace(f"\x00AB{idx}\x00", ab)
        sentences.append(clean_c)
    return sentences


def group_sentences_into_windows(
    sentences: List[str], max_words: int = 85, max_sentences: int = 3
) -> List[List[str]]:
    """Groupe une liste de phrases contiguës en fenêtres de <= max_words mots (et max 3 phrases)."""
    windows: List[List[str]] = []
    curr: List[str] = []
    curr_words = 0

    for s in sentences:
        s_words = _word_count_outside_macros(s)
        if curr and (curr_words + s_words > max_words or len(curr) >= max_sentences):
            windows.append(curr)
            curr = [s]
            curr_words = s_words
        else:
            curr.append(s)
            curr_words += s_words

    if curr:
        windows.append(curr)
    return windows


def plan_paragraph_sentence_rewrites(
    old_para: Optional[str],
    new_para: str,
    max_words: int = 85
) -> List[Dict[str, Any]]:
    """
    Découpe chirurgicalement new_para en fragments ordonnés :
    - 'unchanged' : phrases identiques à old_para conservées 100% intactes sans envoi au modèle.
    - 'modified' : phrases insérées ou altérées, regroupées en fenêtres contiguës de <= max_words mots.
    """
    new_sents = split_sentences(new_para)
    if not new_sents:
        return [{"type": "unchanged", "text": new_para, "sentences": []}]

    word_count = _word_count_outside_macros(new_para)
    if not old_para:
        if word_count <= max_words:
            return [{"type": "modified", "text": new_para, "sentences": new_sents}]
        windows = group_sentences_into_windows(new_sents, max_words=max_words)
        return [{"type": "modified", "text": " ".join(w), "sentences": w} for w in windows]

    old_sents = split_sentences(old_para)
    matcher = difflib.SequenceMatcher(
        None, [_normalize(s) for s in old_sents], [_normalize(s) for s in new_sents]
    )

    plan: List[Dict[str, Any]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            matched_sents = new_sents[j1:j2]
            if matched_sents:
                plan.append({
                    "type": "unchanged",
                    "text": " ".join(matched_sents),
                    "sentences": matched_sents
                })
        elif tag in ("replace", "insert"):
            mod_sents = new_sents[j1:j2]
            if mod_sents:
                windows = group_sentences_into_windows(mod_sents, max_words=max_words)
                for w in windows:
                    plan.append({
                        "type": "modified",
                        "text": " ".join(w),
                        "sentences": w
                    })
        elif tag == "delete":
            pass

    # Si rien n'a été marqué modified (ex. modif cosmétique ignorée par matcher), marquer tout le paragraphe
    if not any(p["type"] == "modified" for p in plan) and _normalize(old_para) != _normalize(new_para):
        windows = group_sentences_into_windows(new_sents, max_words=max_words)
        return [{"type": "modified", "text": " ".join(w), "sentences": w} for w in windows]

    return plan


def one_sentence_per_line(text: str) -> str:
    """Rétablit la convention « une phrase par ligne » d'un segment source multi-lignes."""
    sents = split_sentences(text)
    if len(sents) > 1:
        return "\n".join(sents)
    return text


def extract_prose_segments(raw_text: str, is_latex: bool) -> List[Tuple[int, int, str]]:
    """
    Retourne les segments de prose (ligne_début, ligne_fin exclusive, texte) d'un document.
    LaTeX : lignes hors structure, situées dans un environnement de prose (document/abstract/quote).
    Markdown/texte : blocs séparés par une ligne vide, hors titres, code, tableaux, citations.
    """
    lines = raw_text.split("\n")
    segments: List[Tuple[int, int, str]] = []
    start: Optional[int] = None

    def _flush(end: int) -> None:
        nonlocal start
        if start is not None:
            seg = "\n".join(lines[start:end])
            if _word_count_outside_macros(seg) >= MIN_PROSE_WORDS:
                segments.append((start, end, seg))
        start = None

    if is_latex:
        env_stack: List[str] = []
        for i, line in enumerate(lines):
            structural = (not line.strip()) or bool(STRUCTURAL_LINE_RE.match(line))
            in_prose_env = bool(env_stack) and all(e in PROSE_ENVIRONMENTS for e in env_stack)
            if structural or not in_prose_env:
                _flush(i)
            elif start is None:
                start = i
            for kind, env in ENV_RE.findall(re.sub(r'(?<!\\)%.*$', '', line)):
                if kind == "begin":
                    env_stack.append(env)
                else:
                    if not env_stack or env_stack[-1] != env:
                        raise ValueError(f"[FAIL-FAST] Environnement LaTeX déséquilibré ligne {i + 1} : \\end{{{env}}} (pile={env_stack})")
                    env_stack.pop()
        _flush(len(lines))
        return segments

    in_code = False
    in_frontmatter = bool(lines) and lines[0].strip() == "---"
    for i, line in enumerate(lines):
        s = line.strip()
        if in_frontmatter:
            if i > 0 and s == "---":
                in_frontmatter = False
            continue
        if s.startswith("```"):
            _flush(i)
            in_code = not in_code
            continue
        non_prose = (
            in_code or not s or s.startswith(("#", "|", ">", "<", "!", "---", "- ", "* ", "+ "))
            or bool(re.match(r'^\d+[.)]\s', s))
            or bool(re.match(r'^(?:Subject|Objet)\s*:', s, flags=re.IGNORECASE))
        )
        if non_prose:
            _flush(i)
        elif start is None:
            start = i
    _flush(len(lines))
    return segments


def resolve_stealth_runtime() -> Tuple[str, Path]:
    """
    Résout (interpréteur Python CUDA, script stealth_rewriter.py) avec double cache mémoire + disque.
    Garantit une latence < 0.1 ms après la première résolution.
    """
    global _RUNTIME_CACHE
    if _RUNTIME_CACHE is not None:
        return _RUNTIME_CACHE

    if _CACHE_FILE.exists():
        try:
            cache_data = json.loads(_CACHE_FILE.read_text(encoding="utf-8"))
            exe = cache_data.get("python_exe")
            script = Path(cache_data.get("script_path", ""))
            if exe and Path(exe).is_file() and script.is_file():
                _RUNTIME_CACHE = (exe, script)
                return _RUNTIME_CACHE
        except Exception:
            pass

    # Résolution du script stealth_rewriter.py
    script_env = os.environ.get("DOC_VERSION_STEALTH_SCRIPT", "").strip()
    script: Optional[Path] = None
    if script_env:
        candidate_s = Path(script_env)
        if candidate_s.is_file():
            script = candidate_s
    if not script:
        for s_cand in DEFAULT_SCRIPT_CANDIDATES:
            if s_cand.is_file():
                script = s_cand
                break
    if not script:
        raise RuntimeError(
            "[FAIL-FAST] stealth_rewriter.py introuvable : définir DOC_VERSION_STEALTH_SCRIPT."
        )

    # Résolution ordonnée et dédupliquée de l'interpréteur Python avec CUDA
    py_env = (
        os.environ.get("STEALTH_PYTHON_EXE", "").strip()
        or os.environ.get("DOC_VERSION_STEALTH_PYTHON", "").strip()
    )
    raw_candidates: List[str] = []
    if py_env:
        raw_candidates.append(py_env)
    for p_cand in PREFERRED_CUDA_CANDIDATES:
        if p_cand.is_file():
            raw_candidates.append(str(p_cand))
    raw_candidates.append(sys.executable)
    which_py = shutil.which("python")
    if which_py:
        raw_candidates.append(which_py)

    candidates: List[str] = []
    seen_norm: set = set()
    for c in raw_candidates:
        if not c or not Path(c).is_file():
            continue
        try:
            norm_c = os.path.normcase(str(Path(c).resolve()))
        except Exception:
            norm_c = os.path.normcase(c)
        if norm_c not in seen_norm:
            seen_norm.add(norm_c)
            candidates.append(c)

    probes = []
    for exe in candidates:
        try:
            res = subprocess.run(
                [exe, "-c", "import sys, torch; sys.exit(0 if torch.cuda.is_available() else 3)"],
                capture_output=True, text=True, timeout=30
            )
            probes.append(f"{exe} -> code {res.returncode}")
            if res.returncode == 0:
                _RUNTIME_CACHE = (exe, script)
                try:
                    _CACHE_FILE.write_text(
                        json.dumps({"python_exe": exe, "script_path": str(script)}),
                        encoding="utf-8"
                    )
                except Exception:
                    pass
                return _RUNTIME_CACHE
        except Exception as e:
            probes.append(f"{exe} -> erreur {e}")

    raise RuntimeError(
        "[FAIL-FAST] Aucun interpréteur Python avec torch CUDA pour StealthRL "
        f"(sondes : {'; '.join(probes)}). Définir STEALTH_PYTHON_EXE."
    )


def check_daemon_health(host: str = DEFAULT_DAEMON_HOST, port: int = DEFAULT_DAEMON_PORT, timeout: float = 0.3) -> bool:
    """Vérifie si le démon HTTP StealthRL local est actif et prêt."""
    url = f"http://{host}:{port}/health"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                return data.get("status") == "ok" and (
                    data.get("service") == "stealth_rewriter" or "models_loaded" in data
                )
    except Exception:
        pass
    return False


def start_stealth_daemon(
    python_exe: str,
    script_path: Path,
    host: str = DEFAULT_DAEMON_HOST,
    port: int = DEFAULT_DAEMON_PORT,
    idle_timeout: int = 900,
    max_wait_seconds: float = 120.0
) -> bool:
    """Démarre stealth_rewriter.py --serve en arrière-plan détaché et attend /health."""
    if check_daemon_health(host, port, timeout=0.3):
        return True

    cmd = [
        python_exe,
        str(script_path),
        "--serve",
        "--host", host,
        "--port", str(port),
        "--idle-timeout", str(idle_timeout)
    ]
    creationflags = 0
    if sys.platform == "win32":
        creationflags = (
            getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
            | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
        )

    log_file = Path(tempfile.gettempdir()) / "doc_version_stealth_daemon.log"
    with open(log_file, "a", encoding="utf-8") as out_f:
        subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=out_f,
            stderr=subprocess.STDOUT,
            creationflags=creationflags,
            close_fds=True
        )

    start_wait = time.time()
    while time.time() - start_wait < max_wait_seconds:
        time.sleep(0.5)
        if check_daemon_health(host, port, timeout=0.3):
            return True
    return False


def call_stealth_daemon(
    paragraphs: List[str],
    host: str = DEFAULT_DAEMON_HOST,
    port: int = DEFAULT_DAEMON_PORT,
    mode: str = "paper",
    target_score: float = 0.20,
    n_candidates: int = 2,
    timeout: float = 60.0
) -> Optional[Dict[str, Any]]:
    """Envoie une requête POST /rewrite au démon HTTP local persistant."""
    url = f"http://{host}:{port}/rewrite"
    payload = json.dumps({
        "paragraphs": paragraphs,
        "mode": mode,
        "target_score": target_score,
        "n_candidates": n_candidates
    }, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                data["engine_mode"] = "daemon"
                return data
    except Exception as e:
        sys.stderr.write(f"[WARN] Appel démon StealthRL échoué ({e}) -> repli CLI\n")
    return None


def call_stealth_cli(
    paragraphs: List[str],
    python_exe: str,
    script_path: Path,
    mode: str = "paper",
    target_score: float = 0.20,
    n_candidates: int = 2
) -> Dict[str, Any]:
    """Exécute stealth_rewriter.py en mode CLI (--paragraphs-json)."""
    start_t = time.time()
    with tempfile.TemporaryDirectory(prefix="doc_version_stealth_cli_") as tmp:
        in_json = Path(tmp) / "in.json"
        out_json = Path(tmp) / "out.json"
        in_json.write_text(
            json.dumps([{"id": i, "text": p} for i, p in enumerate(paragraphs)], ensure_ascii=False),
            encoding="utf-8"
        )
        cmd = [
            python_exe,
            str(script_path),
            "--paragraphs-json", str(in_json),
            "-o", str(out_json)
        ]
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace"
        )
        if proc.returncode != 0:
            raise RuntimeError(f"[FAIL-FAST] stealth_rewriter.py CLI a échoué (code {proc.returncode}) :\n{proc.stderr[-3000:]}")

        elapsed_ms = (time.time() - start_t) * 1000.0
        raw_out = json.loads(out_json.read_text(encoding="utf-8"))

        if isinstance(raw_out, dict) and "rewritten" in raw_out:
            raw_out["engine_mode"] = "cli"
            raw_out.setdefault("total_elapsed_ms", elapsed_ms)
            return raw_out
        elif isinstance(raw_out, list):
            rewritten = []
            stats = []
            for i, r in enumerate(raw_out):
                cand_list = r.get("candidates_ranked", [])
                text_res = cand_list[0]["text"] if cand_list else r.get("humanized", paragraphs[i])
                rewritten.append(text_res)
                stats.append({
                    "changed": (text_res != paragraphs[i]),
                    "score_before": r.get("risk_before", 0.0),
                    "score_after": r.get("risk_after", 0.0),
                    "candidates_ranked": cand_list,
                    "status": r.get("status", "VALIDÉ" if cand_list else "REJET_GATES"),
                    "gate_rejections": r.get("gate_rejections", []),
                    "rounds": r.get("rounds", 1),
                    "elapsed_ms": elapsed_ms / max(len(raw_out), 1)
                })
            return {
                "rewritten": rewritten,
                "stats": stats,
                "total_elapsed_ms": elapsed_ms,
                "engine_mode": "cli"
            }
        else:
            raise ValueError(f"[FAIL-FAST] Format de sortie inattendu de stealth_rewriter.py : {type(raw_out)}")


def execute_stealth_batch(
    paragraphs: List[str],
    python_exe: str,
    script_path: Path,
    use_daemon: bool = True,
    daemon_host: str = DEFAULT_DAEMON_HOST,
    daemon_port: int = DEFAULT_DAEMON_PORT,
    mode: str = "paper",
    target_score: float = 0.20,
    n_candidates: int = 2
) -> Dict[str, Any]:
    """Coordonne l'exécution par démon HTTP avec auto-start et repli transparent sur CLI."""
    if use_daemon:
        if not check_daemon_health(daemon_host, daemon_port):
            start_stealth_daemon(python_exe, script_path, host=daemon_host, port=daemon_port)
        if check_daemon_health(daemon_host, daemon_port):
            res = call_stealth_daemon(
                paragraphs, host=daemon_host, port=daemon_port,
                mode=mode, target_score=target_score, n_candidates=n_candidates
            )
            if res is not None:
                return res

    return call_stealth_cli(
        paragraphs, python_exe, script_path, mode=mode,
        target_score=target_score, n_candidates=n_candidates
    )


def format_stealth_callout(stealth_report: Dict[str, Any]) -> str:
    """Génère le bloc d'en-tête Markdown pour l'artéfact de diff."""
    engine_mode = stealth_report.get("engine_mode", "daemon")
    latency_ms = stealth_report.get("total_elapsed_ms", 0.0)
    rewritten_count = stealth_report.get("segments_rewritten", 0)
    total_count = stealth_report.get("segments_modified", 0)

    lines = [
        "> [!NOTE]",
        "> **🛡️ Obfuscation Automatique StealthRL**",
        f"> - **Mode Moteur** : `{engine_mode}` | **Latence GPU** : `{latency_ms:.1f} ms` | **Passages réécrits** : `{rewritten_count}/{total_count}`",
        ">",
        "> | Passage | Lignes | Risque Avant | Risque Après | Delta | Statut |",
        "> | :--- | :--- | :---: | :---: | :---: | :---: |"
    ]
    for i, seg in enumerate(stealth_report.get("segments", []), 1):
        lines_info = seg.get("lines", "—")
        b_risk = seg.get("risk_before", 0.0)
        a_risk = seg.get("risk_after", 0.0)
        delta = (b_risk - a_risk) * 100
        if abs(delta) < 0.05:
            delta_str = "0.0%"
        elif delta > 0:
            delta_str = f"-{delta:.1f}%"
        else:
            delta_str = f"+{-delta:.1f}%"
        status = seg.get("status", "VALIDÉ")
        if status == "VALIDÉ":
            status_label = "🟢 Validé"
        elif status == "ALREADY_CLEAN":
            status_label = "🟢 Certifié (≤ 20%)"
        else:
            status_label = f"⚠️ {status}"
        lines.append(f"> | {i} | {lines_info} | {b_risk*100:.1f}% | {a_risk*100:.1f}% | {delta_str} | {status_label} |")
    return "\n".join(lines) + "\n\n"


def apply_stealth_to_modified_prose(
    old_raw: str,
    new_raw: str,
    target_path: Optional[Path],
    language: str,
    context_mode: str,
    allowed_terms: Optional[List[str]],
    use_daemon: bool = True,
    daemon_host: str = DEFAULT_DAEMON_HOST,
    daemon_port: int = DEFAULT_DAEMON_PORT,
    target_score: float = 0.20,
    n_candidates: int = 2
) -> Tuple[str, Dict[str, Any]]:
    """
    Réécrit via StealthRL chaque fragment de prose modifié (<= 85 mots), préserve intactes les
    phrases inchangées d'un long paragraphe, valide via le Style Guard et réassemble le document.
    """
    is_latex = _is_latex(new_raw, target_path)
    old_segs = extract_prose_segments(old_raw, is_latex) if old_raw else []
    new_segs = extract_prose_segments(new_raw, is_latex)
    old_norm_set = {_normalize(seg) for _, _, seg in old_segs}

    # Identifier les segments modifiés
    modified_records: List[Dict[str, Any]] = []
    for s, e, seg in new_segs:
        if _normalize(seg) in old_norm_set:
            continue
        # Recherche du meilleur homologue dans old_segs par similarité
        best_old: Optional[str] = None
        best_ratio = 0.0
        for _, _, o_seg in old_segs:
            ratio = difflib.SequenceMatcher(None, _normalize(o_seg), _normalize(seg)).ratio()
            if ratio > best_ratio and ratio >= 0.25:
                best_ratio = ratio
                best_old = o_seg

        plan = plan_paragraph_sentence_rewrites(best_old, seg, max_words=85)
        modified_records.append({
            "start": s,
            "end": e,
            "original_seg": seg,
            "old_seg": best_old,
            "plan": plan
        })

    if not modified_records and new_segs:
        for s, e, seg in new_segs:
            plan = plan_paragraph_sentence_rewrites("", seg, max_words=85)
            modified_records.append({
                "start": s,
                "end": e,
                "original_seg": seg,
                "old_seg": "",
                "plan": plan
            })

    report: Dict[str, Any] = {
        "segments_modified": len(modified_records),
        "segments_rewritten": 0,
        "segments": [],
        "engine_mode": "daemon" if use_daemon else "cli",
        "total_elapsed_ms": 0.0
    }
    if not modified_records:
        return new_raw, report

    # Collecter toutes les fenêtres à réécrire
    pending_windows: List[Tuple[int, int, str]] = []  # (rec_idx, plan_idx, text)
    for r_idx, rec in enumerate(modified_records):
        for p_idx, frag in enumerate(rec["plan"]):
            if frag["type"] == "modified":
                pending_windows.append((r_idx, p_idx, frag["text"]))

    if not pending_windows:
        return new_raw, report

    python_exe, script = resolve_stealth_runtime()
    report["python"] = python_exe
    report["script"] = str(script)

    batch_res = execute_stealth_batch(
        paragraphs=[w[2] for w in pending_windows],
        python_exe=python_exe,
        script_path=script,
        use_daemon=use_daemon,
        daemon_host=daemon_host,
        daemon_port=daemon_port,
        mode="paper",
        target_score=target_score,
        n_candidates=n_candidates
    )
    report["engine_mode"] = batch_res.get("engine_mode", report["engine_mode"])
    report["total_elapsed_ms"] = batch_res.get("total_elapsed_ms", 0.0)

    rewritten_texts = batch_res.get("rewritten", [w[2] for w in pending_windows])
    stats_list = batch_res.get("stats", [{} for _ in pending_windows])

    # Apparier les résultats et valider par Style Guard
    for (r_idx, p_idx, orig_text), rew_text, stat in zip(pending_windows, rewritten_texts, stats_list):
        chosen_text = None
        style_rejects = 0

        score_before = stat.get("score_before", 0.0)
        score_after = stat.get("score_after", 0.0)

        # Si candidates_ranked est absent mais changed=True et rew_text fourni -> fallback gracieux
        candidates = stat.get("candidates_ranked", [])
        if not candidates and stat.get("changed") and rew_text:
            candidates = [{"text": rew_text, "risk": score_after}]

        # Vérification de monotonicité : réduction stricte si score_before > 0.15, ou maintien <= 0.15 si déjà bas
        monotonic_ok = (score_after < score_before) if score_before > 0.15 else (score_after <= 0.15)

        if candidates and monotonic_ok:
            for cand in candidates:
                cand_t = cand.get("text", "")
                cand_risk = cand.get("risk", score_after)
                if score_before > 0.15 and cand_risk >= score_before:
                    continue
                if score_before <= 0.15 and cand_risk > 0.15:
                    continue
                if check_style(cand_t, language=language, context_mode=context_mode, allowed_terms=allowed_terms).verdict != "FAIL":
                    chosen_text = cand_t
                    score_after = cand_risk
                    break
                style_rejects += 1
        elif rew_text and monotonic_ok:
            if check_style(rew_text, language=language, context_mode=context_mode, allowed_terms=allowed_terms).verdict != "FAIL":
                chosen_text = rew_text
            else:
                style_rejects += 1

        frag = modified_records[r_idx]["plan"][p_idx]
        is_validated = (chosen_text is not None and chosen_text != orig_text)
        frag["rewritten_text"] = chosen_text if is_validated else orig_text
        if is_validated:
            status = "VALIDÉ"
        elif stat.get("status") == "ALREADY_CLEAN":
            status = "ALREADY_CLEAN"
        elif not monotonic_ok:
            status = "REJET_MONOTONICITE"
        elif style_rejects > 0:
            status = "REJET_STYLE_GUARD"
        else:
            status = stat.get("status", "REJET_GATES")

        frag["status"] = status
        frag["risk_before"] = score_before
        frag["risk_after"] = score_after if is_validated else score_before

    # Réassemblage des segments et réinsertion dans les lignes du document
    lines = new_raw.split("\n")
    # Tri inverse par start line pour préserver les indices
    for rec in sorted(modified_records, key=lambda x: x["start"], reverse=True):
        reconstructed_fragments = []
        any_frag_rewritten = False
        sum_risk_before = 0.0
        sum_risk_after = 0.0
        frag_count = 0

        for frag in rec["plan"]:
            if frag["type"] == "unchanged":
                reconstructed_fragments.append(frag["text"])
            else:
                frag_count += 1
                sum_risk_before += frag.get("risk_before", 0.0)
                sum_risk_after += frag.get("risk_after", 0.0)
                if frag.get("status") == "VALIDÉ":
                    any_frag_rewritten = True
                    reconstructed_fragments.append(frag.get("rewritten_text", frag["text"]))
                else:
                    reconstructed_fragments.append(frag["text"])

        new_seg_text = " ".join(reconstructed_fragments)
        if rec["end"] - rec["start"] > 1:
            new_seg_text = one_sentence_per_line(new_seg_text)

        if any_frag_rewritten:
            lines[rec["start"]:rec["end"]] = new_seg_text.split("\n")

        avg_before = (sum_risk_before / max(frag_count, 1)) if frag_count else 0.0
        avg_after = (sum_risk_after / max(frag_count, 1)) if frag_count else 0.0

        report["segments"].append({
            "lines": f"L{rec['start'] + 1}-L{rec['end']}",
            "status": "VALIDÉ" if any_frag_rewritten else next((frag.get("status") for frag in rec["plan"] if frag["type"] == "modified"), "REJET_GATES"),
            "risk_before": round(avg_before, 4),
            "risk_after": round(avg_after, 4),
            "original": rec["original_seg"],
            "rewritten": new_seg_text if any_frag_rewritten else None
        })

    report["segments"].reverse()
    report["segments_rewritten"] = sum(1 for s in report["segments"] if s["status"] == "VALIDÉ")
    return "\n".join(lines), report

