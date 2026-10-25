"""
html_resolver.py — Convertisseur HTML vers Markdown GitHub Flavored avec préservation des balises d'arbitrage.
"""

import os
import re
import shutil
from html.parser import HTMLParser
from pathlib import Path
from typing import Dict, List, Optional, Any


def is_html_doc(t: str, target_path: Optional[Path] = None) -> bool:
    """Détecte si un fichier ou un texte correspond à un document HTML."""
    if not t:
        return False
    if target_path and target_path.suffix.lower() in (".html", ".htm"):
        return True
    return bool(re.search(r'<!DOCTYPE\s+html|<html\b|<body\b', t, re.IGNORECASE))


class HtmlToMarkdownConverter(HTMLParser):
    """
    Convertisseur HTML vers Markdown propre (GFM), basé sur html.parser standard.
    Extrait le contenu textuel structuré, les tableaux GFM, les listes imbriquées,
    résout et copie les images vers brain_dir, et préserve les balises d'arbitrage <XXX ...>.
    """

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        brain_dir: Optional[Path] = None,
        raw_content: Optional[str] = None
    ):
        super().__init__()
        self.base_dir = base_dir.resolve() if base_dir else None
        self.brain_dir = brain_dir.resolve() if brain_dir else None
        self.raw_content = raw_content

        self.output: List[str] = []
        self.stack: List[str] = []

        # Balises non-éditoriales à ignorer intégralement
        self.skip_tags = {'head', 'script', 'style', 'nav', 'title', 'meta', 'link', 'svg', 'noscript'}
        self.skip_stack = 0

        # Suivi d'état
        self.in_header = False
        self.in_pre = False
        self.current_link: str = ""

        # Listes imbriquées
        self.list_stack: List[Dict[str, Any]] = []

        # Tableaux GFM
        self.in_table = False
        self.table_rows: List[List[str]] = []
        self.current_row: List[str] = []
        self.current_cell: List[str] = []
        self.in_cell = False

    @classmethod
    def convert_text(
        cls,
        text: str,
        base_dir: Optional[Path] = None,
        brain_dir: Optional[Path] = None
    ) -> str:
        """Point d'entrée principal pour convertir une chaîne HTML en Markdown propre."""
        if not text or not text.strip():
            return ""

        # Protection des balises d'arbitrage littérales <XXX ...>
        xxx_tokens: Dict[str, str] = {}
        def _mask_xxx(m: re.Match) -> str:
            tok = f"___PROTECTED_ARBITRATION_XXX_{len(xxx_tokens)}___"
            xxx_tokens[tok] = m.group(0)
            return tok

        masked_text = re.sub(r'<XXX\b[^>]*>', _mask_xxx, text)

        converter = cls(base_dir=base_dir, brain_dir=brain_dir, raw_content=masked_text)
        converter.feed(masked_text)
        result = converter.get_markdown()

        # Restauration des balises d'arbitrage littérales
        for tok, val in xxx_tokens.items():
            result = result.replace(tok, val)

        return result

    def resolve_image(self, src: str) -> str:
        """
        Résout le chemin d'une image, et si brain_dir est fourni et le fichier local existe,
        copie l'image dans brain_dir et renvoie l'URI file:///.
        """
        if not src:
            return ""
        if src.startswith(("http://", "https://", "data:")):
            return src

        clean_path = src.strip().strip('"{}\'')
        if clean_path.startswith("./"):
            clean_path = clean_path[2:]
        if clean_path.startswith("file:///"):
            clean_path = clean_path[8:]

        p = Path(clean_path)
        base_dirs: List[Path] = []
        if self.base_dir:
            base_dirs.extend([
                self.base_dir,
                self.base_dir / "assets",
                self.base_dir / "images",
                self.base_dir / "figures",
            ])
        base_dirs.append(Path.cwd())

        found_target: Optional[Path] = None
        check_exts = [".png", ".jpg", ".jpeg", ".webp", ".svg", ".pdf", ".gif"]

        for b_dir in base_dirs:
            if not b_dir.exists():
                continue
            target = b_dir / p
            if target.exists() and target.is_file():
                found_target = target
                break
            if not p.suffix:
                for ext in check_exts:
                    cand = b_dir / f"{clean_path}{ext}"
                    if cand.exists() and cand.is_file():
                        found_target = cand
                        break
                if found_target:
                    break

        if not found_target or not found_target.exists():
            return clean_path

        safe_name = found_target.name.replace(" ", "_")
        if self.brain_dir and self.brain_dir.is_dir():
            try:
                dest_file = self.brain_dir / safe_name
                if found_target.resolve() != dest_file.resolve():
                    shutil.copy2(found_target, dest_file)
            except Exception:
                pass
            b_posix = self.brain_dir.resolve().as_posix().lstrip('/')
            return f"file:///{b_posix}/{safe_name}"

        return clean_path

    def handle_starttag(self, tag: str, attrs: list):
        tag_lower = tag.lower()
        attrs_dict = dict(attrs)

        void_elements = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

        is_skip_trigger = tag_lower in self.skip_tags or attrs_dict.get('class') == 'toc'

        if self.skip_stack > 0:
            if tag_lower not in void_elements:
                self.skip_stack += 1
            return

        if is_skip_trigger:
            if tag_lower not in void_elements:
                self.skip_stack += 1
            return

        self.stack.append(tag_lower)

        # Titres h1 à h6
        if tag_lower in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            level = int(tag_lower[1])
            self.output.append(f"\n\n{'#' * level} ")
            self.in_header = True

        # Paragraphes et séparateurs
        elif tag_lower == 'p':
            if not self.in_cell:
                self.output.append('\n\n')
        elif tag_lower == 'br':
            if self.in_cell:
                self._add_text(' ')
            else:
                self.output.append('\n')
        elif tag_lower == 'hr':
            self.output.append('\n\n---\n\n')

        # Listes à puces ou numérotées
        elif tag_lower == 'ul':
            self.list_stack.append({'type': 'ul', 'index': 0})
            self.output.append('\n')
        elif tag_lower == 'ol':
            self.list_stack.append({'type': 'ol', 'index': 0})
            self.output.append('\n')
        elif tag_lower == 'li':
            if self.list_stack:
                depth = len(self.list_stack) - 1
                indent = "  " * depth
                curr_list = self.list_stack[-1]
                if curr_list['type'] == 'ul':
                    self.output.append(f"\n{indent}- ")
                else:
                    curr_list['index'] += 1
                    self.output.append(f"\n{indent}{curr_list['index']}. ")
            else:
                self.output.append('\n- ')

        # Images
        elif tag_lower == 'img':
            src = attrs_dict.get('src', '')
            alt = attrs_dict.get('alt', 'image')
            resolved_src = self.resolve_image(src)
            self.output.append(f"\n\n![{alt}]({resolved_src})\n\n")

        # Liens
        elif tag_lower == 'a':
            self.current_link = attrs_dict.get('href', '')
            self._add_text('[')

        # Styles inline
        elif tag_lower in ['strong', 'b']:
            if not self.in_header:
                self._add_text('**')
        elif tag_lower in ['em', 'i']:
            self._add_text('*')
        elif tag_lower == 'code':
            if not self.in_pre:
                self._add_text('`')
        elif tag_lower == 'pre':
            self.in_pre = True
            self.output.append('\n\n```\n')

        elif tag_lower == 'blockquote':
            self.output.append('\n\n> ')

        # Tableaux
        elif tag_lower == 'table':
            self.in_table = True
            self.table_rows = []
        elif tag_lower == 'tr':
            self.current_row = []
        elif tag_lower in ['td', 'th']:
            self.in_cell = True
            self.current_cell = []

    def handle_endtag(self, tag: str):
        tag_lower = tag.lower()
        void_elements = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

        if self.skip_stack > 0:
            if tag_lower not in void_elements:
                self.skip_stack -= 1
            return

        if not self.stack:
            return
        self.stack.pop()

        if tag_lower in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
            self.output.append('\n\n')
            self.in_header = False
        elif tag_lower in ['ul', 'ol']:
            if self.list_stack:
                self.list_stack.pop()
            self.output.append('\n')
        elif tag_lower == 'p':
            if not self.in_cell:
                self.output.append('\n\n')
        elif tag_lower == 'a':
            link_target = self.current_link
            self._add_text(f']({link_target})')
            self.current_link = ""
        elif tag_lower in ['strong', 'b']:
            if not self.in_header:
                self._add_text('**')
        elif tag_lower in ['em', 'i']:
            self._add_text('*')
        elif tag_lower == 'code':
            if not self.in_pre:
                self._add_text('`')
        elif tag_lower == 'pre':
            self.in_pre = False
            self.output.append('\n```\n\n')
        elif tag_lower == 'blockquote':
            self.output.append('\n\n')
        elif tag_lower in ['td', 'th']:
            self.in_cell = False
            cell_text = "".join(self.current_cell)
            cell_text = " ".join(cell_text.split())
            cell_text = cell_text.replace('|', r'\|')
            self.current_row.append(cell_text)
        elif tag_lower == 'tr':
            if self.in_table:
                if any(cell.strip() for cell in self.current_row):
                    self.table_rows.append(self.current_row)
        elif tag_lower == 'table':
            self.in_table = False
            self._render_table()

    def handle_data(self, data: str):
        if self.skip_stack > 0:
            return
        self._add_text(data)

    def _add_text(self, text: str):
        if self.in_cell:
            self.current_cell.append(text)
        else:
            self.output.append(text)

    def _render_table(self):
        if not self.table_rows:
            return

        max_cols = max(len(row) for row in self.table_rows)
        if max_cols == 0:
            return

        self.output.append('\n\n')
        for i, row in enumerate(self.table_rows):
            row_cells = row + [''] * (max_cols - len(row))
            self.output.append('| ' + ' | '.join(row_cells) + ' |\n')
            if i == 0:
                self.output.append('| ' + ' | '.join([':---'] * max_cols) + ' |\n')
        self.output.append('\n')

    def get_markdown(self) -> str:
        """Finalise et nettoie la mise en page Markdown."""
        text = "".join(self.output)

        lines = text.split('\n')
        cleaned_lines = []

        in_code_block = False
        for line in lines:
            stripped = line.rstrip()
            if stripped.startswith("```"):
                in_code_block = not in_code_block
                cleaned_lines.append(stripped)
                continue

            if in_code_block:
                cleaned_lines.append(stripped)
                continue

            if line and not stripped:
                continue
            cleaned_lines.append(stripped)

        text = "\n".join(cleaned_lines)
        text = re.sub(r'\n{3,}', '\n\n', text)

        final_lines = []
        in_code_block = False
        for line in text.split('\n'):
            if line.startswith("```"):
                in_code_block = not in_code_block
                final_lines.append(line)
                continue

            if in_code_block:
                final_lines.append(line)
                continue

            if (
                line.startswith('|')
                or line.startswith('> ')
                or re.match(r'^\s*[-*]\s', line)
                or re.match(r'^\s*\d+\.\s', line)
            ):
                final_lines.append(line)
            else:
                final_lines.append(line.lstrip())

        return "\n".join(final_lines).strip()
