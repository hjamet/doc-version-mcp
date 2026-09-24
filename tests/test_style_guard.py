"""
test_style_guard.py — Tests unitaires pour la boucle bloquante avoid-ai-writing et le Style Guard.
"""

import json
import pytest
from pathlib import Path

from doc_version_mcp.style_guard import check_style, detect_language
from doc_version_mcp.server import get_diff_artifact, commit_document, cas as server_cas
from doc_version_mcp.cas_engine import CASEngine


def test_detect_language():
    """Valide la détection de langue français vs anglais par stop-words."""
    fr_text = "Ceci est un document en français qui présente les résultats de notre recherche académique."
    en_text = "This is a document in English presenting the results of our academic research."
    assert detect_language(fr_text) == "fr"
    assert detect_language(en_text) == "en"


def test_hard_blocker_tier1a():
    """Valide que les termes Tier 1A (delve, robust, tapestry...) entraînent un FAIL immédiat."""
    bad_text = "We delve into the dataset to establish a robust baseline for evaluation."
    res = check_style(bad_text)

    assert res.verdict == "FAIL"
    assert len(res.hard_blockers) >= 2
    terms = [h["term"].lower() for h in res.hard_blockers]
    assert "delve" in terms
    assert "robust" in terms
    assert "FAIL" in res.error_report
    assert "delve" in res.error_report
    assert "robust" in res.error_report


def test_hard_blocker_em_dash():
    """Valide que les em-dashes ('—' et '--') sont bloqués sans tolérance."""
    # Test em-dash Unicode
    text_dash1 = "The model achieves high accuracy — especially on out-of-distribution samples."
    res1 = check_style(text_dash1)
    assert res1.verdict == "FAIL"
    assert any("em-dash" in h["type"] for h in res1.hard_blockers)

    # Test double tiret d'incise
    text_dash2 = "The model achieves high accuracy -- especially on out-of-distribution samples."
    res2 = check_style(text_dash2)
    assert res2.verdict == "FAIL"
    assert any("em-dash" in h["type"] for h in res2.hard_blockers)


def test_hard_blocker_mechanical_transitions():
    """Valide que les transitions mécaniques artificielles sont bloquées."""
    # Anglais
    en_text = "Moreover, we must observe that the experiment succeeded. Furthermore, the loss decreased."
    res_en = check_style(en_text, language="en")
    assert res_en.verdict == "FAIL"
    terms_en = [h["term"].lower() for h in res_en.hard_blockers]
    assert any("moreover" in t for t in terms_en)
    assert any("furthermore" in t for t in terms_en)

    # Français
    fr_text = "En conclusion, nous observons que le dispositif fonctionne. De surcroît, le temps de calcul est réduit."
    res_fr = check_style(fr_text, language="fr")
    assert res_fr.verdict == "FAIL"
    terms_fr = [h["term"].lower() for h in res_fr.hard_blockers]
    assert any("en conclusion" in t for t in terms_fr)
    assert any("de surcroît" in t for t in terms_fr)


def test_hard_blocker_normalization():
    """Valide que les attaques par contournement (ZWSP, homoglyphes) sont interceptées."""
    # Zero-Width Space U+200B
    zwsp_text = "This is a clean\u200B text with an invisible zero width space."
    res_zwsp = check_style(zwsp_text)
    assert res_zwsp.verdict == "FAIL"
    assert any("ZWSP" in h["type"] or "Normalization" in h["type"] for h in res_zwsp.hard_blockers)

    # Homoglyphe cyrillique 'а' (U+0430) au lieu du 'a' latin
    homoglyph_text = "This is а text with cyrillic homoglyph."
    res_homo = check_style(homoglyph_text)
    assert res_homo.verdict == "FAIL"
    assert any("Homoglyphe" in h["type"] or "Normalization" in h["type"] for h in res_homo.hard_blockers)


def test_budget_severe():
    """Valide la politique graduée mais sévère sur les soft warnings."""
    # 1. < 500 mots : budget = 0 (100% strict)
    # 1 soft warning ("utilize") -> doit FAIL
    short_text = "We utilize this algorithm for rapid processing of textual queries."
    res_short = check_style(short_text)
    assert res_short.word_count < 500
    assert res_short.budget_max == 0
    assert len(res_short.soft_warnings) >= 1
    assert res_short.verdict == "FAIL"

    # 2. 500 à 1500 mots : budget = 1 soft warning
    base_paragraph = (
        "The distributed ledger system implements an atomic consensus protocol across heterogeneous nodes. "
        "Each transaction undergoes cryptographic validation before appending to the local storage engine. "
        "Communication latencies remain bounded through pipelined network serialization and non-blocking IO. "
        "Evaluation benchmarks confirm stable throughput under high concurrency conditions without saturation. "
    )
    # Répéter pour créer un texte de ~600 mots
    words_base = base_paragraph.split()
    long_600 = " ".join((words_base * 15)[:600])

    # 2a. 600 mots avec 1 soft warning -> WARN (dans le budget)
    text_warn_1 = "We utilize this algorithm. " + long_600
    res_warn_1 = check_style(text_warn_1)
    assert 500 <= res_warn_1.word_count <= 1500
    assert res_warn_1.budget_max == 1
    assert len(res_warn_1.soft_warnings) == 1
    assert res_warn_1.verdict == "WARN"

    # 2b. 600 mots avec 2 soft warnings -> FAIL (budget dépassé)
    text_fail_2 = "We utilize this algorithm in order to accelerate processing. " + long_600
    res_fail_2 = check_style(text_fail_2)
    assert 500 <= res_fail_2.word_count <= 1500
    assert res_fail_2.budget_max == 1
    assert len(res_fail_2.soft_warnings) >= 2
    assert res_fail_2.verdict == "FAIL"

    # 3. > 1500 mots : budget = 2 soft warnings
    long_1600 = " ".join((words_base * 40)[:1600])

    # 3a. 1600 mots avec 2 soft warnings -> WARN (dans le budget)
    text_warn_2 = "We utilize this algorithm in order to accelerate processing. " + long_1600
    res_warn_2 = check_style(text_warn_2)
    assert res_warn_2.word_count > 1500
    assert res_warn_2.budget_max == 2
    assert len(res_warn_2.soft_warnings) == 2
    assert res_warn_2.verdict == "WARN"

    # 3b. 1600 mots avec 3 soft warnings -> FAIL (budget dépassé)
    text_fail_3 = "We utilize this algorithm in order to accelerate processing due to the fact that speed matters. " + long_1600
    res_fail_3 = check_style(text_fail_3)
    assert res_fail_3.word_count > 1500
    assert res_fail_3.budget_max == 2
    assert len(res_fail_3.soft_warnings) >= 3
    assert res_fail_3.verdict == "FAIL"


def test_clean_document():
    """Valide qu'un document propre produit un verdict PASS, 0 warning et zéro pollution."""
    clean_text = (
        "# Rapport Technique\n\n"
        "Nous présentons ici une analyse comparative des performances réseau.\n"
        "Les mesures indiquent un débit moyen de 120 mégaoctets par seconde.\n"
        "Aucune anomalie de transmission n'a été constatée lors de la campagne d'essais."
    )
    res = check_style(clean_text, language="fr")
    assert res.verdict == "PASS"
    assert len(res.hard_blockers) == 0
    assert len(res.soft_warnings) == 0


def test_get_diff_artifact_blocking_fail_and_warn_integration(tmp_path, monkeypatch):
    """
    Valide l'intégration de la boucle bloquante dans get_diff_artifact :
    - Échec bloquant (ValueError / status error) en cas de hard blocker
    - Insertion du tableau dépliant sans badge en cas de WARN
    - Zéro badge en cas de PASS
    """
    test_cas = CASEngine(storage_dir=tmp_path / "cas_storage")
    monkeypatch.setattr("doc_version_mcp.server.cas", test_cas)

    # 1. Baseline propre
    c0 = json.loads(commit_document(
        target="manuscript.md",
        message="Version initiale propre",
        content="# Manuscrit\n\nVersion initiale de test.",
        author="henri",
        mode="draft"
    ))

    # Cas A : Contenu avec Hard Blocker ("robust") -> Doit renvoyer une erreur bloquante
    res_bad = json.loads(get_diff_artifact(
        target="manuscript.md",
        diff_explanation="Tentative avec terme IA",
        content="# Manuscrit\n\nVersion avec une architecture robust.",
        from_commit_id=c0["commit_id"],
        mode="draft"
    ))
    assert res_bad["status"] == "error"
    assert "Style Guard Bloquant (Verdict: FAIL)" in res_bad["error"]
    assert "robust" in res_bad["error"]

    # Cas B : Contenu avec Soft Warning respectant le budget (>500 mots, 1 warning) -> Doit générer l'artéfact avec tableau dépliant
    sample_words = (
        "The distributed ledger system implements an atomic consensus protocol across heterogeneous nodes. "
        "Each transaction undergoes cryptographic validation before appending to the local storage engine. "
        "Communication latencies remain bounded through pipelined network serialization and non-blocking IO. "
        "Evaluation benchmarks confirm stable throughput under high concurrency conditions without saturation. "
    ).split() * 15
    base_text = " ".join(sample_words[:600])

    warn_content = f"# Manuscrit\n\nWe utilize this algorithm.\n\n{base_text}"
    res_warn = json.loads(get_diff_artifact(
        target="manuscript.md",
        diff_explanation="Révision avec soft warning dans le budget",
        content=warn_content,
        from_commit_id=c0["commit_id"],
        mode="draft",
        language="en"
    ))
    assert res_warn["status"] == "success"
    assert res_warn["style_verdict"] == "WARN"
    assert res_warn["soft_warnings_count"] == 1
    assert "artifact_content" not in res_warn
    assert res_warn["saved_artifact_path"] is not None
    assert Path(res_warn["saved_artifact_path"]).exists()
    art_warn = Path(res_warn["saved_artifact_path"]).read_text(encoding="utf-8")

    # Vérification présence du tableau dépliant
    assert "<details><summary>💡 Recommandations Stylistiques Non-Bloquantes (1 alertes)</summary>" in art_warn
    assert "`utilize`" in art_warn

    # Invariant absolu : Zéro badge de pollution
    assert "Score IA" not in art_warn
    assert "Conformité Anti-IA" not in art_warn
    assert "badge" not in art_warn.lower()

    # Cas C : Contenu 100% propre -> Pas de tableau dépliant, zéro badge
    clean_content = f"# Manuscrit\n\nWe use this algorithm.\n\n{base_text}"
    res_clean = json.loads(get_diff_artifact(
        target="manuscript.md",
        diff_explanation="Révision propre",
        content=clean_content,
        from_commit_id=c0["commit_id"],
        mode="draft",
        language="en"
    ))
    assert res_clean["status"] == "success"
    assert res_clean["style_verdict"] == "PASS"
    assert res_clean["soft_warnings_count"] == 0
    assert "artifact_content" not in res_clean
    assert res_clean["saved_artifact_path"] is not None
    assert Path(res_clean["saved_artifact_path"]).exists()
    art_clean = Path(res_clean["saved_artifact_path"]).read_text(encoding="utf-8")


    # Ni badge, ni tableau dépliant
    assert "Recommandations Stylistiques Non-Bloquantes" not in art_clean
    assert "Score IA" not in art_clean
    assert "Conformité Anti-IA" not in art_clean


def test_iteration_tracking_and_summary_formatting():
    """Valide le formatage synthétique des itérations anti-IA et la conversion to_iteration_dict."""
    from doc_version_mcp.style_guard import format_style_audit_summary, StyleCheckResult

    # 1. Test 1 tour propre (0 pb)
    audit_1 = {
        "iterations": [
            {"iteration": 1, "verdict": "PASS", "total_issues": 0, "hard_blockers": 0, "soft_warnings": 0}
        ]
    }
    assert format_style_audit_summary(audit_1) == "1 tour (0 pb - Conforme)"

    # 2. Test 2 itérations avec résolution
    audit_2 = {
        "iterations": [
            {
                "iteration": 1,
                "verdict": "FAIL",
                "total_issues": 3,
                "hard_blockers": 1,
                "soft_warnings": 2,
                "tier_breakdown": {"Tier 1": 1, "Tier 2": 2}
            },
            {
                "iteration": 2,
                "verdict": "PASS",
                "total_issues": 0,
                "hard_blockers": 0,
                "soft_warnings": 0,
                "tier_breakdown": {}
            }
        ]
    }
    summary_2 = format_style_audit_summary(audit_2)
    assert "2 itérations" in summary_2
    assert "T1: 3 pb" in summary_2
    assert "T2: 0 pb - PASS" in summary_2

    # 3. Test commit Overleaf
    audit_overleaf = {"is_overleaf": True}
    assert format_style_audit_summary(audit_overleaf) == "N/A (commit Overleaf)"

    # 4. Test to_iteration_dict depuis un StyleCheckResult
    scr = StyleCheckResult(
        verdict="FAIL",
        word_count=100,
        budget_max=0,
        hard_blockers=[{"type": "Hard Blocker: em-dash", "line": 5, "term": "—", "suggestion": "Virgule"}],
        soft_warnings=[{"type": "Soft Warning: tier2", "line": 8, "term": "utilize", "suggestion": "use"}]
    )
    it_dict = scr.to_iteration_dict(iteration=1)
    assert it_dict["iteration"] == 1
    assert it_dict["verdict"] == "FAIL"
    assert it_dict["total_issues"] == 2
    assert it_dict["hard_blockers"] == 1
    assert it_dict["soft_warnings"] == 1
    assert "em-dash" in it_dict["tier_breakdown"]
    assert "Tier 2" in it_dict["tier_breakdown"]


def test_save_and_load_style_audit_persistence(tmp_path):
    """Valide la sauvegarde atomique et le rechargement de style_audit.json."""
    from doc_version_mcp.style_guard import save_style_audit, load_style_audit

    cas_dir = tmp_path / "cas_test"
    cas_dir.mkdir()

    test_audit = {
        "commit_id": "abcdef12",
        "iterations_count": 2,
        "summary": "2 itérations (T1: 1 pb ➔ T2: 0 pb - PASS)"
    }

    save_style_audit("abcdef12", test_audit, storage_dir=cas_dir)

    loaded = load_style_audit("abcdef12", storage_dir=cas_dir)
    assert loaded is not None
    assert loaded["commit_id"] == "abcdef12"
    assert loaded["summary"] == "2 itérations (T1: 1 pb ➔ T2: 0 pb - PASS)"

    # Match par préfixe court
    loaded_prefix = load_style_audit("abcdef", storage_dir=cas_dir)
    assert loaded_prefix is not None
    assert loaded_prefix["commit_id"] == "abcdef12"


def test_allowed_terms_bypass():
    """Valide que les termes whitelistés (ex: robust, comprehensive, leverage) ne bloquent pas le Style Guard."""
    text_with_allowed = "We present a comprehensive evaluation to demonstrate that our model is more robust when we leverage prior knowledge."
    # Sans allowed_terms -> FAIL
    res_fail = check_style(text_with_allowed)
    assert res_fail.verdict == "FAIL"

    # Avec allowed_terms -> PASS
    res_pass = check_style(text_with_allowed, allowed_terms=["comprehensive", "robust", "leverage"])
    assert res_pass.verdict == "PASS"
    assert len(res_pass.hard_blockers) == 0


