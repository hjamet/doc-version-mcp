import json
import shutil
from pathlib import Path
import pytest

from doc_version_mcp.artifact_builder import ArtifactBuilder
from doc_version_mcp.server import get_diff_artifact


def test_inject_pdf_banner_direct():
    header = "---\nImage: \"[[cover.png]]\"\n---\n<!-- ARTIFACT: TEST -->\n<!-- Generated at: now -->\n\n# Titre\n\nContenu"
    banner = "> 📄 **Visualisation & Annotation PDF Native Antigravity** : [Ouvrir et annoter doc.pdf](file:///C:/path/doc.pdf) *(commentaires sur texte et captures d'écran annotées)*"
    res = ArtifactBuilder.inject_pdf_banner(header, banner)
    assert banner in res
    # Vérifie que le frontmatter YAML est préservé avant la bannière
    assert res.startswith("---\nImage: \"[[cover.png]]\"\n---\n\n<!-- ARTIFACT: TEST -->")
    # Vérifie que la bannière est insérée avant le titre
    assert res.index(banner) < res.index("# Titre")

    # Vérifie l'idempotence (pas d'injection double)
    res2 = ArtifactBuilder.inject_pdf_banner(res, banner)
    assert res2 == res


def test_get_diff_artifact_copies_stem_pdf_and_injects_banner(tmp_path):
    project_dir = tmp_path / "paper_project"
    project_dir.mkdir()
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()

    tex_file = project_dir / "my_paper.tex"
    tex_file.write_text(r"\section{Introduction} Initial text.", encoding="utf-8")

    # Crée un faux PDF compilé portant le nom du stem
    compiled_pdf = project_dir / "my_paper.pdf"
    compiled_pdf.write_bytes(b"%PDF-1.4 fake pdf content")

    new_content = r"\section{Introduction} Updated text with more details."

    res_json_str = get_diff_artifact(
        target=str(tex_file),
        content=new_content,
        brain_dir=str(brain_dir),
        artifact_name="diff_my_paper",
        mode="paper",
        return_content=True
    )
    res = json.loads(res_json_str)

    assert res["status"] == "success"
    # Vérifie que le PDF a été copié vers brain_dir/<stem>.pdf
    expected_pdf = brain_dir / "my_paper.pdf"
    assert expected_pdf.exists()
    assert expected_pdf.read_bytes() == b"%PDF-1.4 fake pdf content"

    # Vérifie que le chemin du PDF est retourné
    assert res.get("pdf_artifact_path") == expected_pdf.as_posix()

    # Vérifie que l'artéfact Markdown généré contient la bannière cliquable
    art_file = brain_dir / "diff_my_paper.md"
    assert art_file.exists()
    md_content = art_file.read_text(encoding="utf-8")

    b_posix = brain_dir.resolve().as_posix().lstrip('/')
    expected_link = f"file:///{b_posix}/my_paper.pdf"
    assert "> 📄 **Visualisation & Annotation PDF Native Antigravity** :" in md_content
    assert f"[Ouvrir et annoter my_paper.pdf]({expected_link})" in md_content

    # Vérifie que 100% du diff Markdown est bien conservé
    assert "Introduction" in md_content
    assert res.get("diff_count", 0) > 0


def test_get_diff_artifact_fallback_to_main_pdf(tmp_path):
    project_dir = tmp_path / "tex_project"
    project_dir.mkdir()
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()

    tex_file = project_dir / "chapter1.tex"
    tex_file.write_text(r"\section{Chapter 1} Hello.", encoding="utf-8")

    # Crée un main.pdf compilé dans le projet
    main_pdf = project_dir / "main.pdf"
    main_pdf.write_bytes(b"%PDF-1.4 main compiled document")

    res_json_str = get_diff_artifact(
        target=str(tex_file),
        content=r"\section{Chapter 1} Hello world modified.",
        brain_dir=str(brain_dir),
        artifact_name="diff_chapter1",
        mode="paper",
        return_content=True
    )
    res = json.loads(res_json_str)

    assert res["status"] == "success"
    # Le fichier destination prend le stem du document cible chapter1.pdf
    expected_pdf = brain_dir / "chapter1.pdf"
    assert expected_pdf.exists()
    assert expected_pdf.read_bytes() == b"%PDF-1.4 main compiled document"
    assert res.get("pdf_artifact_path") == expected_pdf.as_posix()

    md_content = (brain_dir / "diff_chapter1.md").read_text(encoding="utf-8")
    assert "> 📄 **Visualisation & Annotation PDF Native Antigravity** :" in md_content
    assert "[Ouvrir et annoter chapter1.pdf]" in md_content
