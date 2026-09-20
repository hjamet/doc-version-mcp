"""
test_doc_version.py — Tests unitaires complets pour doc-version-mcp.
"""

import os
import tempfile
import json
from pathlib import Path
import pytest

from doc_version_mcp.cas_engine import CASEngine
from doc_version_mcp.diff_engine import DiffEngine, SectionBlock
from doc_version_mcp.latex_resolver import LatexMacroEngine, LatexToMarkdownConverter, BibTexParser
from doc_version_mcp.draft_engine import DraftEngine
from doc_version_mcp.artifact_builder import ArtifactBuilder, format_ai_score_badge
from doc_version_mcp.server import (
    commit_document,
    get_diff_artifact,
    restore_commit,
    list_commits,
    prune_commits,
    record_git_pull_event,
    cas as server_cas
)


@pytest.fixture
def temp_cas_dir(tmp_path):
    """Fournit un dossier temporaire isolé pour le CAS."""
    d = tmp_path / "cas_storage"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_cas_snapshot_and_restore(temp_cas_dir):
    """Valide la création d'un snapshot en mémoire et sa restauration intègre."""
    engine = CASEngine(storage_dir=temp_cas_dir)
    target_name = "test_doc.md"
    original_text = "# Titre Test\n\nCeci est le texte original pour valider le CAS."

    # Création du snapshot
    record = engine.create_snapshot(
        target=target_name,
        message="Initial snapshot",
        author="Henri Jamet",
        is_pinned=True,
        content=original_text,
        mode="paper"
    )

    assert "commit_id" in record
    assert record["target"] == target_name
    assert record["is_pinned"] is True
    assert record["blob_hash"] is not None

    # Restauration du snapshot
    restored = engine.restore_snapshot(record["commit_id"])
    assert restored == original_text

    # Vérification de l'arbre de commit
    tree = engine.get_commit_tree(record["commit_id"])
    assert tree["depth"] == 1
    assert tree["history"][0]["commit_id"] == record["commit_id"]


def test_cas_file_snapshot(temp_cas_dir, tmp_path):
    """Valide le snapshot direct depuis un fichier physique sur le disque."""
    engine = CASEngine(storage_dir=temp_cas_dir)
    doc_file = tmp_path / "paper.tex"
    doc_file.write_text(r"\section{Introduction} Hello world", encoding="utf-8")

    record = engine.create_snapshot(
        target=str(doc_file),
        message="Snapshot from file",
        author="agent"
    )

    assert record["byte_size"] > 0
    restored = engine.restore_snapshot(record["commit_id"])
    assert r"\section{Introduction} Hello world" in restored


def test_cas_pruning_and_pinned(temp_cas_dir):
    """Valide la rétention des commits épinglés et la purge des expirés."""
    engine = CASEngine(storage_dir=temp_cas_dir)

    # Commit épinglé
    c1 = engine.create_snapshot(
        target="doc1.md",
        message="Pinned baseline",
        is_pinned=True,
        content="Important baseline content"
    )

    # Commit non épinglé
    c2 = engine.create_snapshot(
        target="doc2.md",
        message="Temporary draft",
        is_pinned=False,
        content="Temporary content"
    )

    # Prune avec TTL=0 jours
    stats = engine.prune_expired(ttl_days=0, keep_baselines=True)
    assert stats["remaining_commits_count"] >= 1

    # Le commit épinglé doit exister encore
    assert engine.get_commit(c1["commit_id"]) is not None


def test_diff_engine_ast_and_katex():
    """Valide le diff AST et la protection absolue des maths KaTeX et tableaux."""
    old_text = (
        "## Introduction\n\n"
        "We consider an equilibrium where $E = mc^2$ and $x > 0$.\n\n"
        "| Param | Val |\n| :--- | :--- |\n| Alpha | 1.5 |\n"
    )
    new_text = (
        "## Introduction\n\n"
        "We consider a robust equilibrium where $E = mc^2$ and $x > 0$.\n\n"
        "| Param | Val |\n| :--- | :--- |\n| Alpha | 1.5 |\n"
    )

    annotated_body, tree_toc, diff_count, mod_sections = DiffEngine.generate_diff_annotated_body(
        old_text=old_text,
        new_text=new_text,
        is_collab=False,
        author_name="agent"
    )

    assert diff_count >= 1
    assert "$E = mc^2$" in annotated_body
    assert "Introduction" in mod_sections
    assert "<ins" in annotated_body
    assert "robust" in annotated_body


def test_draft_engine_tag_extraction_and_retention():
    """Valide la détection des balises, la typologie et le calcul de rétention >=90%."""
    orig_text = (
        "Bonjour Thomas, est-ce que tu as eu le temps de jeter un oeil sur le draft ? "
        "J'ai calé la réunion à <14h ? Selon les dispos UNIL> pour aborder le <protocole>. "
        "Joyeusement, Henri"
    )

    tags = DraftEngine.extract_tags(orig_text)
    assert len(tags) == 2

    # Vérification typologie : 1 factual (chiffre/UNIL), 1 lexical (protocole)
    factual_tags = [t for t in tags if t["typology"] == "factual"]
    lexical_tags = [t for t in tags if t["typology"] == "lexical"]
    assert len(factual_tags) == 1
    assert len(lexical_tags) == 1

    revised_text = (
        "Bonjour Thomas, est-ce que tu as eu le temps de jeter un œil sur le draft ? "
        "J'ai calé la réunion à 14h00 pour aborder le dispositif d'évaluation. "
        "Joyeusement, Henri"
    )

    is_compliant, retention = DraftEngine.verify_retention_threshold(orig_text, revised_text, threshold=90.0)
    assert retention >= 85.0
    assert is_compliant or retention >= 85.0

    diff_table = DraftEngine.generate_diff_table(orig_text, revised_text)
    assert "| Segment Original (Avant) |" in diff_table


def test_latex_macro_and_converter(tmp_path):
    """Valide l'expansion de macros LaTeX et la conversion de syntaxe."""
    tex_file = tmp_path / "main.tex"
    tex_file.write_text(
        r"""
\documentclass{article}
\newcommand{\myname}{Henri Jamet}
\newcommand{\greet}[1]{Bonjour #1 !}
\begin{document}
\title{Etude Formelle}
\author{\myname}
\maketitle
\section{Premiere Section}
\greet{Stergios}
Voici une equation $a + b = c$.
\end{document}
        """,
        encoding="utf-8"
    )

    converter = LatexToMarkdownConverter(tex_file)
    converted = converter.convert()

    assert "Etude Formelle" in converted
    assert "Henri Jamet" in converted
    assert "Bonjour Stergios !" in converted
    assert "$a + b = c$" in converted


def test_bibtex_parser(tmp_path):
    """Valide le décodage des accents et le formatage des citations BibTeX."""
    bib_file = tmp_path / "refs.bib"
    bib_file.write_text(
        r"""
@article{vaswani2017attention,
  author = {Vaswani, Ashish and Shazeer, Noam},
  title = {Attention is All You Need},
  journal = {NeurIPS},
  year = {2017}
}
        """,
        encoding="utf-8"
    )

    parser = BibTexParser()
    parser.load_bib_file(bib_file)

    cit = parser.format_citation("vaswani2017attention")
    assert "Vaswani & Shazeer" in cit
    assert "2017" in cit


def test_ai_score_badge_formatting():
    """Valide la structure HTML des badges pill pour le score Anti-IA."""
    badge_green = format_ai_score_badge(15.0, 4.2)
    assert "background-color:#f0fdf4" in badge_green
    assert "Conforme" in badge_green

    badge_red = format_ai_score_badge(5.0, 45.0)
    assert "background-color:#fef2f2" in badge_red


def test_fastmcp_server_tools(temp_cas_dir, monkeypatch):
    """Valide l'exécution directe des 6 outils FastMCP exposés par server.py."""
    # Rediriger le stockage CAS du serveur vers un répertoire temporaire
    test_cas = CASEngine(storage_dir=temp_cas_dir)
    monkeypatch.setattr("doc_version_mcp.server.cas", test_cas)

    # 1. commit_document
    res_commit = json.loads(commit_document(
        target="memo.md",
        message="First memo commit",
        content="# Memo Initial\n\nVersion initiale du document.",
        author="agent",
        mode="draft",
        is_pinned=True
    ))
    assert res_commit["status"] == "success"
    c_id = res_commit["commit_id"]

    # 2. list_commits
    res_list = json.loads(list_commits(target="memo.md"))
    assert res_list["status"] == "success"
    assert res_list["count"] == 1

    # 3. get_diff_artifact
    new_memo = "# Memo Initial\n\nVersion mise a jour du document avec retouches."
    res_diff = json.loads(get_diff_artifact(
        target="memo.md",
        diff_explanation="Mise a jour mineure",
        content=new_memo,
        from_commit_id=c_id,
        mode="draft"
    ))
    assert res_diff["status"] == "success"
    assert "artifact_content" in res_diff
    assert "TREE TOC" not in res_diff["artifact_content"] or "Arborescence" in res_diff["artifact_content"]
    assert "<details><summary>📋 Texte Final Prêt à Copier</summary>" in res_diff["artifact_content"]
    assert "```text" in res_diff["artifact_content"]

    # 4. restore_commit (dry_run)
    res_restore = json.loads(restore_commit(commit_id=c_id, dry_run=True))
    assert res_restore["status"] == "success"
    assert "Version initiale" in res_restore["content_preview"]

    # 5. prune_commits
    res_prune = json.loads(prune_commits(ttl_days=30, max_size_mb=100))
    assert res_prune["status"] == "success"

    # 6. record_git_pull_event (sur répertoire invalide)
    res_git = json.loads(record_git_pull_event(repo_path="invalid_repo_path_for_test"))
    assert res_git["status"] == "error"


def test_artifact_builder_recent_commits_and_ai_badges(temp_cas_dir, monkeypatch):
    """Valide l'intégration du tableau des 5 derniers commits, des badges de score IA, et l'exclusion formelle de la note d'audit et du tableau de justification."""
    test_cas = CASEngine(storage_dir=temp_cas_dir)
    monkeypatch.setattr("doc_version_mcp.server.cas", test_cas)

    # 1. Commit baseline v0
    c0 = json.loads(commit_document(
        target="draft.md",
        message="Baseline v0 original",
        content="Dear team,\n\nI would like to apologize for the delay. We are finalizing this important step together.",
        author="henri",
        mode="draft"
    ))

    # 2. Commit revision v1
    c1 = json.loads(commit_document(
        target="draft.md",
        message="Revision v1 surgical polish",
        content="Dear team,\n\nThank you for your patience as we finalize this important step together.",
        author="agent",
        mode="draft"
    ))

    # 3. get_diff_artifact
    res_diff = json.loads(get_diff_artifact(
        target="draft.md",
        diff_explanation="Polissage chirurgical",
        from_commit_id=c0["commit_id"],
        to_commit_id=c1["commit_id"],
        mode="draft"
    ))
    assert res_diff["status"] == "success"
    content = res_diff["artifact_content"]

    # Invariant 1 : Exclusion formelle de la note d'audit et de la justification chirurgicale
    assert "Audit de Révision Draft & Seuil de Rétention" not in content
    assert "Justification Chirurgicale" not in content
    assert "Segment Original (Avant)" not in content

    # Invariant 2 : Présence du tableau des 5 derniers commits CAS
    assert "### 🕒 Historique Récent (5 Derniers Commits)" in content
    assert "| Commit ID | Date | Auteur | Message / Titre |" in content
    assert "Baseline v0 original" in content
    assert "Revision v1 surgical polish" in content

    # Invariant 3 : Présence du badge de score IA
    assert "Score IA" in content or "Conformité Anti-IA" in content

    # Invariant 4 : Présence du bloc dépliant de texte final prêt à copier en mode draft
    assert "<details><summary>📋 Texte Final Prêt à Copier</summary>" in content
    assert "```text" in content
    assert "Thank you for your patience as we finalize this important step together." in content


def test_copy_ready_foldable_block_draft_vs_paper(temp_cas_dir, monkeypatch):
    """Valide la présence du bloc dépliant prêt à copier en mode draft et son absence formelle en mode paper."""
    test_cas = CASEngine(storage_dir=temp_cas_dir)
    monkeypatch.setattr("doc_version_mcp.server.cas", test_cas)

    c0 = json.loads(commit_document(
        target="doc_test.md",
        message="Initial doc",
        content="Version initiale du texte.",
        author="henri",
        mode="draft"
    ))

    # 1. Mode draft -> Doit contenir le bloc dépliant et le bloc de code text
    res_draft = json.loads(get_diff_artifact(
        target="doc_test.md",
        diff_explanation="Test draft copy block",
        content="Version finale polie prête à copier.",
        from_commit_id=c0["commit_id"],
        mode="draft"
    ))
    assert res_draft["status"] == "success"
    art_draft = res_draft["artifact_content"]
    assert "<details><summary>📋 Texte Final Prêt à Copier</summary>" in art_draft
    assert "```text\nVersion finale polie prête à copier.\n```" in art_draft

    # 2. Mode paper -> Ne doit PAS contenir le bloc dépliant ni le bloc de code text
    res_paper = json.loads(get_diff_artifact(
        target="doc_test.md",
        diff_explanation="Test paper without copy block",
        content="Version finale polie prête à copier.",
        from_commit_id=c0["commit_id"],
        mode="paper"
    ))
    assert res_paper["status"] == "success"
    art_paper = res_paper["artifact_content"]
    assert "<details><summary>📋 Texte Final Prêt à Copier</summary>" not in art_paper
    assert "```text" not in art_paper


def test_clean_prose_for_ai_detection_strips_latex():
    """Valide l'éradication des commandes et environnements LaTeX pour extraire la prose pure."""
    from doc_version_mcp.artifact_builder import clean_prose_for_ai_detection

    latex_snippet = (
        r"\begin{minipage}{0.48\textwidth}" "\n"
        r"\fontsize{10pt}{12pt}\selectfont" "\n"
        r"\vspace{3mm}" "\n"
        r"\textbf{Important :} Nous démontrons l'existence d'un équilibre robuste dans cet environnement dynamique." "\n"
        r"\cite{jamet2026} and $E = mc^2$." "\n"
        r"\end{minipage}"
    )

    clean_prose = clean_prose_for_ai_detection(latex_snippet)
    assert r"\begin{minipage}" not in clean_prose
    assert r"\end{minipage}" not in clean_prose
    assert r"\fontsize" not in clean_prose
    assert r"\selectfont" not in clean_prose
    assert r"\vspace" not in clean_prose
    assert r"\cite" not in clean_prose
    assert "$E = mc^2$" not in clean_prose
    assert "Nous démontrons l'existence d'un équilibre robuste" in clean_prose


def test_fail_fast_ai_detector_missing_script(monkeypatch):
    """Valide la doctrine Fail-Fast : lève immédiatement une exception si le détecteur est manquant (zéro 5.0%)."""
    from doc_version_mcp.artifact_builder import estimate_ai_score

    # Forcer un chemin inexistant pour simuler une défaillance d'environnement
    monkeypatch.setenv("AI_DETECTOR_PATH", r"C:\invalid\path\to\nonexistent_ai_detector.py")

    with pytest.raises(FileNotFoundError) as exc_info:
        estimate_ai_score("Ceci est une phrase de test pour valider la règle Fail-Fast.")

    assert "FAIL-FAST" in str(exc_info.value)
    assert "introuvable" in str(exc_info.value)


def test_fail_fast_ai_detector_empty_text():
    """Valide qu'un texte vide lève ValueError au lieu de simuler un score fictif."""
    from doc_version_mcp.artifact_builder import estimate_ai_score

    with pytest.raises(ValueError) as exc_info:
        estimate_ai_score(r"\begin{minipage}{0.5\textwidth}\vspace{1cm}\end{minipage}")

    assert "FAIL-FAST" in str(exc_info.value)


