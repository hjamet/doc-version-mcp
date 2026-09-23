"""
latex_resolver.py — Résolution récursive AST des macros, inclusions LaTeX, citations BibTeX et rastérisation 300 DPI.
"""

import os
import re
import shutil
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set, Any


class BibTexParser:
    """Parseur BibTeX autonome pour résoudre les citations avec support des accents LaTeX."""

    @staticmethod
    def decode_latex_accents(text: str) -> str:
        text = text.replace(r'{\L}', 'Ł').replace(r'{\l}', 'ł')
        text = text.replace(r'\"u', 'ü').replace(r'{\"u}', 'ü').replace(r'\"{u}', 'ü')
        text = text.replace(r'\"o', 'ö').replace(r'{\"o}', 'ö').replace(r'\"{o}', 'ö')
        text = text.replace(r'\"a', 'ä').replace(r'{\"a}', 'ä').replace(r'\"{a}', 'ä')
        text = text.replace(r'\"e', 'ë').replace(r'{\"e}', 'ë').replace(r'\"{e}', 'ë')
        text = text.replace(r'\'e', 'é').replace(r'{\'e}', 'é').replace(r'\'{e}', 'é')
        text = text.replace(r'\`e', 'è').replace(r'{\`e}', 'è').replace(r'\`{e}', 'è')
        text = text.replace(r'\^e', 'ê').replace(r'{\^e}', 'ê').replace(r'\^{e}', 'ê')
        text = text.replace(r'\'a', 'á').replace(r'{\'a}', 'á').replace(r'\'{a}', 'á')
        text = text.replace(r'\`a', 'à').replace(r'{\`a}', 'à').replace(r'\`{a}', 'à')
        text = text.replace(r'\^a', 'â').replace(r'{\^a}', 'â').replace(r'\^{a}', 'â')
        text = text.replace(r'\'u', 'ú').replace(r'{\'u}', 'ú').replace(r'\'{u}', 'ú')
        text = text.replace(r'\`u', 'ù').replace(r'{\`u}', 'ù').replace(r'\`{u}', 'ù')
        text = text.replace(r'\^u', 'û').replace(r'{\^u}', 'û').replace(r'\^{u}', 'û')
        text = text.replace(r'\'i', 'í').replace(r'{\'i}', 'í').replace(r'\'{i}', 'í').replace(r'\'{\i}', 'í')
        text = text.replace(r'\`i', 'ì').replace(r'{\`i}', 'ì').replace(r'\`{i}', 'ì').replace(r'\`{\i}', 'ì')
        text = text.replace(r'\^i', 'î').replace(r'{\^i}', 'î').replace(r'\^{i}', 'î').replace(r'\^{\i}', 'î')
        text = text.replace(r'\"i', 'ï').replace(r'{\"i}', 'ï').replace(r'\"{i}', 'ï').replace(r'\"{\i}', 'ï')
        text = text.replace(r'\'o', 'ó').replace(r'{\'o}', 'ó').replace(r'\'{o}', 'ó')
        text = text.replace(r'\`o', 'ò').replace(r'{\`o}', 'ò').replace(r'\`{o}', 'ò')
        text = text.replace(r'\^o', 'ô').replace(r'{\^o}', 'ô').replace(r'\^{o}', 'ô')
        text = text.replace(r'\~n', 'ñ').replace(r'{\~n}', 'ñ')
        text = text.replace(r'\c{c}', 'ç').replace(r'{\c{c}}', 'ç')
        text = text.replace(r'\c{C}', 'Ç').replace(r'{\c{C}}', 'Ç')
        text = text.replace(r'\ss', 'ß').replace(r'{\ss}', 'ß')
        text = text.replace(r'\oe', 'œ').replace(r'{\oe}', 'œ')
        text = text.replace(r'\OE', 'Œ').replace(r'{\OE}', 'Œ')
        text = text.replace(r'\ae', 'æ').replace(r'{\ae}', 'æ')
        text = text.replace(r'\AE', 'Æ').replace(r'{\AE}', 'Æ')

        # Accents caron / háček (\v)
        text = text.replace(r'{\v{c}}', 'č').replace(r'\'{c}', 'ć').replace(r'\v{c}', 'č').replace(r'\v c', 'č')
        text = text.replace(r'{\v{C}}', 'Č').replace(r'\'{C}', 'Ć').replace(r'\v{C}', 'Č').replace(r'\v C', 'Č')
        text = text.replace(r'{\v{s}}', 'š').replace(r'\v{s}', 'š').replace(r'\v s', 'š')
        text = text.replace(r'{\v{S}}', 'Š').replace(r'\v{S}', 'Š').replace(r'\v S', 'Š')
        text = text.replace(r'{\v{z}}', 'ž').replace(r'\v{z}', 'ž').replace(r'\v z', 'ž')
        text = text.replace(r'{\v{Z}}', 'Ž').replace(r'\v{Z}', 'Ž').replace(r'\v Z', 'Ž')
        text = text.replace(r'{\v{r}}', 'ř').replace(r'\v{r}', 'ř').replace(r'\v r', 'ř')
        text = text.replace(r'{\v{e}}', 'ě').replace(r'\v{e}', 'ě').replace(r'\v e', 'ě')
        text = text.replace(r'{\v{d}}', 'ď').replace(r'\v{d}', 'ď')
        text = text.replace(r'{\v{t}}', 'ť').replace(r'\v{t}', 'ť')
        text = text.replace(r'{\v{n}}', 'ň').replace(r'\v{n}', 'ň')
        # Formes avec backslash direct comme \vsevic ou \vcek
        text = re.sub(r'\\v\s*([cszredtnCSZREDTN])', r'\1', text)
        text = re.sub(r'\\\'\s*([cszCSZ])', r'\1', text)
        text = re.sub(r'\\&', '&', text)
        return text

    def __init__(self):
        self.entries: Dict[str, Dict[str, str]] = {}

    def load_bib_file(self, bib_path: Path):
        if not bib_path.exists():
            return
        try:
            content = bib_path.read_text(encoding="utf-8", errors="replace")
            self.parse_bib_content(content)
        except Exception as e:
            pass

    def parse_bib_content(self, content: str):
        entry_pattern = re.compile(r'@(\w+)\s*\{\s*([^,]+),([^@]*)\}', re.DOTALL)
        field_pattern = re.compile(r'(\w+)\s*=\s*[\{"](.*?)[\}"]\s*(?:,|$)', re.DOTALL)

        for match in entry_pattern.finditer(content):
            entry_type = match.group(1).lower()
            key = match.group(2).strip()
            body = match.group(3)

            fields = {"_type": entry_type}
            for f_match in field_pattern.finditer(body):
                f_name = f_match.group(1).strip().lower()
                f_val = f_match.group(2).strip()
                f_val = self.decode_latex_accents(f_val)
                f_val = re.sub(r'[\{\}]', '', f_val)
                fields[f_name] = f_val

            self.entries[key] = fields

    def format_citation(self, key: str, citet: bool = False) -> str:
        key = key.strip()
        if key not in self.entries:
            return f"[{key}]" if not citet else f"{key}"

        entry = self.entries[key]
        authors_raw = entry.get("author", "")
        year = entry.get("year", "s.d.")

        if authors_raw:
            authors_list = [a.strip() for a in authors_raw.split(" and ")]
            first_author = authors_list[0].split(",")[0].strip()
            if len(authors_list) == 1:
                author_str = first_author
            elif len(authors_list) == 2:
                second_author = authors_list[1].split(",")[0].strip()
                author_str = f"{first_author} & {second_author}"
            else:
                author_str = f"{first_author} et al."
        else:
            author_str = entry.get("title", key)[:30]

        if citet:
            return f"{author_str} [{year}]"
        else:
            return f"[{author_str}, {year}]"

    def format_full_reference(self, key: str) -> str:
        if key not in self.entries:
            return f"- **[{key}]** : Référence BibTeX non trouvée."

        entry = self.entries[key]
        authors = entry.get("author", "Auteurs inconnus")
        title = entry.get("title", "Sans titre")
        year = entry.get("year", "s.d.")
        venue = entry.get("booktitle") or entry.get("journal") or entry.get("publisher") or ""

        ref = f"- **[{key}]** : {authors} ({year}). *{title}*."
        if venue:
            ref += f" In *{venue}*."
        return ref


class LatexMacroEngine:
    """Moteur d'extraction et d'expansion récursive de macros LaTeX."""

    @staticmethod
    def extract_braced_group(text: str, start_idx: int) -> Tuple[str, int]:
        idx = text.find('{', start_idx)
        if idx == -1:
            return "", start_idx
        depth = 1
        i = idx + 1
        content_start = i
        n = len(text)
        while i < n and depth > 0:
            c = text[i]
            if c == '\\':
                i += 2
                continue
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return text[content_start:i], i + 1
            i += 1
        return text[content_start:i], i

    @classmethod
    def extract_macros(cls, text: str) -> Tuple[str, Dict[str, Dict[str, Any]]]:
        macros: Dict[str, Dict[str, Any]] = {}
        pattern_new = re.compile(
            r'\\(?:newcommand|renewcommand|providecommand)\*?\s*(?:\{\\([a-zA-Z]+)\}|\\([a-zA-Z]+))(?:\s*\[(\d+)\])?\s*\{'
        )
        while True:
            m = pattern_new.search(text)
            if not m:
                break
            name = m.group(1) or m.group(2)
            num_args = int(m.group(3)) if m.group(3) else 0
            open_brace_idx = m.end() - 1
            body, end_idx = cls.extract_braced_group(text, open_brace_idx)
            macros[name] = {"args": num_args, "body": body}
            text = text[:m.start()] + text[end_idx:]

        pattern_def = re.compile(r'\\def\s*\\([a-zA-Z]+)((?:#\d+)*)\s*\{')
        while True:
            m = pattern_def.search(text)
            if not m:
                break
            name = m.group(1)
            params_str = m.group(2) or ""
            num_args = len(re.findall(r'#\d', params_str))
            open_brace_idx = m.end() - 1
            body, end_idx = cls.extract_braced_group(text, open_brace_idx)
            macros[name] = {"args": num_args, "body": body}
            text = text[:m.start()] + text[end_idx:]

        return text, macros

    @classmethod
    def expand_macros(cls, text: str, macros: Dict[str, Dict[str, Any]], max_passes: int = 5) -> str:
        if not macros:
            return text

        sorted_names = sorted(macros.keys(), key=len, reverse=True)
        for _ in range(max_passes):
            changed = False
            for name in sorted_names:
                info = macros[name]
                num_args = info["args"]
                body = info["body"]

                if num_args == 0:
                    pattern_bs = re.compile(r'\\' + re.escape(name) + r'\\(?:\s+|$)')
                    if pattern_bs.search(text):
                        changed = True
                        text = pattern_bs.sub(lambda m: body + " ", text)
                    pattern = re.compile(r'\\' + re.escape(name) + r'(?:\{\}|(?![a-zA-Z]))')
                    if pattern.search(text):
                        changed = True
                        text = pattern.sub(lambda m: body, text)
                else:
                    call_pattern = re.compile(r'\\' + re.escape(name) + r'\s*\{')
                    while True:
                        m = call_pattern.search(text)
                        if not m:
                            break
                        changed = True
                        curr_idx = m.end() - 1
                        args = []
                        valid = True
                        for _ in range(num_args):
                            if curr_idx < len(text) and text[curr_idx] == '{':
                                arg_val, next_idx = cls.extract_braced_group(text, curr_idx)
                                args.append(arg_val)
                                m_ws = re.match(r'\s*', text[next_idx:])
                                curr_idx = next_idx + (m_ws.end() if m_ws else 0)
                            else:
                                valid = False
                                break
                        if valid:
                            sub_body = body
                            for arg_idx, arg_val in enumerate(args, 1):
                                sub_body = sub_body.replace(f"#{arg_idx}", arg_val)
                            text = text[:m.start()] + sub_body + text[curr_idx:]
                        else:
                            break
            if not changed:
                break

        text = re.sub(r'\\xspace\s*([,.:;!?\'"\)\}\]])', r'\1', text)
        text = re.sub(r'\\xspace\b\s*', ' ', text)
        return text


class LatexToMarkdownConverter:
    """Convertisseur de documents LaTeX vers Markdown GitHub Flavored avec support KaTeX."""

    def __init__(
        self,
        root_tex_path: Optional[Path] = None,
        bib_parser: Optional[BibTexParser] = None,
        base_dir: Optional[Path] = None,
        output_path: Optional[Path] = None,
        raw_content: Optional[str] = None,
        brain_dir: Optional[Path] = None
    ):
        self.root_path = root_tex_path.resolve() if root_tex_path else None
        self.root_dir = base_dir.resolve() if base_dir else (self.root_path.parent if self.root_path else Path.cwd())
        self.bib_parser = bib_parser or BibTexParser()
        self.output_path = output_path.resolve() if output_path else None
        self.paper_slug = self.output_path.stem if self.output_path else ""
        self.raw_content = raw_content
        self.cited_keys: List[str] = []
        self.title: str = ""
        self.authors: str = ""
        self.keywords: str = ""
        self.abstract: str = ""
        self.metadata: Dict[str, str] = {}
        self.macros: Dict[str, Dict[str, Any]] = {}
        self.brain_dir: Optional[Path] = brain_dir.resolve() if brain_dir else None

    @classmethod
    def convert_text(
        cls,
        text: str,
        base_dir: Optional[Path] = None,
        bib_parser: Optional[BibTexParser] = None,
        brain_dir: Optional[Path] = None
    ) -> str:
        """Convertit directement une chaîne LaTeX en Markdown propre."""
        if not text or not text.strip():
            return ""
        converter = cls(
            root_tex_path=None,
            bib_parser=bib_parser,
            base_dir=base_dir,
            raw_content=text,
            brain_dir=brain_dir
        )
        return converter.convert()

    def resolve_inputs(self, tex_file: Path, visited: Optional[Set[Path]] = None) -> str:
        """Résout récursivement les \\input, \\include, \\subfile, \\import avec détection de cycles."""
        if visited is None:
            visited = set()

        real_path = tex_file.resolve()
        if real_path in visited:
            return ""
        visited.add(real_path)

        if not real_path.exists():
            if real_path.with_suffix('.tex').exists():
                real_path = real_path.with_suffix('.tex')
            else:
                return f"\n<!-- Fichier introuvable: {tex_file.name} -->\n"

        try:
            content = real_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

        current_dir = real_path.parent

        def replace_input(match):
            rel_file = match.group(1).strip().strip('"{}\'')
            if not rel_file.endswith('.tex') and '.' not in os.path.basename(rel_file):
                rel_file += '.tex'

            target_path = current_dir / rel_file
            if not target_path.exists():
                target_path = self.root_dir / rel_file

            return self.resolve_inputs(target_path, visited)

        input_pattern = re.compile(r'\\(?:input|include|subfile|import)\s*\{([^}]+)\}')
        return input_pattern.sub(replace_input, content)

    def strip_comments(self, text: str) -> str:
        """Supprime les commentaires % tout en préservant \\%."""
        lines = []
        for line in text.splitlines():
            escaped_marker = "___ESCAPED_PERCENT___"
            temp_line = line.replace(r'\%', escaped_marker)
            if '%' in temp_line:
                temp_line = temp_line.split('%', 1)[0]
            temp_line = temp_line.replace(escaped_marker, r'%')
            lines.append(temp_line)
        return "\n".join(lines)

    def extract_metadata(self, text: str) -> str:
        """Extrait le titre, les auteurs, les keywords et prépare le corps de texte."""
        title_match = re.search(r'\\title\s*\{((?:[^{}]|{[^{}]*})*)\}', text, re.DOTALL)
        if title_match:
            self.title = self.clean_inline_formatting(title_match.group(1).strip())

        author_match = re.search(r'\\author\s*\{((?:[^{}]|{[^{}]*})*)\}', text, re.DOTALL)
        if author_match:
            raw_author = author_match.group(1).strip()
            raw_author = re.sub(r'\\and\b', ' & ', raw_author)
            raw_author = re.sub(r'\\thanks\{.*?\}', '', raw_author, flags=re.DOTALL)
            raw_author = re.sub(r'\\inst\{[^}]*\}', '', raw_author)
            raw_author = re.sub(r'\\orcid(?:ID)?\{[^}]*\}', '', raw_author)
            raw_author = re.sub(r'\\email\{[^}]*\}', '', raw_author)
            clean_author = self.clean_inline_formatting(raw_author).strip()
            if re.search(r'anonymous', clean_author, re.IGNORECASE):
                self.authors = "Anonymous Submission"
            else:
                self.authors = clean_author

        kw_match = re.search(r'\\keywords\s*\{', text)
        if kw_match:
            open_brace_idx = kw_match.end() - 1
            raw_kw, _ = LatexMacroEngine.extract_braced_group(text, open_brace_idx)
            if raw_kw:
                cleaned_kw = re.sub(r'\s+', ' ', raw_kw).strip()
                cleaned_kw = re.sub(r'\\and\b', ', ', cleaned_kw)
                cleaned_kw = self.clean_inline_formatting(cleaned_kw)
                items = [k.strip().strip(';') for k in re.split(r'\s*[,;]\s*', cleaned_kw) if k.strip().strip(';')]
                if items:
                    self.keywords = ", ".join(items)

        abstract_match = re.search(r'\\begin\{abstract\}(.*?)\\end\{abstract\}', text, re.DOTALL)
        if abstract_match:
            self.abstract = self.clean_inline_formatting(abstract_match.group(1).strip())

        doc_match = re.search(r'\\begin\{document\}(.*?)\\end\{document\}', text, re.DOTALL)
        body = doc_match.group(1) if doc_match else text
        body = re.sub(r'\\maketitle', '', body)
        body = re.sub(r'\\(?:bibliographystyle|bibliography)(?:\{[^}]*\})?', '', body)
        return body

    def convert_headings(self, text: str) -> str:
        """Convertit les titres LaTeX en titres Markdown avec gestion robuste des accolades imbriquées."""
        heading_types = [
            (r'\\section\*?', '##'),
            (r'\\subsection\*?', '###'),
            (r'\\subsubsection\*?', '####'),
            (r'\\paragraph\*?', '#####'),
            (r'\\subparagraph\*?', '######'),
        ]
        for cmd_pattern, md_prefix in heading_types:
            pattern = re.compile(cmd_pattern + r'\s*\{')
            while True:
                m = pattern.search(text)
                if not m:
                    break
                open_brace_idx = m.end() - 1
                inner, end_idx = LatexMacroEngine.extract_braced_group(text, open_brace_idx)
                # Nettoyer l'intérieur du titre pour qu'il soit propre
                clean_title = inner.strip()
                for _ in range(5):
                    clean_title = re.sub(r'\\(?:textsf|textsc|textup|textmd|textrm|textnormal|text|underline)\{((?:[^{}]|{[^{}]*})*)\}', r'\1', clean_title)
                    clean_title = re.sub(r'\\textbf\{((?:[^{}]|{[^{}]*})*)\}', r'\1', clean_title)
                    clean_title = re.sub(r'\\(?:textit|emph|textsl)\{((?:[^{}]|{[^{}]*})*)\}', r'\1', clean_title)
                    clean_title = re.sub(r'\\texttt\{((?:[^{}]|{[^{}]*})*)\}', r'`\1`', clean_title)
                clean_title = self.clean_layout_formatting(clean_title)
                clean_title = self.clean_inline_formatting(clean_title).strip()
                clean_title = re.sub(r'\\label\{[^}]+\}', '', clean_title).strip()
                clean_title = re.sub(r'^\*\*(.*?)\*\*$', r'\1', clean_title).strip()
                clean_title = re.sub(r'\s+', ' ', clean_title)
                text = text[:m.start()] + f"\n\n{md_prefix} {clean_title}\n\n" + text[end_idx:]

        text = re.sub(r'\\label\{[^}]+\}', '', text)
        return text

    @staticmethod
    def fix_xml_tex_tags(text: str) -> str:
        """Gère proprement les balises XML/TeX comme <reasoning> ou <tag>."""
        def repl_math_xml(m):
            inner = m.group(1).strip()
            inner = re.sub(r'\\text\{([^}]+)\}', r'\1', inner)
            inner = inner.replace(r'\_', '_').replace('\\', '').strip()
            if re.match(r'^[a-zA-Z][a-zA-Z0-9_-]*$', inner):
                return f"<{inner}>"
            return f"$\\langle \\text{{{inner}}} \\rangle$"

        text = re.sub(r'\$\s*\\langle\s*(.*?)\s*\\rangle\s*\$', repl_math_xml, text)

        def repl_fused_langle(m):
            tag = m.group(1).strip()
            tag = re.sub(r'\\text\{([^}]+)\}', r'\1', tag)
            tag = tag.replace(r'\_', '_').replace('\\', '').strip()
            return f"<{tag}>"

        text = re.sub(r'\\langle\s*(?:\\text\{)?([a-zA-Z][a-zA-Z0-9_\\-]*?)\}?\s*\\rangle', repl_fused_langle, text)
        text = re.sub(r'\\langle([a-zA-Z][a-zA-Z0-9_\\-]*?)\\rangle', repl_fused_langle, text)
        return text

    @classmethod
    def mask_math(cls, text: str) -> Tuple[str, Dict[str, str]]:
        """Masque de manière robuste et étanche tous les blocs KaTeX ($$...$$ et $...$)."""
        math_map: Dict[str, str] = {}

        def repl_display(m):
            token = f"___MATH_BLOCK_D_{len(math_map)}___"
            math_map[token] = m.group(0)
            return token

        def repl_inline(m):
            token = f"___MATH_BLOCK_I_{len(math_map)}___"
            math_map[token] = m.group(0)
            return token

        text = re.sub(r'\$\$.*?\$\$', repl_display, text, flags=re.DOTALL)
        text = re.sub(r'(?<!\$)\$(?!\$)(?:\\.|[^\$\\\n])+(?<!\$)\$(?!\$)', repl_inline, text)
        return text, math_map

    @classmethod
    def unmask_math(cls, text: str, math_map: Dict[str, str]) -> str:
        """Restaure les blocs KaTeX masqués en garantissant l'intégrité des $$."""
        for token, math_content in math_map.items():
            text = text.replace(token, math_content)
        return text

    def convert_math(self, text: str) -> str:
        """Convertit les équations LaTeX vers KaTeX Markdown avec doubles dollars équilibrés."""
        text = self.fix_xml_tex_tags(text)

        def replace_display_env(match):
            env_name = match.group(1)
            content = match.group(2).strip()
            content = re.sub(r'\\label\{[^}]+\}', '', content).strip()
            if 'align' in env_name:
                return f"\n\n$$\n\\begin{{aligned}}\n{content}\n\\end{{aligned}}\n$$\n\n"
            return f"\n\n$$\n{content}\n$$\n\n"

        text = re.sub(
            r'\\begin\{(equation|equation\*|align|align\*|gather|gather\*|multline|multline\*)\}(.*?)\\end\{\1\}',
            replace_display_env,
            text,
            flags=re.DOTALL
        )
        text = re.sub(r'\\\[(.*?)\\\]', lambda m: f"\n\n$$\n{re.sub(r'\\\\label\\{[^}]+\\}', '', m.group(1)).strip()}\n$$\n\n", text, flags=re.DOTALL)
        text = re.sub(r'\\\((.*?)\\\)', r'$\1$', text, flags=re.DOTALL)

        # Normalisation des blocs $$ déjà existants pour garantir doubles dollars sur leurs propres lignes
        def normalize_dollar_blocks(m):
            c = m.group(1).strip()
            c = re.sub(r'\\label\{[^}]+\}', '', c).strip()
            return f"\n\n$$\n{c}\n$$\n\n"

        text = re.sub(r'\$\$(.*?)\$\$', normalize_dollar_blocks, text, flags=re.DOTALL)
        return text

    def convert_citations(self, text: str) -> str:
        """Convertit les citations avec le parser BibTeX."""
        def replace_cite(match):
            cmd = match.group(1)
            keys_str = match.group(2)
            keys = [k.strip() for k in keys_str.split(',') if k.strip()]
            for k in keys:
                if k not in self.cited_keys:
                    self.cited_keys.append(k)

            is_citet = (cmd == 'citet' or cmd == 'citeauthor')
            formatted = [self.bib_parser.format_citation(k, citet=is_citet) for k in keys]
            if is_citet:
                return " ".join(formatted)
            else:
                inner = "; ".join([f.strip("[]") for f in formatted])
                return f"[{inner}]"

        text = re.sub(r'\\(cite|citep|citet|citealt|citeauthor|citeyear|autocite)\s*\{([^}]+)\}', replace_cite, text)
        return text

    def resolve_image_path(self, raw_path: str) -> str:
        """
        Résout le fichier image, convertit les PDF vectoriels en PNG 300 DPI via PyMuPDF si disponible,
        et retourne le nom de fichier sécurisé.
        """
        clean_path = raw_path.strip().strip('"{}\'')
        if clean_path.startswith("./"):
            clean_path = clean_path[2:]

        p = Path(clean_path)
        base_dirs = [
            self.root_dir,
            self.root_dir / "figures",
            self.root_dir / "assets",
        ]
        if self.root_path:
            base_dirs.extend([
                self.root_path.parent,
                self.root_path.parent / "figures",
                self.root_path.parent / "assets",
            ])

        found_target: Optional[Path] = None
        check_exts = [".png", ".jpg", ".jpeg", ".webp", ".svg", ".pdf"]

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
            return Path(clean_path).name

        # Rastérisation PyMuPDF si PDF
        if found_target.suffix.lower() == ".pdf":
            try:
                import pymupdf
                doc = pymupdf.open(str(found_target))
                if len(doc) > 0:
                    page = doc[0]
                    pix = page.get_pixmap(dpi=300)
                    raster_png = found_target.with_suffix(".png")
                    pix.save(str(raster_png))
                    if raster_png.exists():
                        found_target = raster_png
            except Exception:
                pass

        safe_name = found_target.name.replace(" ", "_")
        if self.brain_dir and self.brain_dir.is_dir():
            try:
                dest_file = self.brain_dir / safe_name
                if found_target.resolve() != dest_file.resolve():
                    shutil.copy2(found_target, dest_file)
            except Exception:
                pass
        return safe_name

    @staticmethod
    def replace_shortstack(text: str) -> str:
        """Intercepte \\shortstack{...} et convertit en <br>."""
        if r'\shortstack' not in text:
            return text
        pattern = re.compile(r'\\shortstack(?:\s*\[[^\]]*\])?\s*\{')
        pos = 0
        res = []
        while True:
            m = pattern.search(text, pos)
            if not m:
                res.append(text[pos:])
                break
            res.append(text[pos:m.start()])
            inner, end_idx = LatexMacroEngine.extract_braced_group(text, m.end() - 1)
            lines = re.split(r'\\\\(?:\s*\[[^\]]*\])?', inner)
            res.append("<br>".join(l.strip() for l in lines))
            pos = end_idx
        return "".join(res)

    def convert_tables(self, text: str) -> str:
        """Convertit les tableaux LaTeX (tabular, tabularx, booktabs) en tableaux Markdown natifs."""
        def expand_cell(cell: str) -> list:
            m = re.search(r'\\multicolumn\s*\{(\d+)\}\s*\{[^{}]*\}\s*\{', cell)
            if not m:
                m_row = re.search(r'\\multirow\s*\{(\d+)\}\s*\{[^{}]*\}\s*\{', cell)
                if m_row:
                    content, end_idx = LatexMacroEngine.extract_braced_group(cell, m_row.end() - 1)
                    before = cell[:m_row.start()].strip()
                    after = cell[end_idx:].strip()
                    return [f"{before} {content} {after}".strip()]
                return [cell]
            n_cols = int(m.group(1))
            open_idx = m.end() - 1
            content, end_idx = LatexMacroEngine.extract_braced_group(cell, open_idx)
            before = cell[:m.start()].strip()
            after = cell[end_idx:].strip()
            res = f"{before} {content} {after}".strip()
            return [res] + [""] * (n_cols - 1)

        def parse_single_tabular(raw_tab: str, caption: str = "") -> str:
            clean = re.sub(r'\\(?:toprule|midrule|bottomrule|hline|centering|small|footnotesize|scriptsize|label\{[^}]+\})', '', raw_tab)
            clean = re.sub(r'\\addlinespace(?:\s*\[[^\]]*\])?', '', clean)
            clean = re.sub(r'\\(?:rowcolor|columncolor|cellcolor|arrayrulecolor)(?:\[[^\]]*\])?(?:\{[^{}]*\}|\s+[a-zA-Z0-9!_]+)?', '', clean)
            clean = re.sub(r'\\texttimes\b', '×', clean)
            clean = re.sub(r'\\checkmark\b', '✓', clean)
            clean = re.sub(r'\\ding\{51\}', '✓', clean)
            clean = re.sub(r'\\ding\{55\}', '✗', clean)
            clean = self.replace_shortstack(clean)
            amp_marker = "___ESC_AMP___"
            clean = clean.replace(r'\&', amp_marker)

            row_splits = re.split(r'\\\\(?:\s*\[[^\]]*\])?', clean)
            table_rows = []
            max_cols = 0
            for r in row_splits:
                r = r.strip()
                if not r:
                    continue
                cells = [c.replace(amp_marker, r'\&') for c in r.split('&')]
                expanded = []
                for c in cells:
                    expanded.extend(expand_cell(c.strip()))
                if any(expanded):
                    table_rows.append(expanded)
                    if len(expanded) > max_cols:
                        max_cols = len(expanded)

            if not table_rows or max_cols == 0:
                return ""

            normalized_rows = []
            for row in table_rows:
                if len(row) < max_cols:
                    row.extend([""] * (max_cols - len(row)))
                cleaned_row = []
                for cell in row:
                    c = self.clean_inline_formatting(cell.strip())
                    c = c.replace('|', '\\|').replace('\n', ' ')
                    cleaned_row.append(c)
                normalized_rows.append(cleaned_row)

            md_lines = []
            if caption:
                md_lines.append(f"> [!NOTE] **📊 Table : {self.clean_inline_formatting(caption)}**\n")

            header = normalized_rows[0]
            md_lines.append("| " + " | ".join(header) + " |")
            md_lines.append("| " + " | ".join([":---"] * max_cols) + " |")
            for row in normalized_rows[1:]:
                md_lines.append("| " + " | ".join(row) + " |")

            return "\n\n" + "\n".join(md_lines) + "\n\n"

        def parse_table_env(match):
            full_table = match.group(0)
            tab_pattern = re.compile(r'\\begin\{(?:tabular|tabularx)\}(?:\s*(?:\[[^\]]*\]|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}))+\s*(.*?)\\end\{(?:tabular|tabularx)\}', re.DOTALL)
            tabular_matches = list(tab_pattern.finditer(full_table))
            if not tabular_matches:
                return full_table

            converted_parts = []
            for tm in tabular_matches:
                cap_m = re.search(r'\\caption\s*\{', full_table)
                caption = ""
                if cap_m:
                    caption, _ = LatexMacroEngine.extract_braced_group(full_table, cap_m.end() - 1)
                md_tab = parse_single_tabular(tm.group(1), caption.strip())
                converted_parts.append(md_tab)
            return "\n\n" + "\n\n".join(converted_parts) + "\n\n"

        table_pattern = re.compile(r'\\begin\{table\*?\}.*?\\end\{table\*?\}', re.DOTALL)
        text = table_pattern.sub(parse_table_env, text)

        isolated_tabular = re.compile(r'\\begin\{(?:tabular|tabularx)\}(?:\s*(?:\[[^\]]*\]|\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}))+\s*(.*?)\\end\{(?:tabular|tabularx)\}', re.DOTALL)
        text = isolated_tabular.sub(lambda m: parse_single_tabular(m.group(1), ""), text)
        return text

    def convert_figures(self, text: str) -> str:
        """Convertit les figures et includegraphics."""
        def parse_figure(match):
            full_fig = match.group(0)
            cap_match = re.search(r'\\caption\s*\{', full_fig)
            caption = ""
            if cap_match:
                cap_content, _ = LatexMacroEngine.extract_braced_group(full_fig, cap_match.end() - 1)
                caption = cap_content.strip()

            clean_cap = self.clean_inline_formatting(caption) if caption else "Figure"

            img_matches = list(re.finditer(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}', full_fig))
            if img_matches:
                img_blocks = []
                for im in img_matches:
                    raw_p = im.group(1).strip().strip('"{}\'')
                    safe_name = self.resolve_image_path(raw_p)
                    if self.brain_dir and self.brain_dir.is_dir():
                        b_posix = self.brain_dir.resolve().as_posix().lstrip('/')
                        img_blocks.append(f"![{clean_cap}](file:///{b_posix}/{safe_name})")
                    else:
                        img_blocks.append(f"![{clean_cap}]({safe_name})")
                imgs_str = "\n\n".join(img_blocks)
                return f"\n\n> [!NOTE] **🖼️ Figure : {clean_cap}**\n\n{imgs_str}\n\n"

            return f"\n\n> [!NOTE] **🖼️ Figure : {clean_cap}**\n\n"

        text = re.sub(r'\\begin\{figure\*?\}.*?\\end\{figure\*?\}', parse_figure, text, flags=re.DOTALL)

        def repl_isolated_img(m):
            raw_target = m.group(1).strip().strip('"{}\'')
            safe_name = self.resolve_image_path(raw_target)
            alt = Path(raw_target).stem.replace('_', ' ')
            if self.brain_dir and self.brain_dir.is_dir():
                b_posix = self.brain_dir.resolve().as_posix().lstrip('/')
                return f"\n\n![{alt}](file:///{b_posix}/{safe_name})\n\n"
            return f"\n\n![{alt}]({safe_name})\n\n"

        text = re.sub(
            r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}',
            repl_isolated_img,
            text
        )
        return text

    def convert_lists(self, text: str) -> str:
        """Convertit itemize et enumerate en listes Markdown."""
        def parse_list(match):
            env_type = match.group(1)
            body = match.group(2)
            m_first = re.search(r'\\item(?![a-zA-Z])', body)
            if m_first:
                body = body[m_first.start():]
            items = re.split(r'\\item(?![a-zA-Z])(?:\s*\[[^\]]*\])?\s*', body)
            md_items = []
            idx = 1
            for it in items:
                it = it.strip()
                if not it:
                    continue
                clean_it = " ".join([l.strip() for l in it.splitlines() if l.strip()])
                if env_type == 'enumerate':
                    md_items.append(f"{idx}. {clean_it}")
                    idx += 1
                else:
                    md_items.append(f"- {clean_it}")
            return "\n\n" + "\n".join(md_items) + "\n\n"

        for _ in range(3):
            text = re.sub(r'\\begin\{(itemize|enumerate)\}(?:\s*\[[^\]]*\])?(.*?)\\end\{\1\}', parse_list, text, flags=re.DOTALL)
        return text

    @classmethod
    def unwrap_boxes(cls, text: str) -> str:
        """
        Déballe récursivement les boîtes de mise en page LaTeX :
        \\fcolorbox, \\colorbox, \\parbox, \\raisebox, \\makebox, \\framebox, \\scalebox, \\resizebox.
        Supporte les arguments avec ou sans accolades pour les couleurs et les dimensions.
        """
        def extract_arg(s: str, start: int) -> Tuple[Optional[str], int]:
            """Extrait un argument : soit {groupe}, soit un mot simple sans accolades."""
            m_space = re.match(r'\s*', s[start:])
            curr = start + (m_space.end() if m_space else 0)
            if curr >= len(s):
                return None, curr
            if s[curr] == '{':
                val, next_i = LatexMacroEngine.extract_braced_group(s, curr)
                return val, next_i
            # Mot simple sans accolades (ex: acmbluebg ou white ou black)
            m_word = re.match(r'([^\s{}%\\]+)', s[curr:])
            if m_word:
                return m_word.group(1), curr + m_word.end()
            return None, curr

        for _ in range(4):
            prev_text = text

            # 1. \fcolorbox[model]{frame}{bg}{content} -> content (avec ou sans accolades sur frame/bg)
            pattern_fcolorbox = re.compile(r'\\fcolorbox(?:\s*\[[^\]]*\])?\s*')
            pos = 0
            while True:
                m = pattern_fcolorbox.search(text, pos)
                if not m:
                    break
                idx = m.end()

                # arg 1 : frame
                arg1, idx = extract_arg(text, idx)
                if arg1 is None:
                    pos = m.end()
                    continue

                # arg 2 : bg
                arg2, idx = extract_arg(text, idx)
                if arg2 is None:
                    pos = m.end()
                    continue

                # arg 3 : body
                m_space = re.match(r'\s*', text[idx:])
                idx = idx + (m_space.end() if m_space else 0)
                if idx >= len(text) or text[idx] != '{':
                    pos = m.end()
                    continue

                body, end_idx = LatexMacroEngine.extract_braced_group(text, idx)
                text = text[:m.start()] + f"\n\n{body}\n\n" + text[end_idx:]
                pos = m.start()

            # 2. \colorbox[model]{bg}{content} -> content (avec ou sans accolades sur bg)
            pattern_colorbox = re.compile(r'\\colorbox(?:\s*\[[^\]]*\])?\s*')
            pos = 0
            while True:
                m = pattern_colorbox.search(text, pos)
                if not m:
                    break
                idx = m.end()

                arg1, idx = extract_arg(text, idx)
                if arg1 is None:
                    pos = m.end()
                    continue

                m_space = re.match(r'\s*', text[idx:])
                idx = idx + (m_space.end() if m_space else 0)
                if idx >= len(text) or text[idx] != '{':
                    pos = m.end()
                    continue

                body, end_idx = LatexMacroEngine.extract_braced_group(text, idx)
                text = text[:m.start()] + f"\n\n{body}\n\n" + text[end_idx:]
                pos = m.start()

            # 3. \parbox[pos][height][inner-pos]{width}{content} -> content
            pattern_parbox = re.compile(r'\\parbox(?:\s*\[[^\]]*\])*\s*')
            pos = 0
            while True:
                m = pattern_parbox.search(text, pos)
                if not m:
                    break
                idx = m.end()
                m_space = re.match(r'\s*', text[idx:])
                idx = idx + (m_space.end() if m_space else 0)
                if idx >= len(text):
                    pos = m.end()
                    continue

                # Consommation de l'argument width
                if text[idx] == '{':
                    _, idx = LatexMacroEngine.extract_braced_group(text, idx)
                elif text[idx:].startswith(r'\dimexpr'):
                    m_dim = re.search(r'\\dimexpr.*?(?:\\relax|(?=\{))', text[idx:])
                    if m_dim:
                        idx = idx + m_dim.end()
                    else:
                        pos = m.end()
                        continue
                elif re.match(r'\\(?:linewidth|textwidth|columnwidth)[^\s{]*', text[idx:]):
                    m_dim = re.match(r'\\(?:linewidth|textwidth|columnwidth)[^\s{]*', text[idx:])
                    idx = idx + m_dim.end()
                else:
                    pos = m.end()
                    continue

                # Consommation du body {content}
                m_space = re.match(r'\s*', text[idx:])
                idx = idx + (m_space.end() if m_space else 0)
                if idx >= len(text) or text[idx] != '{':
                    pos = m.end()
                    continue

                body, end_idx = LatexMacroEngine.extract_braced_group(text, idx)
                text = text[:m.start()] + f"\n\n{body}\n\n" + text[end_idx:]
                pos = m.start()

            # 4. \raisebox{lift}[height][depth]{content} -> content
            pattern_raisebox = re.compile(r'\\raisebox\s*\{')
            pos = 0
            while True:
                m = pattern_raisebox.search(text, pos)
                if not m:
                    break
                idx = m.end() - 1
                _, idx = LatexMacroEngine.extract_braced_group(text, idx)
                while idx < len(text) and text[idx] == '[':
                    close_bracket = text.find(']', idx)
                    if close_bracket == -1:
                        break
                    idx = close_bracket + 1
                m_ws = re.match(r'\s*', text[idx:])
                idx = idx + (m_ws.end() if m_ws else 0)
                if idx >= len(text) or text[idx] != '{':
                    pos = m.end()
                    continue
                body, end_idx = LatexMacroEngine.extract_braced_group(text, idx)
                text = text[:m.start()] + f" {body} " + text[end_idx:]
                pos = m.start()

            # 5. \makebox / \framebox
            pattern_box = re.compile(r'\\(?:makebox|framebox)(?:\s*\[[^\]]*\])*\s*\{')
            pos = 0
            while True:
                m = pattern_box.search(text, pos)
                if not m:
                    break
                idx = m.end() - 1
                body, end_idx = LatexMacroEngine.extract_braced_group(text, idx)
                text = text[:m.start()] + f" {body} " + text[end_idx:]
                pos = m.start()

            # 6. \scalebox / \resizebox
            pattern_scalebox = re.compile(r'\\scalebox\s*\{')
            pos = 0
            while True:
                m = pattern_scalebox.search(text, pos)
                if not m:
                    break
                idx = m.end() - 1
                _, idx = LatexMacroEngine.extract_braced_group(text, idx)
                while idx < len(text) and text[idx] == '[':
                    close_bracket = text.find(']', idx)
                    if close_bracket == -1:
                        break
                    idx = close_bracket + 1
                m_ws = re.match(r'\s*', text[idx:])
                idx = idx + (m_ws.end() if m_ws else 0)
                if idx >= len(text) or text[idx] != '{':
                    pos = m.end()
                    continue
                body, end_idx = LatexMacroEngine.extract_braced_group(text, idx)
                text = text[:m.start()] + f" {body} " + text[end_idx:]
                pos = m.start()

            pattern_resizebox = re.compile(r'\\resizebox\*?\s*\{')
            pos = 0
            while True:
                m = pattern_resizebox.search(text, pos)
                if not m:
                    break
                idx = m.end() - 1
                _, idx = LatexMacroEngine.extract_braced_group(text, idx)
                m_ws = re.match(r'\s*', text[idx:])
                idx = idx + (m_ws.end() if m_ws else 0)
                if idx >= len(text) or text[idx] != '{':
                    pos = m.end()
                    continue
                _, idx = LatexMacroEngine.extract_braced_group(text, idx)
                m_ws = re.match(r'\s*', text[idx:])
                idx = idx + (m_ws.end() if m_ws else 0)
                if idx >= len(text) or text[idx] != '{':
                    pos = m.end()
                    continue
                body, end_idx = LatexMacroEngine.extract_braced_group(text, idx)
                text = text[:m.start()] + f" {body} " + text[end_idx:]
                pos = m.start()

            if text == prev_text:
                break

        # Élimination systématique des résidus internes de dimensions et règles
        text = re.sub(r'\\dimexpr\b[^{}]*(?:\\relax)?', '', text)
        text = re.sub(r'\\relax\b', '', text)
        text = re.sub(r'\\(?:linewidth|textwidth|columnwidth|paperwidth|paperheight)\b', '', text)
        text = re.sub(r'\\(?:fboxsep|fboxrule)\b', '', text)
        text = re.sub(r'\\vrule(?:\s*(?:width|height|depth)\s*[\d\.]+\s*[a-zA-Z%]+)*', '', text)
        return text

    def convert_environments(self, text: str) -> str:
        """Convertit minipage, abstract, quote, tcolorbox, center, etc."""
        text = self.unwrap_boxes(text)

        for _ in range(5):
            text = re.sub(
                r'\\begin\{(?:minipage|boxedminipage)\}(?:\[[^\]]*\])?(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})+\s*(.*?)\s*\\end\{(?:minipage|boxedminipage)\}%?',
                r'\n\n\1\n\n',
                text,
                flags=re.DOTALL
            )

        for env in ('center', 'flushleft', 'flushright', 'tcolorbox', 'shaded', 'framed', 'mdframed'):
            text = re.sub(rf'\\begin\{{{env}\}}(?:\[[^\]]*\])?\s*(.*?)\s*\\end\{{{env}\}}', r'\n\n\1\n\n', text, flags=re.DOTALL)

        env_names = r'(?:abstract|quote|quotation|verse)'
        def parse_quote(m):
            lines = m.group(2).strip().splitlines()
            return "\n\n" + "\n".join([f"> {l}" if l.strip() else ">" for l in lines]) + "\n\n"

        for _ in range(2):
            text = re.sub(rf'\\begin\{{({env_names})\}}(?:\[[^\]]*\])?(.*?)\\end\{{\1\}}', parse_quote, text, flags=re.DOTALL)
        return text

    def clean_layout_formatting(self, text: str) -> str:
        """Filtre et nettoie les commandes et balises de mise en page LaTeX brutes."""
        text = self.unwrap_boxes(text)

        # 1. Environnements de mise en page (minipage, center, flushleft, flushright)
        for _ in range(5):
            text = re.sub(
                r'\\begin\{(?:minipage|boxedminipage)\}(?:\[[^\]]*\])?(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})+\s*(.*?)\s*\\end\{(?:minipage|boxedminipage)\}%?',
                r'\n\n\1\n\n',
                text,
                flags=re.DOTALL
            )
        for env in ('center', 'flushleft', 'flushright', 'tcolorbox', 'shaded', 'framed', 'mdframed'):
            text = re.sub(rf'\\begin\{{{env}\}}(?:\[[^\]]*\])?\s*(.*?)\s*\\end\{{{env}\}}', r'\n\n\1\n\n', text, flags=re.DOTALL)

        # 2. Polices et tailles de police
        text = re.sub(r'\\fontsize\{[^{}]*\}\{[^{}]*\}\s*(?:\\selectfont)?', '', text)
        text = re.sub(r'\\selectfont\b', '', text)
        text = re.sub(r'\\(?:small|footnotesize|scriptsize|normalsize|large|Large|LARGE|huge|Huge)\b', '', text)
        text = re.sub(r'\\(?:normalfont|bfseries|itshape|slshape|scshape|sffamily|ttfamily|rmfamily)\b', '', text)

        # 3. Espacements verticaux/horizontaux et règles de séparation
        text = re.sub(r'\\vspace\*?\{[^{}]*\}', '\n\n', text)
        text = re.sub(r'\\hspace\*?\{[^{}]*\}', ' ', text)
        text = re.sub(r'\\(?:smallskip|medskip|bigskip)\b', '\n\n', text)
        text = re.sub(r'\\(?:pagebreak|clearpage|newpage|vfill|hfill|noindent|centering|raggedleft|raggedright|frenchspacing)\b', ' ', text)
        text = re.sub(r'\\needspace(?:\{[^{}]*\}|\[[^\]]*\])?', '', text)
        text = re.sub(r'\\(?:setlength|addtolength)\{[^{}]*\}\{[^{}]*\}', '', text)
        text = re.sub(r'\\renewcommand\{\\arraystretch\}\{[^{}]*\}', '', text)

        # 4. Règles, boîtes, couleurs et dimensions
        text = re.sub(r'\\hrule\b(?:[ \t]*(?:height|width|depth)[ \t]+[\d\.]+\s*[a-zA-Z%]+)*', '\n\n---\n\n', text)
        text = re.sub(r'\\rule(?:\[[^\]]*\])?\{[^{}]*\}\{[^{}]*\}', '', text)
        text = re.sub(r'\\vrule\b(?:\s*(?:width|height|depth)\s*[\d\.]+\s*[a-zA-Z%]+)*', '', text)
        text = re.sub(r'\\dimexpr\b[^{}]*(?:\\relax)?', '', text)
        text = re.sub(r'\\relax\b', '', text)
        text = re.sub(r'\\(?:linewidth|textwidth|columnwidth|paperwidth|paperheight)\b', '', text)
        text = re.sub(r'\\(?:fboxsep|fboxrule)\b', '', text)
        text = re.sub(r'\\definecolor\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}', '', text)
        text = re.sub(r'\\(?:color|rowcolor|columncolor|cellcolor|arrayrulecolor)(?:\[[^\]]*\])?(?:\{[^{}]*\}|\s+[a-zA-Z0-9!_]+)?', '', text)
        text = re.sub(r'\\(?:toprule|midrule|bottomrule|hline|addlinespace|cmidrule(?:\[[^\]]*\])?\{[^}]*\})', '', text)
        text = re.sub(r'\\textcolor(?:\[[^\]]*\])?\{[^{}]*\}\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)

        # 5. Configuration et métadonnées parasites
        text = re.sub(r'\\titleformat\*?\{[^{}]*\}(?:\[[^\]]*\])?\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}(?:\[[^\]]*\])?', '', text)
        text = re.sub(r'\\titlespacing\*?\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}', '', text)
        text = re.sub(r'\\setlist(?:\[[^\]]*\])?\{[^{}]*\}', '', text)
        text = re.sub(r'\\hypersetup\{((?:[^{}]|{[^{}]*})*)\}', '', text, flags=re.DOTALL)
        text = re.sub(r'\\the(?:sub)*section\b', '', text)
        text = re.sub(r'\\settopmatter\{[^}]*\}', '', text)
        text = re.sub(r'\\(?:acmConference|acmBooktitle|acmYear|copyrightyear|acmDOI|acmISBN|acmPrice|acmSubmissionID)(?:\[[^\]]*\])?\{[^}]*\}', '', text)
        text = re.sub(r'\\ccsdesc(?:\[[^\]]*\])?\{[^}]*\}', '', text)
        text = re.sub(r'\\begin\{CCSXML\}.*?\\end\{CCSXML\}', '', text, flags=re.DOTALL)
        text = re.sub(r'\\Description\{((?:[^{}]|{[^{}]*})*)\}', '', text)
        text = re.sub(r'\\affiliation\{((?:[^{}]|{[^{}]*})*)\}', '', text, flags=re.DOTALL)
        text = re.sub(r'\\(?:institution|city|country|state|postcode|streetaddress)\{[^{}]*\}', '', text)

        # Bibliographie résiduelle
        text = re.sub(r'\\(?:bibliographystyle|bibliography)(?:\{[^}]*\})?', '', text)
        text = re.sub(r'\\nocite\*?(?:\{[^}]*\})?', '', text)

        # 6. Caractères et symboles spéciaux
        text = re.sub(r'\\textbar\b', '|', text)
        text = re.sub(r'\\quad\b', ' ', text)
        text = re.sub(r'\\qquad\b', '  ', text)
        text = re.sub(r'\\textsuperscript\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)
        text = re.sub(r'\\textsubscript\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)
        text = re.sub(r'\\rightarrow\b', '->', text)
        text = re.sub(r'\\leftarrow\b', '<-', text)
        text = re.sub(r'\\checkmark\b', '✓', text)
        text = re.sub(r'\\texttimes\b', '×', text)
        text = re.sub(r'\\ding\{51\}', '✓', text)
        text = re.sub(r'\\ding\{55\}', '✗', text)
        text = re.sub(r'\\\\(?:\[[^\]]*\])?', '\n', text)

        return text

    def clean_inline_formatting(self, text: str) -> str:
        """Nettoie le formatage inline LaTeX avec protection KaTeX absolue."""
        text = re.sub(r'\\par\b', '\n\n', text)
        text = re.sub(r'\\(?:smallskip|medskip|bigskip)\b', '\n\n', text)
        text = self.replace_shortstack(text)

        math_map = {}
        def repl_display(m):
            token = f"___MATH_BLOCK_D_{len(math_map)}___"
            math_map[token] = m.group(0)
            return token

        def repl_inline(m):
            token = f"___MATH_BLOCK_I_{len(math_map)}___"
            math_map[token] = m.group(0)
            return token

        text = re.sub(r'\$\$.*?\$\$', repl_display, text, flags=re.DOTALL)
        text = re.sub(r'(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)', repl_inline, text)

        # Déballage des polices inline récursif
        for _ in range(5):
            text = re.sub(r'\\textbf\{((?:[^{}]|{[^{}]*})*)\}', r'**\1**', text)
            text = re.sub(r'\\textit\{((?:[^{}]|{[^{}]*})*)\}', r'*\1*', text)
            text = re.sub(r'\\emph\{((?:[^{}]|{[^{}]*})*)\}', r'*\1*', text)
            text = re.sub(r'\\texttt\{((?:[^{}]|{[^{}]*})*)\}', r'`\1`', text)
            text = re.sub(r'\\textsf\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)
            text = re.sub(r'\\textsl\{((?:[^{}]|{[^{}]*})*)\}', r'*\1*', text)
            text = re.sub(r'\\textsc\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)
            text = re.sub(r'\\textup\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)
            text = re.sub(r'\\textmd\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)
            text = re.sub(r'\\textrm\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)
            text = re.sub(r'\\textnormal\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)
            text = re.sub(r'\\underline\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)
            text = re.sub(r'\\text\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)

        text = re.sub(r'\\eqref\{([^}]+)\}', r'(\1)', text)
        text = re.sub(r'\\(?:ref|autoref|pageref)\{([^}]+)\}', r'[\1]', text)
        text = re.sub(r'\\url\{([^}]+)\}', r'<\1>', text)
        text = re.sub(r'\\href\{([^}]+)\}\{([^}]+)\}', r'[\2](\1)', text)
        text = re.sub(r'\\footnote\{([^}]+)\}', r' (*Note: \1*)', text)

        text = re.sub(r'\\\s+', ' ', text)
        text = text.replace('``', '"').replace("''", '"').replace('~', ' ').replace(r'\,', ' ')
        text = text.replace(r'\&', '&').replace(r'\_', '_').replace(r'\#', '#').replace(r'\%', '%')
        text = text.replace(r'\{', '{').replace(r'\}', '}')

        text = BibTexParser.decode_latex_accents(text)
        text = re.sub(r'\\(?:centering|noindent|frenchspacing|medskip|bigskip|smallskip|clearpage|newpage|vfill|hfill|small|footnotesize|scriptsize|large|Large|LARGE|huge|Huge)\b[ \t]*', ' ', text)
        text = re.sub(r'\\label\{[^}]+\}', '', text)
        text = re.sub(r'\\(?:color|rowcolor|columncolor|cellcolor|arrayrulecolor)(?:\[[^\]]*\])?(?:\{[^{}]*\}|\s+[a-zA-Z0-9!_]+)?', '', text)
        text = re.sub(r'\\(?:toprule|midrule|bottomrule|hline|addlinespace|cmidrule(?:\[[^\]]*\])?\{[^}]*\})', '', text)
        text = re.sub(r'\\dimexpr\b[^{}]*(?:\\relax)?', '', text)
        text = re.sub(r'\\relax\b', '', text)
        text = re.sub(r'\\(?:fboxsep|fboxrule|linewidth|vrule)\b', '', text)

        text = re.sub(r'\\checkmark\b', '✓', text)
        text = re.sub(r'\\texttimes\b', '×', text)
        text = re.sub(r'\\ding\{51\}', '✓', text)
        text = re.sub(r'\\ding\{55\}', '✗', text)

        # Nettoyage des accolades résiduelles de groupement AVANT de restaurer math_map !
        for _ in range(3):
            text = re.sub(r'(?<![\\\$a-zA-Z0-9_])\{([^{}]*)\}', r'\1', text)

        # Nettoyage des accolades fermantes orphelines
        text = re.sub(r'\*\*\}([ \t]*)', '** ', text)
        text = re.sub(r'\*\}\b', '* ', text)

        # Restauration des blocs mathématiques KaTeX intacts
        for token, math_content in math_map.items():
            text = text.replace(token, math_content)

        return text

    def format_paragraphs(self, text: str) -> str:
        """Normalise les paragraphes et retours à la ligne."""
        text = re.sub(r'\r\n', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        raw_blocks = re.split(r'\n\s*\n', text.strip())
        formatted_blocks = []

        for block in raw_blocks:
            lines = [l.rstrip() for l in block.splitlines() if l.strip()]
            if not lines:
                continue
            first_line = lines[0].strip()
            if (any(l.strip().startswith('|') for l in lines) or
                first_line.startswith(('#', '>', '$$', '![')) or
                any(l.strip().startswith(('>', '$$', '![')) for l in lines) or
                re.match(r'^\s*[-*+]\s+', first_line) or
                re.match(r'^\s*\d+\.\s+', first_line)):
                formatted_blocks.append('\n'.join(lines))
            else:
                formatted_blocks.append(' '.join(l.strip() for l in lines))

        result = '\n\n'.join(formatted_blocks)
        result = re.sub(r'([^\n])\n(#{1,6}\s+)', r'\1\n\n\2', result)
        result = re.sub(r'(#{1,6}\s+[^\n]+)\n([^\n#])', r'\1\n\n\2', result)
        result = re.sub(r'\n{3,}', '\n\n', result)
        return result

    @staticmethod
    def sanitize_callouts(text: str) -> str:
        """Garantit le formatage natif valide des callouts Obsidian."""
        lines = text.splitlines()
        out_lines = []
        in_callout = False
        for line in lines:
            stripped = line.strip()
            m_start = re.match(r'^>\s*\[!([a-zA-Z]+)\]\s*(.*)$', stripped)
            if m_start:
                in_callout = True
                c_type = m_start.group(1).upper()
                c_title = m_start.group(2).strip()
                out_lines.append(f"> [!{c_type}] {c_title}" if c_title else f"> [!{c_type}]")
                continue

            if in_callout:
                if re.match(r'^#{1,6}\s+', stripped) or re.match(r'^---+$', stripped):
                    in_callout = False
                    out_lines.append(line)
                    continue
                if stripped.startswith('>'):
                    cleaned_line = re.sub(r'^\s*>\s*', '', line).strip()
                    out_lines.append(f"> {cleaned_line}" if cleaned_line else ">")
                elif stripped == '':
                    out_lines.append("")
                    in_callout = False
                else:
                    out_lines.append(f"> {stripped}")
            else:
                out_lines.append(line)
        return '\n'.join(out_lines)

    def convert(self) -> str:
        """Pipeline complet de conversion."""
        if self.root_path and self.root_path.exists():
            raw_text = self.resolve_inputs(self.root_path)
        else:
            raw_text = self.raw_content or ""

        if not self.bib_parser.entries and self.root_dir and self.root_dir.exists():
            for bib_file in self.root_dir.glob("*.bib"):
                self.bib_parser.load_bib_file(bib_file)

        text_no_comments = self.strip_comments(raw_text)
        text_no_macros, self.macros = LatexMacroEngine.extract_macros(text_no_comments)
        text_expanded = LatexMacroEngine.expand_macros(text_no_macros, self.macros) if self.macros else text_no_comments

        body = self.extract_metadata(text_expanded)
        body = self.convert_math(body)
        body = self.convert_citations(body)
        body = self.convert_figures(body)
        body = self.convert_tables(body)
        body = self.convert_lists(body)
        body = self.convert_environments(body)
        body = self.convert_headings(body)
        body = self.clean_layout_formatting(body)
        body = self.clean_inline_formatting(body)
        body = self.clean_layout_formatting(body)
        body = self.format_paragraphs(body)

        doc_parts = []
        if self.title:
            doc_parts.append(f"# {self.title}\n")

        if self.authors:
            doc_parts.append(f"**Auteurs :** {self.authors}\n")

        if self.keywords and "**Mots-clés :**" not in body:
            doc_parts.append(f"**Mots-clés :** {self.keywords}\n")

        doc_parts.append(body)

        if self.cited_keys:
            doc_parts.append("\n\n## 📚 Références Bibliographiques\n")
            for k in self.cited_keys:
                doc_parts.append(self.bib_parser.format_full_reference(k))

        final_md = "\n\n".join(doc_parts)
        formatted = self.format_paragraphs(final_md)
        return self.sanitize_callouts(formatted)
