"""
test_stealth_bridge.py — Tests unitaires pour le bridge StealthRL, son cache, son découpage chirurgical et son client démon.
"""

import os
import json
import time
import socket
import threading
import http.server
from pathlib import Path
import pytest

from doc_version_mcp.stealth_bridge import (
    resolve_stealth_runtime,
    _clear_runtime_cache,
    _CACHE_FILE,
    split_sentences,
    group_sentences_into_windows,
    plan_paragraph_sentence_rewrites,
    check_daemon_health,
    call_stealth_daemon,
    format_stealth_callout,
    apply_stealth_to_modified_prose,
    execute_stealth_batch
)
from doc_version_mcp.server import get_diff_artifact, cas


def test_runtime_resolution_and_cache(monkeypatch):
    """Valide la résolution du runtime CUDA et la mise en cache mémoire/disque (< 1 ms au 2e appel)."""
    _clear_runtime_cache()

    exe, script = resolve_stealth_runtime()
    assert Path(exe).is_file(), f"Interpréteur introuvable : {exe}"
    assert Path(script).is_file(), f"Script introuvable : {script}"
    assert _CACHE_FILE.exists(), "Le fichier cache disque doit avoir été créé."

    # Deuxième appel immédiat : doit prendre moins de 5 ms grâce au cache mémoire (< 0.1 ms mesuré hors surcharge)
    t0 = time.perf_counter()
    exe2, script2 = resolve_stealth_runtime()
    elapsed_ms = (time.perf_counter() - t0) * 1000.0

    assert exe2 == exe
    assert script2 == script
    assert elapsed_ms < 5.0, f"Le cache mémoire doit répondre en < 5 ms (obtenu {elapsed_ms:.3f} ms)"

    # Test lecture directe depuis le cache disque après invalidation du cache mémoire seul
    import doc_version_mcp.stealth_bridge as sb
    sb._RUNTIME_CACHE = None
    t1 = time.perf_counter()
    exe3, script3 = resolve_stealth_runtime()
    elapsed_disk_ms = (time.perf_counter() - t1) * 1000.0

    assert exe3 == exe
    assert script3 == script
    assert elapsed_disk_ms < 50.0, f"Le cache disque doit répondre en < 50 ms (obtenu {elapsed_disk_ms:.3f} ms)"


def test_sentence_splitting_academic_abbreviations():
    """Valide la préservation des abréviations académiques sans découpe erronée de phrases."""
    text = (
        "We follow the protocol established by Smith et al. in their recent study. "
        "For e.g., consider Eq. (1) and Fig. 2 as illustrative examples. "
        "Sec. 3 presents our empirical results vs. the baseline (cf. p. 42). "
        "Furthermore, Dr. Watson and Prof. Moriarty verified the convergence."
    )
    sents = split_sentences(text)
    assert len(sents) == 4
    assert "Smith et al." in sents[0]
    assert "For e.g." in sents[1] and "Eq. (1)" in sents[1] and "Fig. 2" in sents[1]
    assert "Sec. 3" in sents[2] and "vs. the baseline" in sents[2] and "p. 42" in sents[2]
    assert "Prof. Moriarty" in sents[3]


def test_surgical_sentence_windowing_preserves_unchanged():
    """Valide le découpage chirurgical préservant intactes les phrases inchangées d'un long paragraphe."""
    old_para = (
        "Modern deep learning architectures rely heavily on large-scale distributed training across heterogeneous clusters. "
        "Traditional approaches often fail to account for communication overhead in decentralized environments. "
        "In this work, we propose an adaptive communication schedule that minimizes idle worker periods. "
        "Extensive empirical evaluations confirm significant throughput gains over competitive state-of-the-art baselines."
    )

    # new_para modifie uniquement la 2e phrase (introduction d'un style IA) et conserve les phrases 1, 3 et 4 intactes
    new_para = (
        "Modern deep learning architectures rely heavily on large-scale distributed training across heterogeneous clusters. "
        "Moreover, it is worth noting that traditional methods exhibit a multifaceted tapestry of bottlenecks. "
        "In this work, we propose an adaptive communication schedule that minimizes idle worker periods. "
        "Extensive empirical evaluations confirm significant throughput gains over competitive state-of-the-art baselines."
    )

    plan = plan_paragraph_sentence_rewrites(old_para, new_para, max_words=85)

    # Le plan doit comporter :
    # 1. unchanged (phrase 1)
    # 2. modified (phrase 2 altérée)
    # 3. unchanged (phrases 3 et 4)
    assert len(plan) == 3
    assert plan[0]["type"] == "unchanged"
    assert "Modern deep learning architectures" in plan[0]["text"]

    assert plan[1]["type"] == "modified"
    assert "multifaceted tapestry" in plan[1]["text"]

    assert plan[2]["type"] == "unchanged"
    assert "In this work, we propose" in plan[2]["text"]
    assert "Extensive empirical evaluations" in plan[2]["text"]


def test_sentence_grouping_max_words():
    """Valide que les sous-fenêtres ne dépassent pas max_words (85 mots)."""
    sentences = [
        "This is a short sentence one.",
        "Here is another sentence that contains a few more words to test the windowing accumulation logic properly.",
        "A third sentence adds further context to the paragraph.",
        "Finally, the fourth sentence concludes this sequence of statements."
    ]
    windows = group_sentences_into_windows(sentences, max_words=20, max_sentences=2)
    assert len(windows) >= 2
    for w in windows:
        total_w = sum(len(s.split()) for s in w)
        assert len(w) <= 2


class _MockDaemonHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Silence stdout/stderr logging during tests

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "ok",
                "device": "cuda",
                "models_loaded": True,
                "idle_seconds": 1.5,
                "pid": 99999
            }).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/rewrite":
            content_length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(content_length).decode("utf-8")
            data = json.loads(raw_body)
            paras = data.get("paragraphs", [])

            rewritten = [f"Humanized: {p}" for p in paras]
            stats = [{
                "changed": True,
                "score_before": 0.88,
                "score_after": 0.15,
                "candidates_ranked": [{"text": r, "risk": 0.15}],
                "status": "VALIDÉ",
                "gate_rejections": [],
                "rounds": 1,
                "elapsed_ms": 45.0
            } for r in rewritten]

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({
                "rewritten": rewritten,
                "stats": stats,
                "total_elapsed_ms": 45.0 * len(paras),
                "engine_mode": "daemon"
            }).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def test_daemon_client_http_and_mock():
    """Valide les requêtes GET /health et POST /rewrite vers un démon HTTP local persistant."""
    port = _get_free_port()
    server = http.server.HTTPServer(("127.0.0.1", port), _MockDaemonHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        # 1. Vérification santé
        assert check_daemon_health(host="127.0.0.1", port=port) is True

        # 2. Appel POST /rewrite
        res = call_stealth_daemon(
            paragraphs=["Moreover, we delve into the dataset."],
            host="127.0.0.1",
            port=port
        )
        assert res is not None
        assert res["engine_mode"] == "daemon"
        assert len(res["rewritten"]) == 1
        assert res["rewritten"][0] == "Humanized: Moreover, we delve into the dataset."
        assert res["stats"][0]["score_after"] == 0.15

        # 3. Port fermé -> repli propre (renvoie None sans crasher)
        closed_port = _get_free_port()
        assert check_daemon_health(host="127.0.0.1", port=closed_port) is False
        assert call_stealth_daemon(["Test"], host="127.0.0.1", port=closed_port) is None

    finally:
        server.shutdown()
        server.server_close()


def test_format_stealth_callout():
    """Valide le formatage du bloc d'en-tête Markdown Obsidian/Antigravity."""
    report = {
        "engine_mode": "daemon",
        "total_elapsed_ms": 142.5,
        "segments_rewritten": 1,
        "segments_modified": 1,
        "segments": [{
            "lines": "L15-L22",
            "risk_before": 0.854,
            "risk_after": 0.142,
            "status": "VALIDÉ"
        }]
    }
    callout = format_stealth_callout(report)
    assert "> [!NOTE]" in callout
    assert "🛡️ Obfuscation Automatique StealthRL" in callout
    assert "`daemon`" in callout
    assert "142.5 ms" in callout
    assert "1/1" in callout
    assert "85.4%" in callout
    assert "14.2%" in callout
    assert "-71.2%" in callout
    assert "🟢 Validé" in callout


def test_get_diff_artifact_stealth_integration(monkeypatch, tmp_path):
    """Valide l'intégration de bout en bout dans get_diff_artifact avec double snapshot CAS et callout."""
    # Mock de apply_stealth_to_modified_prose pour un test unitaire rapide et déterministe
    def mock_apply_stealth(old_raw, new_raw, target_path, language, context_mode, allowed_terms, **kwargs):
        rewritten = new_raw.replace("delve into the multifaceted challenges", "examine the diverse challenges")
        report = {
            "segments_modified": 1,
            "segments_rewritten": 1,
            "segments": [{
                "lines": "L1-L3",
                "risk_before": 0.84,
                "risk_after": 0.18,
                "status": "VALIDÉ"
            }],
            "engine_mode": "daemon",
            "total_elapsed_ms": 85.0
        }
        return rewritten, report

    monkeypatch.setattr("doc_version_mcp.server.apply_stealth_to_modified_prose", mock_apply_stealth)

    test_file = tmp_path / "paper.tex"
    test_file.write_text(
        "\\begin{document}\nWe present a standard approach.\n\\end{document}",
        encoding="utf-8"
    )

    new_content = "\\begin{document}\nWe delve into the multifaceted challenges in distributed optimization.\n\\end{document}"

    res_json_str = get_diff_artifact(
        target=str(test_file),
        diff_explanation="Mise à jour méthodologique",
        content=new_content,
        mode="paper",
        run_stealth=True,
        return_content=True
    )
    res = json.loads(res_json_str)

    assert res["status"] == "success"
    stealth = res.get("stealth_rewrite", {})
    assert stealth.get("applied") is True
    assert stealth.get("segments_rewritten") == 1
    assert "pre_commit_id" in stealth, "Le pré-snapshot CAS doit être scellé"
    assert "post_commit_id" in stealth, "Le post-snapshot CAS doit être scellé"

    # Vérification de l'injection du callout dans l'artéfact Markdown
    art_content = res.get("artifact_content", "")
    assert "> [!NOTE]" in art_content
    assert "🛡️ Obfuscation Automatique StealthRL" in art_content
    assert "`daemon`" in art_content


class _ForeignServiceHandler(http.server.BaseHTTPRequestHandler):
    response_payload = {"status": "ok", "service": "aivc_daemon"}

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(self.response_payload).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def test_check_daemon_health_rejects_foreign_service():
    """Valide que check_daemon_health rejette un service étranger (ex: aivc.daemon sur 18765) sans service:stealth_rewriter."""
    port = _get_free_port()
    server = http.server.HTTPServer(("127.0.0.1", port), _ForeignServiceHandler)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    try:
        # 1. Réponse avec un service étranger -> False
        _ForeignServiceHandler.response_payload = {"status": "ok", "service": "aivc_daemon"}
        assert check_daemon_health(host="127.0.0.1", port=port) is False

        # 2. Réponse générique status: ok sans tag de service ni models_loaded -> False
        _ForeignServiceHandler.response_payload = {"status": "ok"}
        assert check_daemon_health(host="127.0.0.1", port=port) is False

        # 3. Réponse avec service: stealth_rewriter -> True
        _ForeignServiceHandler.response_payload = {"status": "ok", "service": "stealth_rewriter"}
        assert check_daemon_health(host="127.0.0.1", port=port) is True

        # 4. Réponse avec models_loaded: True -> True
        _ForeignServiceHandler.response_payload = {"status": "ok", "models_loaded": True}
        assert check_daemon_health(host="127.0.0.1", port=port) is True
    finally:
        server.shutdown()
        server.server_close()


def test_apply_stealth_fallback_candidates_ranked_and_monotonicity(monkeypatch):
    """Valide le fallback gracieux si candidates_ranked est absent et la stricte monotonicité."""
    old_raw = (
        "\\begin{document}\n"
        "We consider decentralized gradient optimization across workers.\n"
        "\\end{document}"
    )
    new_raw = (
        "\\begin{document}\n"
        "Moreover, we delve into a multifaceted tapestry of deep neural network architectures.\n"
        "\\end{document}"
    )

    # 1. Test du fallback : changed=True, candidates_ranked absent mais rewritten fourni
    def mock_batch_fallback(*args, **kwargs):
        return {
            "rewritten": ["We examine diverse neural network architectures across multiple distributed tasks."],
            "stats": [{
                "changed": True,
                "score_before": 0.88,
                "score_after": 0.12,
                "status": "VALIDÉ"
                # candidates_ranked intentionnellement absent
            }],
            "engine_mode": "daemon",
            "total_elapsed_ms": 32.0
        }

    monkeypatch.setattr("doc_version_mcp.stealth_bridge.execute_stealth_batch", mock_batch_fallback)
    monkeypatch.setattr("doc_version_mcp.stealth_bridge.resolve_stealth_runtime", lambda: ("python.exe", Path("stealth_rewriter.py")))

    rewritten, report = apply_stealth_to_modified_prose(
        old_raw=old_raw,
        new_raw=new_raw,
        target_path=Path("paper.tex"),
        language="en",
        context_mode="technical",
        allowed_terms=None,
        use_daemon=True
    )
    assert report["segments_rewritten"] == 1
    assert report["segments"][0]["status"] == "VALIDÉ"
    assert report["segments"][0]["risk_after"] == 0.12
    assert "We examine diverse neural network architectures" in rewritten

    # 2. Test de monotonicité : score_after >= score_before -> REJET_MONOTONICITE
    def mock_batch_non_monotonic(*args, **kwargs):
        return {
            "rewritten": ["A worse sentence that increases AI risk further."],
            "stats": [{
                "changed": True,
                "score_before": 0.50,
                "score_after": 0.82,  # Régression de score -> doit être rejeté
                "status": "VALIDÉ"
            }],
            "engine_mode": "daemon",
            "total_elapsed_ms": 25.0
        }

    monkeypatch.setattr("doc_version_mcp.stealth_bridge.execute_stealth_batch", mock_batch_non_monotonic)

    rewritten_mono, report_mono = apply_stealth_to_modified_prose(
        old_raw=old_raw,
        new_raw=new_raw,
        target_path=Path("paper.tex"),
        language="en",
        context_mode="technical",
        allowed_terms=None,
        use_daemon=True
    )
    assert report_mono["segments_rewritten"] == 0
    assert report_mono["segments"][0]["status"] == "REJET_MONOTONICITE"
    # Le texte doit être resté intact (non modifié par un candidat régressif)
    assert rewritten_mono == new_raw


def test_get_diff_artifact_stealth_default_in_draft_and_paper(monkeypatch, tmp_path):
    """Valide que StealthRL est activé par défaut en mode draft et paper hors environnement pytest."""
    call_count = {"count": 0}

    def mock_apply_stealth(old_raw, new_raw, target_path, language, context_mode, allowed_terms, **kwargs):
        call_count["count"] += 1
        rewritten = new_raw.replace("delve into", "explore")
        report = {
            "segments_modified": 1,
            "segments_rewritten": 1,
            "segments": [{"lines": "L1", "risk_before": 0.8, "risk_after": 0.2, "status": "VALIDÉ"}],
            "engine_mode": "daemon",
            "total_elapsed_ms": 40.0
        }
        return rewritten, report

    monkeypatch.setattr("doc_version_mcp.server.apply_stealth_to_modified_prose", mock_apply_stealth)

    # 1. Simuler l'environnement hors pytest : PYTEST_CURRENT_TEST non défini
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    test_file = tmp_path / "draft.md"
    test_file.write_text("Introduction to our methodology.\n", encoding="utf-8")
    new_draft = "Introduction to our methodology.\nWe delve into this problem.\n"

    # Appel en mode draft sans spécifier run_stealth -> doit s'exécuter par défaut
    res_draft = json.loads(get_diff_artifact(
        target=str(test_file),
        diff_explanation="Update draft",
        content=new_draft,
        mode="draft",
        return_content=True
    ))
    assert res_draft["status"] == "success"
    assert res_draft.get("stealth_rewrite", {}).get("applied") is True
    assert call_count["count"] == 1

    # 2. Appel avec run_stealth=False explicite -> doit être désactivé
    clean_draft = "Introduction to our methodology.\nWe investigate this problem in depth.\n"
    res_disabled = json.loads(get_diff_artifact(
        target=str(test_file),
        diff_explanation="Update draft without stealth",
        content=clean_draft,
        mode="draft",
        run_stealth=False,
        return_content=True
    ))
    assert res_disabled["status"] == "success"
    assert res_disabled.get("stealth_rewrite", {}).get("applied") is False
    assert call_count["count"] == 1  # Pas d'incrément


