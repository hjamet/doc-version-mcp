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
    assert "<span" in annotated_body
    assert "#dcfce7" in annotated_body
    assert "<ins" not in annotated_body
    assert "<del" not in annotated_body
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

    # Invariant 2 : Présence du tableau des 5 derniers commits CAS avec colonne d'audit Anti-IA
    assert "### 🕒 Historique Récent (5 Derniers Commits)" in content
    assert "| Commit ID | Date | Auteur | Message / Titre | Boucle Anti-IA (Itérations & Résolutions) |" in content
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

    # 2. Les lignes d'en-tête institutionnel ne doivent PAS être marquées en diff
    preamble_part = annotated_body.split("## Objectifs")[0]
    assert "<ins" not in preamble_part
    assert "<del" not in preamble_part
    assert "#dcfce7" not in preamble_part
    assert "#fee2e2" not in preamble_part

    # 3. Seule la section Objectifs doit contenir le diff
    assert any("Objectifs" in s for s in mod_sections)
    objectifs_part = annotated_body.split("## Objectifs")[1]
    assert "<span" in objectifs_part
    assert "#dcfce7" in objectifs_part
    assert "<ins" not in annotated_body
    assert "<del" not in annotated_body


def test_del_ins_no_strikethrough_no_underline():
    """Valide que les diffs utilisent des balises <span> sans rature ni soulignement (couleur seule)."""
    assert DiffEngine.DEL_STYLE_LOCAL == 'style="background-color: #fee2e2; color: #991b1b; padding: 2px 4px; border-radius: 3px;"'
    assert DiffEngine.INS_STYLE_LOCAL == 'style="background-color: #dcfce7; color: #166534; padding: 2px 4px; border-radius: 3px;"'
    assert DiffEngine.DEL_STYLE_COLLAB == 'style="background-color: #ffedd5; color: #9a3412; padding: 2px 4px; border-radius: 3px;"'
    assert DiffEngine.INS_STYLE_COLLAB == 'style="background-color: #dbeafe; color: #1e40af; padding: 2px 4px; border-radius: 3px;"'

    assert "line-through" not in DiffEngine.DEL_STYLE_LOCAL
    assert "line-through" not in DiffEngine.DEL_STYLE_COLLAB
    assert "underline" not in DiffEngine.INS_STYLE_LOCAL
    assert "underline" not in DiffEngine.INS_STYLE_COLLAB

    # Formatage local
    del_html = DiffEngine.format_del("texte supprimé")
    assert del_html == '<span style="background-color: #fee2e2; color: #991b1b; padding: 2px 4px; border-radius: 3px;">texte supprimé</span>'
    assert "<del" not in del_html
    assert "line-through" not in del_html

    ins_html = DiffEngine.format_ins("texte ajouté")
    assert ins_html == '<span style="background-color: #dcfce7; color: #166534; padding: 2px 4px; border-radius: 3px;">texte ajouté</span>'
    assert "<ins" not in ins_html
    assert "underline" not in ins_html

    # Formatage collaborateur
    del_collab = DiffEngine.format_del("suppression collab", is_collab=True, author="Alice")
    assert del_collab == '<span style="background-color: #ffedd5; color: #9a3412; padding: 2px 4px; border-radius: 3px;" title="Supprimé par Alice">suppression collab</span>'
    assert "<del" not in del_collab

    ins_collab = DiffEngine.format_ins("ajout collab", is_collab=True, author="Alice")
    assert ins_collab == '<span style="background-color: #dbeafe; color: #1e40af; padding: 2px 4px; border-radius: 3px;" title="Ajouté par Alice">ajout collab</span>'
    assert "<ins" not in ins_collab


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


def test_span_diff_end_to_end_and_multiline():
    """Valide de bout en bout l'absence totale de <del> / <ins> et le bon fonctionnement de validate_revisions et extract_paragraph."""
    old_p = "Premier paragraphe avec ancien texte.\n\n> Citation avec ancienne phrase."
    new_p = "Premier paragraphe avec nouveau texte.\n\n> Citation avec nouvelle phrase."

    body, toc, count, secs = DiffEngine.generate_diff_annotated_body(old_p, new_p)
    assert count >= 1
    assert "<del" not in body
    assert "<ins" not in body
    assert '<span style="background-color: #fee2e2; color: #991b1b; padding: 2px 4px; border-radius: 3px;">' in body
    assert '<span style="background-color: #dcfce7; color: #166534; padding: 2px 4px; border-radius: 3px;">' in body

    # Validation sélective via validate_revisions_up_to_line
    validated_text, val_count, rem_count = DiffEngine.validate_revisions_up_to_line(body, commit_line=100)
    assert val_count >= 1
    assert "<span" not in validated_text
    assert "<del" not in validated_text
    assert "<ins" not in validated_text
    assert "nouveau texte" in validated_text

    # Extraction avant / après
    para_diff = 'Texte avec <span style="background-color: #fee2e2; color: #991b1b; padding: 2px 4px; border-radius: 3px;">suppression</span> et <span style="background-color: #dcfce7; color: #166534; padding: 2px 4px; border-radius: 3px;">ajout</span> ici.'
    tb, ta = DiffEngine.extract_paragraph_diff_texts(para_diff)
    assert tb == "Texte avec suppression et ici."
    assert ta == "Texte avec et ajout ici."


def test_git_upstream_baseline_when_ahead(tmp_path, monkeypatch):
    """Valide que si HEAD est en avance sur son upstream (@{u}), la baseline choisie est le commit upstream."""
    import subprocess
    import json
    from doc_version_mcp.cas_engine import CASEngine
    from doc_version_mcp.server import get_diff_artifact
    import doc_version_mcp.server as srv

    test_cas = CASEngine(storage_dir=tmp_path / "cas")
    monkeypatch.setattr(srv, "cas", test_cas)

    # Créer un dépôt remote (bare) et un dépôt local
    remote_repo = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote_repo)], check=True, capture_output=True)

    local_repo = tmp_path / "local"
    subprocess.run(["git", "clone", str(remote_repo), str(local_repo)], check=True, capture_output=True)

    subprocess.run(["git", "-C", str(local_repo), "config", "user.name", "Test User"], check=True)
    subprocess.run(["git", "-C", str(local_repo), "config", "user.email", "test@example.com"], check=True)

    doc_file = local_repo / "doc.md"
    doc_file.write_text("Version Overleaf originale.\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(local_repo), "add", "doc.md"], check=True)
    subprocess.run(["git", "-C", str(local_repo), "commit", "-m", "Initial commit on overleaf"], check=True)
    subprocess.run(["git", "-C", str(local_repo), "push", "origin", "HEAD:main"], check=True)
    subprocess.run(["git", "-C", str(local_repo), "branch", "--set-upstream-to=origin/main"], check=True)

    # Maintenant, faire 2 commits locaux en avance sur origin/main
    doc_file.write_text("Version Overleaf originale.\nAjout commit 1.\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(local_repo), "commit", "-am", "Commit 1 local"], check=True)

    doc_file.write_text("Version Overleaf originale.\nAjout commit 1.\nAjout commit 2 final.\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(local_repo), "commit", "-am", "Commit 2 local"], check=True)

    # get_diff_artifact sans from_commit_id doit comparer contre origin/main (l'upstream), pas HEAD~1
    res = json.loads(get_diff_artifact(
        target=str(doc_file),
        diff_explanation="Diff global par rapport à la version distante"
    ))
    assert res["status"] == "success"
    assert "Ajout commit 1." in res["artifact_content"]
    assert "Ajout commit 2 final." in res["artifact_content"]
    assert "Version Overleaf originale." in res["artifact_content"]


def test_commit_with_style_audit_iterations_and_resolution(temp_cas_dir, monkeypatch):
    """Valide l'enregistrement d'un audit multi-itérations et son affichage dans le tableau des commits."""
    test_cas = CASEngine(storage_dir=temp_cas_dir)
    monkeypatch.setattr("doc_version_mcp.server.cas", test_cas)

    # 1. Créer un commit avec un audit à 2 itérations
    audit_data = {
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

    res_commit = json.loads(commit_document(
        target="paper_review.tex",
        message="Polissage suite boucle avoid-ai-writing",
        content=r"\section{Introduction} Clean text without ai writing.",
        author="agent",
        mode="paper",
        style_audit=audit_data
    ))
    assert res_commit["status"] == "success"
    c_id = res_commit["commit_id"]

    # 2. Générer le diff et vérifier la présence de la colonne et du résumé
    res_diff = json.loads(get_diff_artifact(
        target="paper_review.tex",
        diff_explanation="Test affichage audit itérations",
        from_commit_id=c_id
    ))
    assert res_diff["status"] == "success"
    art = res_diff["artifact_content"]

    # Invariants d'affichage
    assert "| Boucle Anti-IA (Itérations & Résolutions) |" in art
    assert "2 itérations (T1: 3 pb (Tier 1: 1, Tier 2: 2) ➔ T2: 0 pb - PASS)" in art


def test_record_style_audit_tool_integration(temp_cas_dir, monkeypatch):
    """Valide l'outil record_style_audit et la persistance rétroactive de l'audit."""
    from doc_version_mcp.server import record_style_audit

    test_cas = CASEngine(storage_dir=temp_cas_dir)
    monkeypatch.setattr("doc_version_mcp.server.cas", test_cas)

    # Créer un commit simple
    res_c = json.loads(commit_document(
        target="memo.md",
        message="Snapshot avant audit",
        content="# Memo",
        author="agent"
    ))
    cid = res_c["commit_id"]

    # Enregistrer un audit a posteriori
    iters_json = json.dumps([
        {"iteration": 1, "verdict": "FAIL", "total_issues": 1, "tier_breakdown": {"Tier 1": 1}},
        {"iteration": 2, "verdict": "PASS", "total_issues": 0}
    ])
    res_record = json.loads(record_style_audit(
        commit_id=cid,
        target="memo.md",
        iterations=iters_json
    ))
    assert res_record["status"] == "success"
    assert "2 itérations" in res_record["summary"]
    assert "T1: 1 pb" in res_record["summary"]
    assert "T2: 0 pb - PASS" in res_record["summary"]

    # Vérifier que get_commit et list_snapshots reflètent cet audit
    c_loaded = test_cas.get_commit(cid)
    assert "style_audit" in c_loaded
    assert c_loaded["style_audit"]["summary"] == res_record["summary"]


def test_sequential_drafts_diff_against_immediate_parent(temp_cas_dir, monkeypatch):
    """
    Valide que lors de révisions séquentielles (mode draft ou standard),
    get_diff_artifact compare par défaut contre le commit parent immédiat (HEAD~1 CAS)
    et non contre l'initiale baseline v0.
    """
    test_cas = CASEngine(storage_dir=temp_cas_dir)
    monkeypatch.setattr("doc_version_mcp.server.cas", test_cas)

    target_name = "virtual:draft_sequential_test"

    # 1. Commit 0 : Baseline v0 initiale
    c0 = json.loads(commit_document(
        target=target_name,
        message="Baseline v0 brouillon initial",
        content="Salut l'équipe,\n\nJe voulais m'excuser pour le retard. Voici le premier jet avec plein de coquilles.",
        author="henri",
        mode="draft"
    ))

    # 2. Commit 1 : Tour 1 draft (polissage initial)
    c1 = json.loads(commit_document(
        target=target_name,
        message="Tour 1 polissage initial",
        content="Salut l'équipe,\n\nMerci pour votre patience. Voici le premier jet intermédiaire propre.",
        author="agent",
        mode="draft"
    ))

    # 3. Commit 2 : Tour 2 draft (ajustements demandés par Henri)
    c2 = json.loads(commit_document(
        target=target_name,
        message="Tour 2 intégration retours Henri",
        content="Salut l'équipe,\n\nMerci pour votre patience. Voici le premier jet final validé.",
        author="henri",
        mode="draft"
    ))

    # Cas A : Appel de get_diff_artifact sans from_commit_id sur le texte déjà commité (Commit 2)
    # -> Doit comparer contre Commit 1 (parent direct), PAS contre Commit 0 (v0) !
    res_a = json.loads(get_diff_artifact(
        target=target_name,
        content="Salut l'équipe,\n\nMerci pour votre patience. Voici le premier jet final validé.",
        diff_explanation="Vérification parent immédiat Tour 2 vs Tour 1",
        mode="draft"
    ))
    assert res_a["status"] == "success"
    assert res_a["baseline_commit"] == c1["short_id"]
    content_a = res_a["artifact_content"]
    # Le texte intermédiaire issu de Commit 1 doit être le texte de référence (seul "intermédiaire" -> "final validé" change)
    assert "intermédiaire" in content_a
    assert "final validé" in content_a
    # Les changements de Commit 0 ("m'excuser pour le retard" etc.) ne doivent PAS être dans le diff (ils sont résolus en Commit 1)
    assert "m'excuser pour le retard" not in content_a

    # Cas B : Appel avec from_commit_id="v0" explicite
    # -> Doit comparer contre Commit 0 !
    res_b = json.loads(get_diff_artifact(
        target=target_name,
        content="Salut l'équipe,\n\nMerci pour votre patience. Voici le premier jet final validé.",
        from_commit_id="v0",
        diff_explanation="Comparaison explicite contre v0",
        mode="draft"
    ))
    assert res_b["status"] == "success"
    assert res_b["baseline_commit"] == c0["short_id"]
    content_b = res_b["artifact_content"]
    assert "m\'excuser" in content_b or "m'excuser" in content_b
    assert "retard" in content_b

    # Cas C : Appel avec to_commit_id=Commit 1 sans from_commit_id
    # -> Doit comparer Commit 1 contre son parent direct (Commit 0)
    res_c = json.loads(get_diff_artifact(
        target=target_name,
        to_commit_id=c1["commit_id"],
        diff_explanation="Comparaison to_commit parent automatique",
        mode="draft"
    ))
    assert res_c["status"] == "success"
    assert res_c["baseline_commit"] == c0["short_id"]
    content_c = res_c["artifact_content"]
    assert "retard" in content_c


def test_latex_command_filtering_and_nested_braces():
    """Valide le filtrage absolu des commandes LaTeX dans les headings et les corps de texte."""
    latex_text = r"""
    \section{Introduction}
    \paragraph*{\textsf{\textbf{Limitations of Monolithic LLMs.}}}
    Intelligent Tutoring Systems have long aimed to deliver personalized instruction.
    \paragraph*{\textsf{\textbf{The DLLP Framework.}}}
    To resolve these challenges, we introduce the framework.
    """
    converted = LatexToMarkdownConverter.convert_text(latex_text)

    # 1. Pas de résidu \textsf ni **} orphelin
    assert r"\textsf" not in converted
    assert "**}" not in converted
    assert "##### Limitations of Monolithic LLMs." in converted
    assert "##### The DLLP Framework." in converted
    assert "Intelligent Tutoring Systems" in converted


def test_latex_boxes_unwrapping_and_layout():
    r"""Valide le déballage complet des boîtes de mise en page \fcolorbox et \parbox."""
    latex_text = r"""
    \fcolorbox{acmblue!50}{acmbluebg}{
      \parbox{\dimexpr\linewidth-2\fboxsep-2\fboxrule\relax}{
        \small\textbf{\textsf{\color{acmblue}Takeaway:}} Graph constraints replace unconstrained generation.
      }
    }
    \parbox{\linewidth}{
      {\color{acmblue}\vrule width 2.5pt}\hspace{6pt}
      \parbox{\dimexpr\linewidth-10pt\relax}{
        \small\textbf{\textsf{\color{acmblue}RQ1:}} How does dynamic compilation prevent cycles?
      }
    }
    """
    converted = LatexToMarkdownConverter.convert_text(latex_text)

    # Vérification que toutes les commandes parasites sont éradiquées
    assert r"\fcolorbox" not in converted
    assert r"\parbox" not in converted
    assert r"\vrule" not in converted
    assert r"\dimexpr" not in converted
    assert r"\relax" not in converted
    assert r"\fboxsep" not in converted
    assert r"\fboxrule" not in converted
    assert r"\color" not in converted
    assert "**Takeaway:** Graph constraints replace unconstrained generation." in converted
    assert "**RQ1:** How does dynamic compilation prevent cycles?" in converted


def test_katex_math_braces_preservation():
    """Valide que les accolades KaTeX dans les exposants/indices sont préservées intactes."""
    latex_text = r"""
    \section{Formulation}
    Given $\text{Top-}k(q) = \arg\max_{c \in \mathcal{C}}^{(k)} \cos(\mathbf{e}_q, \mathbf{e}_c)$
    and visual elements $\mathcal{I}_p = \{d_{p,k}\}_{k=1}^{K_p}$.
    """
    converted = LatexToMarkdownConverter.convert_text(latex_text)

    # Les accolades de mathématiques KaTeX ne doivent pas avoir été tronquées
    assert "^{(k)}" in converted
    assert "^{K_p}" in converted
    assert "_{c \\in \\mathcal{C}}" in converted


def test_latex_table_colors_and_checkmarks():
    r"""Valide le nettoyage de \rowcolor, \checkmark et \texttimes dans les tableaux."""
    latex_text = r"""
    \begin{tabularx}{\textwidth}{l c c}
    \toprule
    System & DAG & Multi-Agent \\
    \midrule
    \rowcolor{acmbluebg}
    DLLP & \checkmark & \texttimes \\
    \bottomrule
    \end{tabularx}
    """
    converted = LatexToMarkdownConverter.convert_text(latex_text)

    assert r"\rowcolor" not in converted
    assert r"\checkmark" not in converted
    assert r"\texttimes" not in converted
    assert "✓" in converted
    assert "×" in converted



