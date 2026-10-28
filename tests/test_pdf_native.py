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


def test_compiled_pdf_direct_detection(tmp_path):
    """
    Vérifie la détection directe : Response_to_Reviewers.tex -> Response_to_Reviewers.pdf
    avec présence de '📕 **PDF Compilé** : [Response_to_Reviewers.pdf](file:///...)' en haut de l'artéfact.
    """
    project_dir = tmp_path / "review_response"
    project_dir.mkdir()
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()

    tex_file = project_dir / "Response_to_Reviewers.tex"
    tex_file.write_text(r"\section{Responses} Initial text to reviewers.", encoding="utf-8")

    compiled_pdf = project_dir / "Response_to_Reviewers.pdf"
    compiled_pdf.write_bytes(b"%PDF-1.4 Fake compiled response pdf")

    res_json = get_diff_artifact(
        target=str(tex_file),
        content=r"\section{Responses} Updated response with detailed answers.",
        brain_dir=str(brain_dir),
        artifact_name="diff_responses",
        mode="paper",
        return_content=True
    )
    res = json.loads(res_json)
    assert res["status"] == "success"

    md_content = (brain_dir / "diff_responses.md").read_text(encoding="utf-8")
    expected_pdf_posix = compiled_pdf.resolve().as_posix().lstrip('/')
    expected_src_posix = tex_file.resolve().as_posix().lstrip('/')

    assert f"📄 **Fichier Source** : [Response_to_Reviewers.tex](file:///{expected_src_posix})" in md_content
    assert f"📕 **PDF Compilé** : [Response_to_Reviewers.pdf](file:///{expected_pdf_posix})" in md_content
    assert res.get("compiled_pdf_path") == compiled_pdf.resolve().as_posix()


def test_compiled_pdf_subfile_inclusion_detection(tmp_path):
    r"""
    Vérifie la détection depuis un sous-fichier inclus :
    tex/Declarations.tex -> paper.pdf via paper.tex contenant \documentclass et \input{tex/Declarations}.
    """
    project_dir = tmp_path / "paper_repo"
    project_dir.mkdir()
    tex_dir = project_dir / "tex"
    tex_dir.mkdir()
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()

    subfile = tex_dir / "Declarations.tex"
    subfile.write_text(r"\section{Declarations} Ethical declarations.", encoding="utf-8")

    paper_tex = project_dir / "paper.tex"
    paper_tex.write_text(
        "\\documentclass{article}\n\\begin{document}\n\\input{tex/Declarations}\n\\end{document}",
        encoding="utf-8"
    )

    paper_pdf = project_dir / "paper.pdf"
    paper_pdf.write_bytes(b"%PDF-1.4 Master paper compiled pdf")

    res_json = get_diff_artifact(
        target=str(subfile),
        content=r"\section{Declarations} Ethical declarations updated.",
        brain_dir=str(brain_dir),
        artifact_name="diff_declarations",
        mode="paper",
        return_content=True
    )
    res = json.loads(res_json)
    assert res["status"] == "success"

    md_content = (brain_dir / "diff_declarations.md").read_text(encoding="utf-8")
    expected_pdf_posix = paper_pdf.resolve().as_posix().lstrip('/')
    expected_src_posix = subfile.resolve().as_posix().lstrip('/')

    assert f"📄 **Fichier Source** : [Declarations.tex](file:///{expected_src_posix})" in md_content
    assert f"📕 **PDF Compilé** : [paper.pdf](file:///{expected_pdf_posix})" in md_content
    assert res.get("compiled_pdf_path") == paper_pdf.resolve().as_posix()


def test_compiled_pdf_virtual_target_no_compiled_pdf(tmp_path):
    """
    Vérifie l'absence de ligne '📕 **PDF Compilé**' pour un brouillon virtual: sans PDF.
    """
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()

    res_json = get_diff_artifact(
        target="virtual:response_draft_virtual",
        content="Draft response without physical file.",
        brain_dir=str(brain_dir),
        artifact_name="diff_virtual",
        mode="draft",
        return_content=True
    )
    res = json.loads(res_json)
    assert res["status"] == "success"

    md_content = (brain_dir / "diff_virtual.md").read_text(encoding="utf-8")
    assert "📕 **PDF Compilé**" not in md_content
    assert "📄 **Fichier Source**" not in md_content
    assert res.get("compiled_pdf_path") is None


def test_compiled_pdf_explicit_pdf_path(tmp_path):
    """
    Vérifie le bon fonctionnement du paramètre explicite pdf_path.
    """
    project_dir = tmp_path / "custom_project"
    project_dir.mkdir()
    brain_dir = tmp_path / "brain"
    brain_dir.mkdir()

    tex_file = project_dir / "draft_review.tex"
    tex_file.write_text(r"\section{Review} Text.", encoding="utf-8")

    custom_pdf = project_dir / "custom_build_final.pdf"
    custom_pdf.write_bytes(b"%PDF-1.4 Custom compiled pdf")

    res_json = get_diff_artifact(
        target=str(tex_file),
        content=r"\section{Review} Text updated.",
        brain_dir=str(brain_dir),
        artifact_name="diff_custom",
        mode="paper",
        pdf_path=str(custom_pdf),
        return_content=True
    )
    res = json.loads(res_json)
    assert res["status"] == "success"

    md_content = (brain_dir / "diff_custom.md").read_text(encoding="utf-8")
    expected_pdf_posix = custom_pdf.resolve().as_posix().lstrip('/')
    assert f"📕 **PDF Compilé** : [custom_build_final.pdf](file:///{expected_pdf_posix})" in md_content
    assert res.get("compiled_pdf_path") == custom_pdf.resolve().as_posix()


