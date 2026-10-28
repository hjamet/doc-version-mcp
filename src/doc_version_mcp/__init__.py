"""
doc_version_mcp — Serveur FastMCP pour le versionnement documentaire, CAS snapshots, AST diffs et certification Anti-IA.
"""

__version__ = "0.1.0"

from .cas_engine import CASEngine
from .diff_engine import DiffEngine, SectionBlock
from .latex_resolver import LatexMacroEngine, LatexToMarkdownConverter, BibTexParser
from .draft_engine import DraftEngine
from .artifact_builder import ArtifactBuilder, _resolve_compiled_pdf

__all__ = [
    "CASEngine",
    "DiffEngine",
    "SectionBlock",
    "LatexMacroEngine",
    "LatexToMarkdownConverter",
    "BibTexParser",
    "DraftEngine",
    "ArtifactBuilder",
    "_resolve_compiled_pdf",
]
