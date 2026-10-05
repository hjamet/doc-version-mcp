"""
test_latex_and_diff.py — Tests ciblés pour les filtres LaTeX et le mode block-diff par paragraphe.
"""

import re
import pytest

from doc_version_mcp.diff_engine import DiffEngine
from doc_version_mcp.latex_resolver import LatexMacroEngine, LatexToMarkdownConverter


def test_paragraph_diff_under_threshold_word_diff():
    """
    Vérifie qu'un paragraphe avec un taux de modification <= 50% (ex: 30%)
    reste en mode word-diff chirurgical (un seul paragraphe avec spans inline).
    """
    old_p = "The quick brown fox jumps gracefully over the very lazy sleeping dog near the old riverbank."
    # Changement d'un ou deux mots (~20-25% de modification)
    new_p = "The fast brown fox jumps gracefully over the very lazy sleeping cat near the old riverbank."

    old_doc = f"## Section\n\n{old_p}\n"
    new_doc = f"## Section\n\n{new_p}\n"

    annotated_body, _, diff_count, _ = DiffEngine.generate_diff_annotated_body(
        old_text=old_doc,
        new_text=new_doc,
        is_collab=False,
        author_name="agent",
        block_diff_threshold=0.5
    )

    # Doit contenir les balises inline sans scinder le paragraphe en deux blocs complets
    assert "quick" in annotated_body
    assert "fast" in annotated_body
    assert "dog" in annotated_body
    assert "cat" in annotated_body
    # Il ne doit pas y avoir l'intégralité de old_p dans un seul bloc rouge séparé
    assert not (f">{old_p}</span>" in annotated_body or f">{old_p} </span>" in annotated_body)


def test_paragraph_diff_over_threshold_block_diff():
    """
    Vérifie qu'un paragraphe avec un taux de modification > 50% (ex: 80%)
    bascule en mode block-diff : ancien paragraphe entier en rouge, puis nouveau entier en vert.
    """
    old_p = "This initial formulation relied heavily on traditional collaborative filtering algorithms which suffered from cold-start problems and data sparsity across all benchmark datasets."
    new_p = "Our novel architecture leverages dense representation learning with self-supervised contrastive objectives to achieve superior generalization under extreme zero-shot transfer conditions."

    old_doc = f"## Methodology\n\n{old_p}\n"
    new_doc = f"## Methodology\n\n{new_p}\n"

    annotated_body, _, diff_count, _ = DiffEngine.generate_diff_annotated_body(
        old_text=old_doc,
        new_text=new_doc,
        is_collab=False,
        author_name="agent",
        block_diff_threshold=0.5
    )

    # Vérifie la présence du bloc rouge intégral
    assert re.search(r'<span style="[^"]*#fee2e2[^"]*">' + re.escape(old_p) + r'</span>', annotated_body)
    # Vérifie la présence du bloc vert intégral
    assert re.search(r'<span style="[^"]*#dcfce7[^"]*">' + re.escape(new_p) + r'</span>', annotated_body)


def test_pure_addition_and_pure_deletion():
    """
    Vérifie le comportement en cas d'ajout pur ou de suppression pure d'un paragraphe.
    """
    p1 = "Paragraph that remains strictly unchanged across versions."
    p_added = "Brand new paragraph that has been completely added in this revision."
    p_deleted = "Outdated paragraph that has been completely removed from this section."

    # 1. Ajout pur
    old_doc1 = f"## Sec\n\n{p1}\n"
    new_doc1 = f"## Sec\n\n{p1}\n\n{p_added}\n"
    annotated_body1, _, _, _ = DiffEngine.generate_diff_annotated_body(old_doc1, new_doc1)
    assert re.search(r'<span style="[^"]*#dcfce7[^"]*">' + re.escape(p_added) + r'</span>', annotated_body1)

    # 2. Suppression pure
    old_doc2 = f"## Sec\n\n{p1}\n\n{p_deleted}\n"
    new_doc2 = f"## Sec\n\n{p1}\n"
    annotated_body2, _, _, _ = DiffEngine.generate_diff_annotated_body(old_doc2, new_doc2)
    assert re.search(r'<span style="[^"]*#fee2e2[^"]*">' + re.escape(p_deleted) + r'</span>', annotated_body2)


def test_latex_runningexample_and_algorithm():
    """
    Vérifie la conversion des environnements runningexample et algorithm/algorithmic sans résidus LaTeX.
    """
    snippet = r"""
\begin{runningexample}{Phase II}
In the second phase, candidates are reranked.
\end{runningexample}

\begin{algorithm}
\caption{Dual-Stage Agentic Reasoning}
\label{alg:dual_stage}
\begin{algorithmic}[1]
\Require Query context $\mathcal{Q}$, candidate pool $\mathcal{C}$
\Ensure Final ranking $\pi^*$
\State Initialize shortlist $\mathcal{S} \leftarrow \emptyset$
\For{each candidate $c \in \mathcal{C}$}
    \State Compute score $s \leftarrow f(c, \mathcal{Q})$ \Comment{Forward pass}
    \If{$s > \tau$}
        \State $\mathcal{S} \leftarrow \mathcal{S} \cup \{c\}$
    \EndIf
\EndFor
\Statex
\State \Return Rerank($\mathcal{S}$)
\end{algorithmic}
\end{algorithm}
"""
    res = LatexToMarkdownConverter.convert_text(snippet)

    # runningexample converti en callout
    assert "> [!NOTE] **Running example : Phase II**" in res
    assert "In the second phase, candidates are reranked." in res
    assert r"\begin{runningexample}" not in res
    assert r"\end{runningexample}" not in res

    # algorithm converti en callout avec pseudo-code propre
    assert "Algorithme : Dual-Stage Agentic Reasoning" in res
    assert "**Require:**" in res
    assert "**Ensure:**" in res
    assert "**for** each candidate" in res
    assert "**if**" in res
    assert "*// Forward pass*" in res

    # Aucune commande LaTeX d'algorithme résiduelle
    assert r"\State" not in res
    assert r"\Statex" not in res
    assert r"\Comment" not in res
    assert r"\Require" not in res
    assert r"\Ensure" not in res
    assert r"\For" not in res
    assert r"\EndFor" not in res
    assert r"\If" not in res
    assert r"\EndIf" not in res


def test_latex_cmidrule_and_macro_trailing_space():
    """
    Vérifie le nettoyage de \\cmidrule(lr){...} et la préservation des espaces après macro.
    """
    latex_input = r"""
\newcommand{\red}[1]{\textcolor{red}{#1}}
Values in \red{red} indicate the best performing configuration on the benchmark.

\begin{tabular}{lcccc}
\toprule
Model & NDCG@10 & HR@10 & MRR & MAP \\
\cmidrule(lr){2-5}
Baseline & 0.421 & 0.650 & 0.310 & 0.280 \\
\bottomrule
\end{tabular}
"""
    engine = LatexMacroEngine()
    text, macros = engine.extract_macros(latex_input)
    expanded = engine.expand_macros(text, macros)

    # Vérifie que la macro expansée préserve l'espace avant indicate
    assert r"\textcolor{red}{red} indicate" in expanded

    conv = LatexToMarkdownConverter.convert_text(expanded)
    assert r"\cmidrule" not in conv
    assert "Values in red indicate" in conv
    assert "Values in redindicate" not in conv
    assert "| Baseline | 0.421 | 0.650 | 0.310 | 0.280 |" in conv


def test_latex_figure_with_slmbox_caption():
    """
    Vérifie que pour une figure contenant une boîte slmbox sans \\caption,
    le titre slmbox est extrait comme légende au lieu de produire 'Figure : Figure'.
    """
    snippet = r"""
\begin{figure}[t]
\centering
\begin{slmbox}{MovieLens-10M Reranking Example}
User prompt: Recommend a sci-fi movie.
System: Interstellar (2014).
\end{slmbox}
\label{fig:movielens_example}
\end{figure}
"""
    res = LatexToMarkdownConverter.convert_text(snippet)
    assert "Figure : Figure" not in res
    assert "MovieLens-10M Reranking Example" in res
    assert "> [!NOTE]" in res
    assert "User prompt: Recommend a sci-fi movie." in res


def test_latex_keywords_stripped_from_abstract():
    """
    Vérifie que \\keywords{...} est extrait en métadonnées et supprimé du texte de l'abstract.
    """
    snippet = r"""
\begin{abstract}
This paper introduces an innovative benchmark for generative recommendation.
\keywords{Recommender Systems \and Large Language Models \and Evaluation}
\end{abstract}
"""
    conv = LatexToMarkdownConverter(raw_content=snippet)
    res = conv.convert()
    assert "Recommender Systems" in conv.keywords
    assert r"\keywords" not in res
    assert r"\and" not in res
    assert "This paper introduces an innovative benchmark" in res


def test_diff_abstract_block_mode_and_quotes():
    """
    Vérifie qu'un abstract modifié > 90% dans un bloc de citation '>'
    est rendu intégralement en bloc rouge (ancien) puis en bloc vert (nouveau),
    avec le préfixe '>' préservé sur chaque ligne.
    """
    old_doc = (
        "## Abstract\n\n"
        "> Collaborative filtering (CF) algorithms degrade substantially in extreme sparse recommendation scenarios.\n"
        ">\n"
        "> Extensive offline evaluations across three diverse benchmarks demonstrate that our method outperforms baselines.\n"
    )
    new_doc = (
        "## Abstract\n\n"
        "> Recommendation systems on mobile devices require accurate on-device inference under tight latency budgets.\n"
        ">\n"
        "> Our distilled student model achieves superior throughput while preserving recommendation fidelity.\n"
    )

    annotated, _, _, _ = DiffEngine.generate_diff_annotated_body(old_doc, new_doc, block_diff_threshold=0.5)

    # 1. Vérifie la présence du bloc rouge (ancien abstract)
    assert re.search(r'>\s*<span style="[^"]*#fee2e2[^"]*">Collaborative filtering', annotated)
    # 2. Vérifie la présence du bloc vert (nouvel abstract)
    assert re.search(r'>\s*<span style="[^"]*#dcfce7[^"]*">Recommendation systems', annotated)
    # 3. L'ancien bloc rouge doit précéder le nouveau bloc vert
    pos_del = annotated.find("Collaborative filtering")
    pos_ins = annotated.find("Recommendation systems")
    assert 0 <= pos_del < pos_ins
    # 4. Aucun span ne contient de saut de ligne
    spans_with_nl = re.findall(r'<span\b[^>]*>[^<]*\n[^<]*</span>', annotated)
    assert len(spans_with_nl) == 0


def test_diff_display_equations_separate_blocks():
    """
    Vérifie que les équations modifiées apparaissent dans deux blocs $$ distincts
    (ancien puis nouveau), sans fusion dans un même bloc $$.
    """
    old_doc = (
        "## Methodology\n\n"
        "The teacher model produces the candidate rationale:\n\n"
        "$$\n"
        "r_u = \\mathcal{T}(P_u, C'_u, i^{*}_u).\n"
        "$$\n\n"
        "Next paragraph continues here.\n"
    )
    new_doc = (
        "## Methodology\n\n"
        "The teacher model produces the candidate rationale:\n\n"
        "$$\n"
        "r_u = \\mathcal{T}(P_u, C_u, i^{*}_u).\n"
        "$$\n\n"
        "Next paragraph continues here.\n"
    )

    annotated, _, _, _ = DiffEngine.generate_diff_annotated_body(old_doc, new_doc)

    # Vérifie que les deux équations sont présentes
    assert "C'_u" in annotated
    assert "C_u" in annotated

    # Vérifie qu'aucun bloc $$ ne contient les deux équations fusionnées
    for block in re.findall(r'\$\$(.*?)\$\$', annotated, flags=re.DOTALL):
        assert block.count("r_u =") <= 1

    # Les équations doivent être dans des blocs séparés
    math_blocks = re.findall(r'\$\$(.*?)\$\$', annotated, flags=re.DOTALL)
    assert len(math_blocks) == 2

    # Aucun span ne contient de saut de ligne
    spans_with_nl = re.findall(r'<span\b[^>]*>[^<]*\n[^<]*</span>', annotated)
    assert len(spans_with_nl) == 0


def test_diff_zero_spans_with_newline_complex_section():
    """
    Vérifie sur une section mêlant citations, listes, inline math et display math
    que le nombre de <span> contenant un saut de ligne est strictement 0.
    """
    old_doc = (
        "## Section\n\n"
        "> Quote line 1 with $x = 1$.\n"
        "> Quote line 2 with $y = 2$.\n\n"
        "Paragraph with detailed description of the retriever where $i^*_u \\notin C_u$.\n\n"
        "$$\n"
        "\\mathcal{L}_{\\text{old}} = \\sum_{i=1}^N (y_i - \\hat{y}_i)^2\n"
        "$$\n\n"
        "- Item 1: alpha\n"
        "- Item 2: beta\n"
    )
    new_doc = (
        "## Section\n\n"
        "> Rewritten quote line 1 with updated $x = 10$.\n"
        "> Rewritten quote line 2 with updated $y = 20$.\n\n"
        "Modified paragraph with concise description of the shortlist with $i^*_u \\in C_u$.\n\n"
        "$$\n"
        "\\mathcal{L}_{\\text{new}} = -\\sum_{i=1}^N y_i \\log \\hat{y}_i\n"
        "$$\n\n"
        "- Item 1: alpha prime\n"
        "- Item 2: beta prime\n"
    )

    annotated, _, _, _ = DiffEngine.generate_diff_annotated_body(old_doc, new_doc)
    spans_with_nl = re.findall(r'<span\b[^>]*>[^<]*\n[^<]*</span>', annotated)
    assert len(spans_with_nl) == 0

