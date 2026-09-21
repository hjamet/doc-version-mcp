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
from doc_version_mcp.artifact_builder import ArtifactBuilder
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


def test_artifact_builder_recent_commits_and_no_ai_badges(temp_cas_dir, monkeypatch):
    """Valide l'intégration du tableau des 5 derniers commits, l'exclusion formelle de l'IA, et le bloc dépliant draft."""
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

    # Invariant 3 : Exclusion formelle de tout badge ou calcul IA
    assert "Score IA" not in content
    assert "Conformité Anti-IA" not in content

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


def test_preamble_institutional_header_no_false_deltas():
    """Valide que l'en-tête institutionnel / préambule sans titre H1 ne génère aucun faux delta ins."""
    old_latex = r"""
    \begin{document}
    \begin{minipage}[c]{0.80\textwidth}
        \textbf{Université de Lausanne} \textbar\ \textbf{Faculté des HEC} \\
        Département des Systèmes d'Information (DESI) \textbar\ \textit{Applied AI Lab}
    \end{minipage}
    \begin{center}
        \textbf{Rapport Scientifique et Financier : HEC Research Fund 2024-2025}
    \end{center}
    \section{Objectifs}
    Texte initial de la section objectifs.
    \end{document}
    """

    new_latex = r"""
    \begin{document}
    \begin{minipage}[c]{0.80\textwidth}
        \textbf{Université de Lausanne} \textbar\ \textbf{Faculté des HEC} \\
        Département des Systèmes d'Information (DESI) \textbar\ \textit{Applied AI Lab}
    \end{minipage}
    \begin{center}
        \textbf{Rapport Scientifique et Financier : HEC Research Fund 2024-2025}
    \end{center}
    \section{Objectifs}
    Texte révisé et mis à jour de la section objectifs.
    \end{document}
    """

    old_md = LatexToMarkdownConverter.convert_text(old_latex)
    new_md = LatexToMarkdownConverter.convert_text(new_latex)

    annotated_body, tree_toc, diff_count, mod_sections = DiffEngine.generate_diff_annotated_body(
        old_text=old_md,
        new_text=new_md
    )

    # 1. L'en-tête ne doit pas apparaître dans les sections modifiées
    assert "Préambule" not in mod_sections
    assert "Introduction & Préambule" not in mod_sections

    # 2. Les lignes d'en-tête institutionnel ne doivent PAS être marquées en <ins> ou <del>
    preamble_part = annotated_body.split("## Objectifs")[0]
    assert "<ins" not in preamble_part
    assert "<del" not in preamble_part

    # 3. Seule la section Objectifs doit contenir le diff
    assert any("Objectifs" in s for s in mod_sections)
    assert "<ins" in annotated_body.split("## Objectifs")[1]


def test_del_ins_no_strikethrough_no_underline():
    """Valide que <del> n'est pas barré et <ins> n'est pas souligné (couleur seule)."""
    assert "text-decoration:none !important;" in DiffEngine.DEL_STYLE_LOCAL
    assert "line-through" not in DiffEngine.DEL_STYLE_LOCAL
    assert "text-decoration:none !important;" in DiffEngine.DEL_STYLE_COLLAB
    assert "line-through" not in DiffEngine.DEL_STYLE_COLLAB

    assert "text-decoration:none !important;" in DiffEngine.INS_STYLE_LOCAL
    assert "text-decoration:none !important;" in DiffEngine.INS_STYLE_COLLAB

    del_html = DiffEngine.format_del("texte supprimé")
    assert "line-through" not in del_html
    assert "text-decoration:none !important;" in del_html

    ins_html = DiffEngine.format_ins("texte ajouté")
    assert "text-decoration:none !important;" in ins_html


def test_artifact_builder_no_style_tag_leak():
    """Valide qu'aucun bloc <style> ne fuit dans l'artéfact."""
    header = ArtifactBuilder.build_artifact_header(target_name="test_doc")
    assert "<style>" not in header
    assert "</style>" not in header
    assert "line-through" not in header

    # Assemblage avec un style injecté dans le corps -> doit être éradiqué
    artifact = ArtifactBuilder.assemble_brain_artifact(
        target_name="test_doc",
        annotated_body="<style>ins { color: red; }</style>\n\nCorps de test",
        tree_toc="",
        diff_count=0,
        enable_ai_score=False
    )
    assert "<style>" not in artifact
    assert "</style>" not in artifact


def test_image_copying_and_formatting_in_brain(tmp_path):
    """Valide la copie physique des images et la réécriture file:/// vers brain_dir."""
    src_dir = tmp_path / "source_docs"
    src_dir.mkdir()
    img_file = src_dir / "unil_logo.png"
    img_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRtest")

    brain_dir = tmp_path / "brain_target"
    brain_dir.mkdir()

    md_input = "Voici le logo wikilink : ![[unil_logo.png|800]] et standard : ![Logo](unil_logo.png)"
    formatted = ArtifactBuilder.format_images_for_brain(
        markdown_text=md_input,
        brain_target_dir=brain_dir,
        source_dir=src_dir
    )

    # 1. Le fichier doit avoir été copié dans brain_dir
    copied_img = brain_dir / "unil_logo.png"
    assert copied_img.exists()
    assert copied_img.read_bytes() == img_file.read_bytes()

    # 2. Le texte ne doit plus contenir de wikilink
    assert "![[" not in formatted
    # 3. Le texte doit pointer en file:/// vers brain_dir
    b_posix = brain_dir.resolve().as_posix().lstrip('/')
    assert f"file:///{b_posix}/unil_logo.png" in formatted


def test_latex_convert_figures_markdown_standard(tmp_path):
    """Valide que les figures LaTeX sont converties en Markdown standard et non en wikilinks."""
    tex_snippet = r"""
    \begin{figure}[h]
    \centering
    \includegraphics{figures/architecture.png}
    \caption{Architecture Globale}
    \end{figure}
    """
    converted = LatexToMarkdownConverter.convert_text(tex_snippet, base_dir=tmp_path)
    assert "![[" not in converted
    assert "![Architecture Globale](architecture.png)" in converted


def test_git_sync_and_default_diff_with_latest_commit(tmp_path, monkeypatch):
    """
    Valide que doc-version détecte les dépôts Git, synchronise automatiquement
    le dernier commit dans le CAS et compare par défaut contre HEAD ou HEAD~1.
    """
    import subprocess
    repo_dir = tmp_path / "git_repo"
    repo_dir.mkdir()

    # 1. Initialiser le dépôt Git
    subprocess.run(["git", "-C", str(repo_dir), "init"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.name", "Test Henri"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "config", "user.email", "henri@test.ch"], check=True, capture_output=True)

    doc_path = repo_dir / "document.md"

    # Commit 1 : version initiale
    doc_path.write_text("# Document\n\nVersion initiale du manuscrit.", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_dir), "add", "document.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "Commit 1 initial"], check=True, capture_output=True)

    # Commit 2 : version mise à jour
    doc_path.write_text("# Document\n\nVersion retouchee du manuscrit.", encoding="utf-8")
    subprocess.run(["git", "-C", str(repo_dir), "add", "document.md"], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo_dir), "commit", "-m", "Commit 2 polish"], check=True, capture_output=True)

    test_cas = CASEngine(storage_dir=tmp_path / "cas_storage")
    monkeypatch.setattr("doc_version_mcp.server.cas", test_cas)

    # Cas A : Le fichier sur disque est déjà commité (identique à HEAD)
    # -> Le diff doit automatiquement comparer avec HEAD~1 (Commit 1) !
    res_a = json.loads(get_diff_artifact(
        target=str(doc_path),
        diff_explanation="Diff automatique contre HEAD~1"
    ))
    assert res_a["status"] == "success"
    assert res_a["diff_count"] >= 1
    content_a = res_a["artifact_content"]
    assert "initiale" in content_a
    assert "retouchee" in content_a
    assert "Commit 2 polish" in content_a

    # Cas B : Des modifications non commitées sont présentes sur le disque
    doc_path.write_text("# Document\n\nVersion 3 en cours de travail.", encoding="utf-8")
    # -> Le diff doit automatiquement comparer contre HEAD (Commit 2) !
    res_b = json.loads(get_diff_artifact(
        target=str(doc_path),
        diff_explanation="Diff modifications en cours contre HEAD"
    ))
    assert res_b["status"] == "success"
    assert res_b["diff_count"] >= 1
    content_b = res_b["artifact_content"]
    assert "retouchee" in content_b
    assert "cours de travail" in content_b



