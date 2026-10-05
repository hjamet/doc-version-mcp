"""
diff_engine.py — Moteur AST de diff inline word-diff chirurgical multi-auteurs avec protection KaTeX.
"""

import re
import difflib
from typing import Dict, List, Tuple, Optional, Set, Any


class SectionBlock:
    """Représentation d'une section Markdown pour le moteur AST diff."""
    def __init__(self, heading: str, level: int, title: str, lines: List[str]):
        self.heading = heading  # Ex: "### General Info" ou ""
        self.level = level      # 1, 2, 3, etc. (0 pour le préambule)
        self.title = title      # Ex: "General Info"
        self.lines = lines      # Lignes sous le titre

    @property
    def normalized_title(self) -> str:
        """Normalise le titre de section pour l'alignement (ignore numérotation, émojis et casse)."""
        cleaned = re.sub(r'^[0-9\.\s\-\:\#]+', '', self.title.lower())
        cleaned = re.sub(r'[^\w\s]', '', cleaned)
        return ' '.join(cleaned.split())


class CalloutBlock:
    """Représentation d'un bloc callout Markdown (> [!TYPE] ...) pour le moteur AST diff."""
    def __init__(self, raw_text: str, c_type: str, title: str, lines: List[str]):
        self.raw_text = raw_text
        self.c_type = c_type
        self.title = title
        self.lines = lines


class DiffEngine:
    """Moteur de comparaison différentielle chirurgicale par sections AST."""

    DIFF_SUMMARY_HEADER = "## 🔄 Synthèse des Changements & Diffs Récents"
    USER_COMMENTS_HEADER = "## 💬 Commentaires & Retours d'Arbitrage"

    # Style Auteur Local / Agent (vert doux épuré / rouge doux)
    DEL_STYLE_LOCAL = 'style="background-color: #fee2e2; color: #991b1b; padding: 2px 4px; border-radius: 3px;"'
    INS_STYLE_LOCAL = 'style="background-color: #dcfce7; color: #166534; padding: 2px 4px; border-radius: 3px;"'

    # Style Collaborateurs (bleu ciel pour ajouts, ambre doux pour suppressions)
    DEL_STYLE_COLLAB = 'style="background-color: #ffedd5; color: #9a3412; padding: 2px 4px; border-radius: 3px;"'
    INS_STYLE_COLLAB = 'style="background-color: #dbeafe; color: #1e40af; padding: 2px 4px; border-radius: 3px;"'

    PARAGRAPH_BLOCK_DIFF_THRESHOLD: float = 0.5
    """Seuil de taux de modification au-delà duquel un paragraphe est rendu en bloc plutôt que mot à mot (défaut: 0.5 = 50%)."""

    SECTION_ALIASES = {
        'the llm network game': 'the latent space',
        'game overview and setup': 'game overview and components',
        'economy scoring and victory objective': 'economy tolerance and scoring',
        'the 5step round loop': 'the 5phase gameplay loop',
        'expansion modules': 'modular architectural expansions',
        'game calibration via largescale monte carlo simulation': 'game balance verification via insilico simulation',
    }

    @classmethod
    def split_into_sections(cls, text: str) -> List[SectionBlock]:
        """Découpe un texte Markdown en une liste de sections AST."""
        lines = text.splitlines()
        sections: List[SectionBlock] = []
        curr_heading = ""
        curr_level = 0
        curr_title = "Préambule"
        curr_lines: List[str] = []

        for line in lines:
            match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if match:
                if curr_lines or curr_heading:
                    sections.append(SectionBlock(curr_heading, curr_level, curr_title, curr_lines))
                curr_level = len(match.group(1))
                raw_t = match.group(2).strip()
                from .latex_resolver import LatexToMarkdownConverter
                raw_t = LatexToMarkdownConverter.unwrap_font_commands(raw_t, to_markdown=False)
                raw_t = LatexToMarkdownConverter.strip_html_and_styles(raw_t)
                raw_t = re.sub(r'\\label\{[^}]+\}', '', raw_t).strip()
                raw_t = re.sub(r'^\*\*(.*?)\*\*$', r'\1', raw_t).strip()
                raw_t = re.sub(r'\\(?:textsf|textsc|textup|textmd|textrm|textnormal|text|underline|textbf|textit|emph|textsl|texttt)\b\s*\{?', '', raw_t)
                raw_t = re.sub(r'[\{\}]', '', raw_t)
                raw_t = re.sub(r'\s+', ' ', raw_t).strip()
                curr_title = raw_t
                curr_heading = f"{match.group(1)} {curr_title}"
                curr_lines = []
            else:
                curr_lines.append(line)

        if curr_lines or curr_heading:
            sections.append(SectionBlock(curr_heading, curr_level, curr_title, curr_lines))

        return sections

    @classmethod
    def find_matching_section(
        cls,
        norm_title: str,
        sec_map: Dict[str, List[SectionBlock]],
        used_secs: Set[SectionBlock]
    ) -> Optional[SectionBlock]:
        """Recherche intelligente d'une section correspondante (exacte, alias ou fuzzy)."""
        if norm_title in sec_map:
            for cand in sec_map[norm_title]:
                if cand not in used_secs:
                    return cand

        rev_aliases = {v: k for k, v in cls.SECTION_ALIASES.items()}
        alias = cls.SECTION_ALIASES.get(norm_title) or rev_aliases.get(norm_title)
        if alias and alias in sec_map:
            for cand in sec_map[alias]:
                if cand not in used_secs:
                    return cand

        best_cand = None
        best_score = 0.0
        norm_tokens = set(norm_title.split())
        for title, cand_list in sec_map.items():
            cand_tokens = set(title.split())
            ratio = difflib.SequenceMatcher(None, norm_title, title, autojunk=False).ratio()
            jaccard = len(norm_tokens & cand_tokens) / max(len(norm_tokens | cand_tokens), 1)
            comb = max(ratio, jaccard)
            if comb > 0.55 and comb > best_score:
                for cand in cand_list:
                    if cand not in used_secs:
                        best_cand = cand
                        best_score = comb
        return best_cand

    @classmethod
    def clean_residual_latex(cls, text: str) -> str:
        """Nettoie tout résidu LaTeX afin que les comparaisons portent sur le fond avec protection KaTeX absolue."""
        if not text:
            return ""

        math_map = {}
        def repl_display(m):
            token = f"___DIFF_MATH_D_{len(math_map)}___"
            math_map[token] = m.group(0)
            return token

        def repl_inline(m):
            token = f"___DIFF_MATH_I_{len(math_map)}___"
            math_map[token] = m.group(0)
            return token

        text = re.sub(r'\$\$.*?\$\$', repl_display, text, flags=re.DOTALL)
        text = re.sub(r'(?<!\$)\$(?!\$)(.*?)(?<!\$)\$(?!\$)', repl_inline, text)

        from .latex_resolver import LatexToMarkdownConverter
        text = LatexToMarkdownConverter.strip_html_and_styles(text)
        text = LatexToMarkdownConverter.convert_special_callouts(text)
        text = LatexToMarkdownConverter.unwrap_boxes(text)

        # Environnements de mise en page (minipage, center, flushleft, flushright, tcolorbox)
        for _ in range(5):
            text = re.sub(
                r'\\begin\{(?:minipage|boxedminipage)\}(?:\[[^\]]*\])?(?:\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})+\s*(.*?)\s*\\end\{(?:minipage|boxedminipage)\}%?',
                r'\n\n\1\n\n',
                text,
                flags=re.DOTALL
            )
        for env in ('center', 'flushleft', 'flushright', 'tcolorbox', 'shaded', 'framed', 'mdframed'):
            text = re.sub(rf'\\begin\{{{env}\}}(?:\[[^\]]*\])?\s*(.*?)\s*\\end\{{{env}\}}', r'\n\n\1\n\n', text, flags=re.DOTALL)

        # Blockquotes
        env_quote = re.compile(r'\\begin\{(?:quote|quotation|verse)\}\s*(.*?)\s*\\end\{(?:quote|quotation|verse)\}', re.DOTALL)
        text = env_quote.sub(lambda m: "\n\n" + "\n".join([f"> {l}" if l.strip() else ">" for l in m.group(1).strip().splitlines()]) + "\n\n", text)
        text = re.sub(r'\\begin\{(?:center|abstract)\}\s*(.*?)\s*\\end\{(?:center|abstract)\}', r'\1', text, flags=re.DOTALL)
        text = re.sub(r'\\(?:begin|end)\{[^}]+\}', '', text)
        text = re.sub(r'\\item(?:\s*\[[^\]]*\])?\s*', '- ', text)

        # Polices et tailles de police
        text = re.sub(r'\\fontsize\{[^{}]*\}\{[^{}]*\}\s*(?:\\selectfont)?', '', text)
        text = re.sub(r'\\selectfont\b', '', text)
        text = re.sub(r'\\(?:small|footnotesize|scriptsize|normalsize|large|Large|LARGE|huge|Huge)\b', '', text)
        text = re.sub(r'\\(?:normalfont|bfseries|itshape|slshape|scshape|sffamily|ttfamily|rmfamily)\b', '', text)

        # Déballage récursif robuste des polices inline et suppression de tout résidu orphelin
        text = LatexToMarkdownConverter.unwrap_font_commands(text, to_markdown=True)
        text = LatexToMarkdownConverter.strip_html_and_styles(text)

        # Espacements et sauts
        text = re.sub(r'\\label\{[^}]+\}', '', text)
        text = re.sub(r'\\(?:centering|noindent|frenchspacing|medskip|bigskip|smallskip|clearpage|newpage|vfill|hfill|raggedleft|raggedright)\b', '', text)
        text = re.sub(r'\\needspace(?:\{[^{}]*\}|\[[^\]]*\])?', '', text)
        text = re.sub(r'\\(?:vspace|hspace|setlength|addtolength)\*?\{[^}]*\}(?:\{[^}]*\})?', '', text)
        text = re.sub(r'\\cmidrule(?:\s*\([^)]*\))?(?:\s*\[[^\]]*\])?(?:\s*\{[^}]*\}|\s*\d+-\d+)?', '', text)
        text = re.sub(r'\\(?:toprule|midrule|bottomrule|hline|addlinespace)\b', '', text)
        text = re.sub(r'\\keywords\s*\{.*?\}', '', text, flags=re.DOTALL)
        text = re.sub(r'\\and\b', ' • ', text)
        text = re.sub(r'\\(?:Statex|State|Require|Ensure|EndFor|EndIf|EndWhile)\b', '', text)
        text = re.sub(r'\\renewcommand\{\\arraystretch\}\{[^{}]*\}', '', text)

        # Règles, boîtes, couleurs et dimensions
        text = re.sub(r'\\hrule\b(?:[ \t]*(?:height|width|depth)[ \t]+[\d\.]+\s*[a-zA-Z%]+)*', '\n\n---\n\n', text)
        text = re.sub(r'\\rule(?:\[[^\]]*\])?\{[^{}]*\}\{[^{}]*\}', '', text)
        text = re.sub(r'\\vrule\b(?:\s*(?:width|height|depth)\s*[\d\.]+\s*[a-zA-Z%]+)*', '', text)
        text = re.sub(r'\\dimexpr\b[^{}]*(?:\\relax)?', '', text)
        text = re.sub(r'\\relax\b', '', text)
        text = re.sub(r'\\(?:linewidth|textwidth|columnwidth|paperwidth|paperheight)\b', '', text)
        text = re.sub(r'\\(?:fboxsep|fboxrule)\b', '', text)
        text = re.sub(r'\\definecolor\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}', '', text)
        text = re.sub(r'\\(?:color|rowcolor|columncolor|cellcolor|arrayrulecolor)(?:\s*\[[^\]]*\])?(?:\s*\{[^{}]*\}|\s+[a-zA-Z0-9!_]+)?', '', text)
        text = re.sub(r'\\textcolor(?:\[[^\]]*\])?\{[^{}]*\}\{((?:[^{}]|{[^{}]*})*)\}', r'\1', text)

        # Configuration et métadonnées parasites
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

        # Caractères et symboles spéciaux
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

        text = re.sub(r'\\(?:newcommand|renewcommand|providecommand)\*?\s*\{\\[a-zA-Z]+\}(?:\[\d+\])?\{.*?\}', '', text, flags=re.DOTALL)
        text = re.sub(r'\\nocite\*?(?:\{[^}]*\})?', '', text)
        text = re.sub(r'\\(?:bibliography|bibliographystyle)\s*(?:\{[^}]*\}|[a-zA-Z0-9_\-]+)?', '', text)

        text = re.sub(r'\\xspace\s*([,.:;!?\'"\)\}\]])', r'\1', text)
        text = re.sub(r'\\xspace\b\s*', ' ', text)
        text = text.replace('~', ' ').replace(r'\,', ' ').replace(r'\&', '&').replace(r'\_', '_').replace(r'\#', '#').replace(r'\%', '%')
        text = re.sub(r'(?<![\n:|\-])---(?![\n:|\-])', '—', text)
        text = re.sub(r'(?<![\n:|\-])--(?![\n:|\-])', '–', text)
        text = re.sub(r'\\+\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\\+\s*\|', '|', text)

        # Deuxième passe de sécurisation : suppression de toute commande de police orpheline restante
        text = re.sub(r'\\(?:textsf|textsc|textup|textmd|textrm|textnormal|text|underline|textbf|textit|emph|textsl|texttt)\b\s*\{?', '', text)

        # Nettoyage des accolades résiduelles de groupement AVANT de restaurer math_map
        for _ in range(3):
            text = re.sub(r'(?<![\\\$a-zA-Z0-9_])\{([^{}]*)\}', r'\1', text)

        # Nettoyage des accolades fermantes orphelines attachées à des marqueurs markdown
        text = re.sub(r'\*\*\}([ \t]*)', '** ', text)
        text = re.sub(r'\*\}\b', '* ', text)
        text = re.sub(r'`\}([ \t]*)', '` ', text)

        # Restauration des blocs mathématiques KaTeX intacts
        for token, math_content in math_map.items():
            text = text.replace(token, math_content)

        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @classmethod
    def extract_manuscript_body(cls, content: str) -> str:
        """Extrait le texte de fond d'un document ou artéfact en déballant les diffs précédents."""
        text = content
        text = re.sub(r'^---\n.*?\n---\n?', '', text, flags=re.DOTALL)
        text = re.sub(r'<!--.*?-->\n?', '', text)

        if cls.USER_COMMENTS_HEADER in text:
            text = text.split(cls.USER_COMMENTS_HEADER)[0]

        for hdr in [cls.DIFF_SUMMARY_HEADER, "## 📑 Structure & Sommaire AST du Manuscrit"]:
            if hdr in text:
                parts = text.split(hdr, 1)
                after = parts[1]
                sep_match = re.search(r'\n---\s*\n', after)
                if sep_match:
                    text = after[sep_match.end():]
                else:
                    next_h2 = re.search(r'\n##\s+', after)
                    if next_h2:
                        text = after[next_h2.start():]

        # Nettoyage du bloc texte final prêt à copier s'il est présent
        text = re.sub(r'<details><summary>📋\s*Texte Final Prêt à Copier</summary>.*?</details>\s*(?:---\s*)?', '', text, flags=re.DOTALL)

        # Nettoyage des anciens callouts
        text = re.sub(
            r'>\s*\[!NOTE\]\s*\n>\s*\*\*🔄\s*Synthèse des Travaux Récents & Conciliation Collaborative\*\*.*?(?=(?:\n(?!>))|\Z)',
            '',
            text,
            flags=re.DOTALL
        )
        text = re.sub(
            r'>\s*\[!(?:TIP|CAUTION|NOTE)\]\s*\n>\s*(?:🛡️|🚨|\*\*Baseline Git).*?(?=(?:\n(?!>))|\Z)',
            '',
            text,
            flags=re.DOTALL
        )
        text = re.sub(r'<span\b[^>]*>(?:🛡️|🚨|⚠️)\s*(?:Score IA|P\(AI\))\s*:?.*?</span>\s*', '', text)
        text = re.sub(r'>\s*\[!CAUTION\]\s*🔴\s*Section Supprimée\s*:.*?(?=(?:\n(?!>))|\Z)', '', text, flags=re.DOTALL)

        # Supprimer le texte balisé en suppression
        text = re.sub(r'<del\b[^>]*>.*?</del>', '', text, flags=re.DOTALL)
        text = re.sub(r'<span\b[^>]*style="[^"]*#(?:fee2e2|ffedd5)[^"]*"[^>]*>.*?</span>', '', text, flags=re.DOTALL)

        # Déballer le texte balisé en ajout
        text = re.sub(r'<ins\b[^>]*>(.*?)</ins>', r'\1', text, flags=re.DOTALL)
        text = re.sub(r'<span\b[^>]*style="[^"]*#(?:dcfce7|dbeafe)[^"]*"[^>]*>(.*?)</span>', r'\1', text, flags=re.DOTALL)
        from .latex_resolver import LatexToMarkdownConverter
        text = LatexToMarkdownConverter.strip_html_and_styles(text)

        lines = text.splitlines()
        clean_lines = []
        quote_buffer = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(('> [!CAUTION]', '> [!FAILURE]', '> [!FAIL]', '> [!DANGER]')):
                continue
            if stripped.startswith('>'):
                quote_buffer.append(line)
            else:
                if quote_buffer:
                    if cls.has_substantive_words("\n".join(quote_buffer)):
                        clean_lines.extend(quote_buffer)
                    quote_buffer = []
                clean_lines.append(line)
        if quote_buffer:
            if cls.has_substantive_words("\n".join(quote_buffer)):
                clean_lines.extend(quote_buffer)

        result_lines = [re.sub(r'[ \t]{2,}', ' ', l) for l in clean_lines]
        body = "\n".join(result_lines).strip()
        return cls.clean_residual_latex(body)

    @classmethod
    def has_substantive_words(cls, text: str) -> bool:
        """Vérifie si le texte contient au moins un mot alphanumérique substantiel."""
        if not text:
            return False
        t = re.sub(r'<[^>]+>', ' ', text)
        t = re.sub(r'[\s>\*\_`#\-\+\|~=:;,\.!\?\(\)\[\]\{\}\\\/\'\"«»“”–—\^]+', ' ', t)
        return bool(re.search(r'\w', t))

    @classmethod
    def mask_figures_in_text(cls, text: str) -> Tuple[str, Dict[str, str]]:
        """Remplace les figures et callouts graphiques par des marqueurs atomiques."""
        figure_map: Dict[str, str] = {}
        lines = text.splitlines(keepends=True)
        out_lines: List[str] = []
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            s = line.strip()
            is_fig_callout = False
            if s.startswith('> [!NOTE]') and ('🖼️ Figure' in s or '📐 Schéma' in s):
                is_fig_callout = True
            elif s.startswith('> [!NOTE]') and i + 1 < n and ('📐 Schéma' in lines[i+1] or '🖼️ Figure' in lines[i+1]):
                is_fig_callout = True

            if is_fig_callout:
                fig_lines = [line]
                i += 1
                while i < n:
                    curr = lines[i]
                    curr_s = curr.strip()
                    if curr_s.startswith('> [!'):
                        break
                    if curr_s.startswith('>') or not curr_s:
                        fig_lines.append(curr)
                        if not curr_s and i + 1 < n and not lines[i+1].strip().startswith('>'):
                            i += 1
                            break
                        i += 1
                    else:
                        break
                token = f"___MD_FIGURE_BLOCK_{len(figure_map)}___"
                suffix = "\n" if fig_lines and fig_lines[-1].endswith("\n") else ""
                figure_map[token] = "".join(fig_lines)
                out_lines.append(token + suffix)
                continue

            if re.match(r'^\s*!\[[^\]]*\]\([^\)]+\)\s*$', line) or re.match(r'^\s*!\[\[[^\]]+\]\]\s*$', line):
                token = f"___MD_FIGURE_BLOCK_{len(figure_map)}___"
                suffix = "\n" if line.endswith("\n") else ""
                figure_map[token] = line
                out_lines.append(token + suffix)
                i += 1
                continue

            out_lines.append(line)
            i += 1

        return "".join(out_lines), figure_map

    @classmethod
    def mask_tables_in_text(cls, text: str) -> Tuple[str, Dict[str, str]]:
        """Remplace les tableaux Markdown par des marqueurs atomiques."""
        table_map: Dict[str, str] = {}
        lines = text.splitlines(keepends=True)
        out_lines: List[str] = []
        i = 0
        n = len(lines)

        def is_table_candidate(l: str) -> bool:
            s = l.strip()
            if s.startswith('>'):
                s = s.lstrip('>').strip()
            return s.startswith('|') and s.endswith('|') and '|' in s[1:]

        while i < n:
            if is_table_candidate(lines[i]):
                tbl_lines = []
                while i < n and is_table_candidate(lines[i]):
                    tbl_lines.append(lines[i])
                    i += 1

                has_sep = any(re.search(r'\|\s*:?-{2,}:?\s*\|', l) for l in tbl_lines)
                if has_sep and len(tbl_lines) >= 2:
                    token = f"___MD_TABLE_BLOCK_{len(table_map)}___"
                    suffix = "\n" if tbl_lines[-1].endswith("\n") else ""
                    table_map[token] = "".join(tbl_lines)
                    out_lines.append(token + suffix)
                else:
                    out_lines.extend(tbl_lines)
            else:
                out_lines.append(lines[i])
                i += 1

        return "".join(out_lines), table_map

    @classmethod
    def extract_callouts(cls, text: str) -> Tuple[str, List[CalloutBlock]]:
        """Extrait les blocs callouts Markdown (> [!TYPE] ...) et les remplace par des marqueurs atomiques."""
        lines = text.splitlines(keepends=True)
        out_lines: List[str] = []
        callouts: List[CalloutBlock] = []
        i = 0
        n = len(lines)

        while i < n:
            line = lines[i]
            s = line.strip()
            m_start = re.match(r'^>\s*\[!([a-zA-Z]+)\]\s*(.*)$', s)
            if m_start:
                c_type = m_start.group(1).upper()
                c_title = m_start.group(2).strip()
                c_lines = [line]
                i += 1
                while i < n:
                    curr = lines[i]
                    curr_s = curr.strip()
                    if re.match(r'^>\s*\[!([a-zA-Z]+)\]', curr_s):
                        break
                    if curr_s.startswith('>') or (not curr_s and i + 1 < n and lines[i + 1].strip().startswith('>')):
                        c_lines.append(curr)
                        i += 1
                    else:
                        break
                raw = "".join(c_lines)
                callout = CalloutBlock(raw, c_type, c_title, c_lines)
                idx = len(callouts)
                callouts.append(callout)
                token = f"___MD_CALLOUT_BLOCK_{idx}___"
                suffix = "\n" if raw.endswith("\n") else ""
                out_lines.append(token + suffix)
            else:
                out_lines.append(line)
                i += 1

        return "".join(out_lines), callouts

    @classmethod
    def diff_callout_pair(
        cls,
        old_c: CalloutBlock,
        new_c: CalloutBlock,
        is_collab: bool = False,
        author_name: str = ""
    ) -> Tuple[str, int, int, int, int]:
        """Compare chirurgicalement deux callouts appariés."""
        if old_c.raw_text == new_c.raw_text:
            return new_c.raw_text, 0, 0, 0, 0

        old_l = [l.rstrip('\r\n') for l in old_c.lines]
        new_l = [l.rstrip('\r\n') for l in new_c.lines]
        diffed_lines, l_add, l_del, c_add, c_del = cls.diff_section_lines(
            old_l, new_l,
            is_collab=is_collab,
            author_name=author_name,
            in_callout_diff=True
        )
        suffix = "\n" if new_c.raw_text.endswith("\n") else ""
        return "\n".join(diffed_lines) + suffix, l_add, l_del, c_add, c_del

    @classmethod
    def sanitize_table_pipes_in_diff(cls, lines: List[str]) -> List[str]:
        """Empêche les balises de diff de traverser les pipes d'un tableau Markdown."""
        cleaned_lines = []
        for l in lines:
            if re.search(r'\|\s*:?-{2,}:?\s*\|', l):
                clean_l = re.sub(r'</?(?:ins|del|span)\b[^>]*>', '', l)
                cleaned_lines.append(clean_l)
            elif l.strip().startswith('|') or (l.strip().startswith('>') and '|' in l):
                clean_l = re.sub(r'(<(ins|del|span)\b[^>]*>)([^<]*?)\|([^<]*?)(<\/\2>)', r'\1\3\5 | \1\4\5', l)
                cleaned_lines.append(clean_l)
            else:
                cleaned_lines.append(l)
        return cleaned_lines

    @classmethod
    def sanitize_katex_in_diff(cls, text: str) -> str:
        """
        Garantit que les délimiteurs KaTeX $$...$$ sont parfaitement équilibrés,
        isolés sur leurs propres lignes, et totalement exempts de balises HTML de diff
        (<span>, <ins>, <del>) qui coupent les $$ ou cassent le parseur KaTeX.
        """
        if not text or "$$" not in text:
            return text

        # 1. Nettoyer les balises de diff parasites collées directement aux délimiteurs $$ sur la même ligne
        text = re.sub(r'</?(?:ins|del|span)\b[^>]*>[^\S\r\n]*\$\$[^\S\r\n]*</?(?:ins|del|span)\b[^>]*>', '\n\n$$\n\n', text)
        text = re.sub(r'</?(?:ins|del|span)\b[^>]*>[^\S\r\n]*\$\$', '\n\n$$\n\n', text)
        text = re.sub(r'\$\$[^\S\r\n]*</?(?:ins|del|span)\b[^>]*>', '\n\n$$\n\n', text)

        # 2. Pour chaque bloc $$...$$, isoler les $$ sur leurs propres lignes et éliminer tout tag HTML intérieur
        def clean_display_math(match):
            inner = match.group(1)
            clean_inner = re.sub(r'</?(?:ins|del|span)\b[^>]*>', '', inner)
            clean_inner = clean_inner.strip()
            if not clean_inner:
                return ""
            return f"\n\n$$\n{clean_inner}\n$$\n\n"

        text = re.sub(r'\$\$(.*?)\$\$', clean_display_math, text, flags=re.DOTALL)

        # 3. Nettoyer les sauts de ligne excessifs autour des blocs math
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    @classmethod
    def sanitize_inline_code_in_diff(cls, text: str) -> str:
        """
        Garantit qu'aucune balise HTML de diff (<span...>, <ins...>, <del...>)
        n'est piégée à l'intérieur de backticks Markdown (`...`), ce qui causerait
        l'affichage du HTML brut dans Obsidian et Antigravity.
        Inverse l'imbrication pour placer les délimiteurs de code inline
        À L'INTÉRIEUR des balises span de diff :
        `<span ...>`ancien`</span><span ...>`nouveau`</span>` au lieu de `<span ...>...</span>`.
        """
        if not text or '`' not in text:
            return text

        code_span_pattern = re.compile(
            r'(?<!`)(`{1,3})(?!`)(.+?)(?<!`)\1(?!`)',
            re.DOTALL
        )

        diff_tag_pattern = re.compile(
            r'(<(?:span|ins|del)\b[^>]*>.*?</(?:span|ins|del)>)',
            re.DOTALL
        )

        def fix_code_span(match: re.Match) -> str:
            fence = match.group(1)
            inner = match.group(2)

            if not re.search(r'</?(?:span|ins|del)\b', inner):
                return match.group(0)

            parts = diff_tag_pattern.split(inner)
            out_parts = []
            for part in parts:
                if not part:
                    continue
                m_tag = re.match(r'^(<(?:span|ins|del)\b[^>]*>)(.*?)(</(?:span|ins|del)>)$', part, re.DOTALL)
                if m_tag:
                    open_tag = m_tag.group(1)
                    tag_content = m_tag.group(2)
                    close_tag = m_tag.group(3)

                    if tag_content.startswith(fence) and tag_content.endswith(fence) and len(tag_content) >= 2 * len(fence):
                        out_parts.append(f"{open_tag}{tag_content}{close_tag}")
                    else:
                        out_parts.append(f"{open_tag}{fence}{tag_content}{fence}{close_tag}")
                else:
                    if part.strip():
                        leading_ws = part[:len(part) - len(part.lstrip(' '))]
                        trailing_ws = part[len(part.rstrip(' ')):]
                        core = part.strip(' ')
                        out_parts.append(f"{leading_ws}{fence}{core}{fence}{trailing_ws}")
                    else:
                        out_parts.append(part)

            return "".join(out_parts)

        return code_span_pattern.sub(fix_code_span, text)

    @classmethod
    def wrap_inline_block(cls, text: str, tag: str = "span", style: str = "", extra_attrs: str = "") -> str:
        """Enrobe le texte dans <tag style="...">...</tag> en préservant les préfixes Markdown."""
        lines = text.splitlines(keepends=True)
        wrapped_lines = []
        full_attrs = f"{style} {extra_attrs}".strip() if extra_attrs else style
        for line in lines:
            line_ending = "\n" if line.endswith("\n") else ""
            content = line[:-1] if line_ending else line

            prefix = ""
            m_quote = re.match(r'^(>+\s*)', content)
            m_list = re.match(r'^(\s*[-*+]\s+|\s*\d+\.\s+)', content)
            if m_quote:
                prefix = m_quote.group(1)
                content = content[len(prefix):]
            elif m_list:
                prefix = m_list.group(1)
                content = content[len(prefix):]

            if content.strip():
                wrapped_lines.append(f"{prefix}<{tag} {full_attrs}>{content}</{tag}>{line_ending}")
            else:
                wrapped_lines.append(f"{prefix}{content}{line_ending}")
        return "".join(wrapped_lines)

    @classmethod
    def format_del(cls, text: str, is_collab: bool = False, author: str = "") -> str:
        """Enrobe un texte supprimé dans un <span> stylisé."""
        if not text:
            return ""
        if '![' in text and '](' in text:
            return ""
        leading_ws = text[:len(text) - len(text.lstrip(' '))]
        trailing_ws = text[len(text.rstrip(' ')):]
        core = text.strip(' ')
        if not core:
            return text

        active_style = cls.DEL_STYLE_COLLAB if is_collab else cls.DEL_STYLE_LOCAL
        extra = f'title="Supprimé par {author}"' if (is_collab and author) else ""

        if '\n\n' in core:
            paras = core.split('\n\n')
            wrapped_paras = [cls.wrap_inline_block(p, "span", active_style, extra) if p.strip() else p for p in paras]
            return leading_ws + '\n\n'.join(wrapped_paras) + trailing_ws

        return leading_ws + cls.wrap_inline_block(core, "span", active_style, extra) + trailing_ws

    @classmethod
    def format_ins(cls, text: str, is_collab: bool = False, author: str = "") -> str:
        """Enrobe un texte ajouté dans un <span> stylisé."""
        if not text:
            return ""
        if '![' in text and '](' in text:
            return text
        leading_ws = text[:len(text) - len(text.lstrip(' '))]
        trailing_ws = text[len(text.rstrip(' ')):]
        core = text.strip(' ')
        if not core:
            return text

        active_style = cls.INS_STYLE_COLLAB if is_collab else cls.INS_STYLE_LOCAL
        extra = f'title="Ajouté par {author}"' if (is_collab and author) else ""

        if '\n\n' in core:
            paras = core.split('\n\n')
            wrapped_paras = [cls.wrap_inline_block(p, "span", active_style, extra) if p.strip() else p for p in paras]
            return leading_ws + '\n\n'.join(wrapped_paras) + trailing_ws

        return leading_ws + cls.wrap_inline_block(core, "span", active_style, extra) + trailing_ws

    @classmethod
    def apply_paragraph_block_diff(
        cls,
        text: str,
        threshold: float = PARAGRAPH_BLOCK_DIFF_THRESHOLD,
        is_collab: bool = False,
        author_name: str = ""
    ) -> str:
        """
        Convertit en mode bloc les paragraphes dont le taux de modification dépasse le seuil :
        taux = (mots_supprimes + mots_ajoutes) / (mots_ancien + mots_nouveau).
        Au-delà du seuil (défaut 0.5 = 50%), affiche le paragraphe d'origine entier (supprimé),
        puis le nouveau paragraphe entier (ajouté).
        """
        paras = text.split("\n\n")
        out_paras: List[str] = []

        del_span_re = re.compile(r'<span\b[^>]*style="[^"]*#(?:fee2e2|ffedd5)[^"]*"[^>]*>(.*?)</span>', re.DOTALL)
        ins_span_re = re.compile(r'<span\b[^>]*style="[^"]*#(?:dcfce7|dbeafe)[^"]*"[^>]*>(.*?)</span>', re.DOTALL)

        for p in paras:
            p_strip = p.strip()
            # Ignorer les lignes de titres, tables, blocs mathématiques ou callouts/citations
            if p_strip.startswith(('#', '|', '$$', '![', '>')):
                out_paras.append(p)
                continue

            has_del = bool(del_span_re.search(p))
            has_ins = bool(ins_span_re.search(p))
            if not (has_del or has_ins):
                out_paras.append(p)
                continue

            del_text = " ".join(del_span_re.findall(p))
            ins_text = " ".join(ins_span_re.findall(p))

            tb, ta = cls.extract_paragraph_diff_texts(p)

            mots_supp = len(re.findall(r'\b\w+\b', del_text))
            mots_ajoutes = len(re.findall(r'\b\w+\b', ins_text))
            mots_ancien = len(re.findall(r'\b\w+\b', tb))
            mots_nouveau = len(re.findall(r'\b\w+\b', ta))

            total_words = mots_ancien + mots_nouveau
            taux = (mots_supp + mots_ajoutes) / total_words if total_words > 0 else 0.0

            tok_re = re.compile(r'\s+|\w+|[^\w\s]', re.DOTALL | re.UNICODE)
            t_o = tok_re.findall(tb)
            t_n = tok_re.findall(ta)
            sm = difflib.SequenceMatcher(None, t_o, t_n, autojunk=False)
            mod_segments = [op for op in sm.get_opcodes() if op[0] in ('delete', 'insert', 'replace')]
            change_rate = 1.0 - sm.ratio()

            if taux > threshold or change_rate > threshold or len(mod_segments) > 6:
                collab = is_collab or bool(re.search(r'#(?:ffedd5|dbeafe)', p))
                author = author_name
                m_author = re.search(r'data-author="([^"]+)"', p)
                if m_author:
                    author = m_author.group(1)

                is_quote = all(l.strip().startswith('>') for l in p.splitlines() if l.strip())

                if not tb and ta:
                    res = cls.format_ins(ta, is_collab=collab, author=author)
                elif tb and not ta:
                    res = cls.format_del(tb, is_collab=collab, author=author)
                else:
                    del_block = cls.format_del(tb, is_collab=collab, author=author)
                    ins_block = cls.format_ins(ta, is_collab=collab, author=author)
                    res = f"{del_block}\n\n{ins_block}"

                if is_quote:
                    res = "\n".join(f"> {l}" if l.strip() else ">" for l in res.splitlines())
                out_paras.append(res)
            else:
                out_paras.append(p)

        return "\n\n".join(out_paras)

    @classmethod
    def split_section_units(cls, text: str) -> List[str]:
        """
        Découpe une section Markdown en unités atomiques (paragraphes, équations KaTeX, citations, callouts, tables).
        Isole rigoureusement les blocs display math $$...$$ et préserve la granularité des paragraphes.
        """
        text = re.sub(r'([^\n])\s*(\$\$.*?\$\$)', r'\1\n\n\2', text, flags=re.DOTALL)
        text = re.sub(r'(\$\$.*?\$\$)\s*([^\n])', r'\1\n\n\2', text, flags=re.DOTALL)
        text = re.sub(r'([^\n])\s*(>\s*\[![A-Z]+\])', r'\1\n\n\2', text)

        raw = re.split(r'\n\s*\n+', text.strip())
        units = []
        i = 0
        while i < len(raw):
            u = raw[i].strip()
            if not u:
                i += 1
                continue
            while u.count('$$') % 2 != 0 and i + 1 < len(raw):
                i += 1
                u = u + '\n\n' + raw[i].strip()

            # Scinder les citations multi-paragraphes (ex: abstract) séparées par >\n
            if u.startswith('>') and not re.match(r'^>\s*\[![A-Z]+\]', u) and re.search(r'\n>\s*\n', u):
                sub_quotes = re.split(r'\n>\s*\n', u)
                for sq in sub_quotes:
                    sq_s = sq.strip()
                    if sq_s:
                        units.append(sq_s)
            else:
                units.append(u)
            i += 1
        return units

    @classmethod
    def get_unit_type(cls, u: str) -> str:
        """Détermine la nature structurelle d'une unité Markdown."""
        if u.startswith('$$') and u.endswith('$$'):
            return 'math'
        if u.startswith('|') and '|' in u[1:]:
            return 'table'
        if re.match(r'^\s*!\[.*?\]\(.*?\)\s*$', u) or re.match(r'^\s*!\[\[.*?\]\]\s*$', u):
            return 'image'
        if re.match(r'^>\s*\[![A-Z]+\]', u):
            return 'callout'
        if u.startswith('>'):
            return 'quote'
        if u.startswith('#'):
            return 'heading'
        return 'paragraph'

    @classmethod
    def align_section_units(
        cls,
        u_old: List[str],
        u_new: List[str]
    ) -> List[Tuple[str, Optional[int], Optional[int]]]:
        """
        Aligne les unités atomiques de deux sections par programmation dynamique monotone.
        Garantit que les suppressions précèdent toujours les ajouts lors des substitutions non-alignées.
        """
        n, m = len(u_old), len(u_new)
        dp = [[0.0] * (m + 1) for _ in range(n + 1)]
        back = [[(0, 0)] * (m + 1) for _ in range(n + 1)]

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                t_old = cls.get_unit_type(u_old[i-1])
                t_new = cls.get_unit_type(u_new[j-1])

                sim = 0.0
                if t_old == t_new:
                    if u_old[i-1] == u_new[j-1]:
                        sim = 2.0
                    elif t_old == 'math':
                        ratio = difflib.SequenceMatcher(None, u_old[i-1], u_new[j-1], autojunk=False).ratio()
                        if ratio >= 0.35:
                            sim = 1.0 + ratio
                    elif t_old in ('quote', 'paragraph', 'callout', 'image'):
                        ratio = difflib.SequenceMatcher(None, u_old[i-1], u_new[j-1], autojunk=False).ratio()
                        if ratio >= 0.20:
                            sim = ratio

                best_val = dp[i-1][j]
                best_choice = (i-1, j)

                if dp[i][j-1] > best_val:
                    best_val = dp[i][j-1]
                    best_choice = (i, j-1)

                if sim > 0.0 and dp[i-1][j-1] + sim > best_val:
                    best_val = dp[i-1][j-1] + sim
                    best_choice = (i-1, j-1)

                dp[i][j] = best_val
                back[i][j] = best_choice

        raw_alignment = []
        curr_i, curr_j = n, m
        while curr_i > 0 or curr_j > 0:
            prev_i, prev_j = back[curr_i][curr_j]
            if prev_i == curr_i - 1 and prev_j == curr_j - 1:
                raw_alignment.append(('pair', curr_i - 1, curr_j - 1))
            elif prev_i == curr_i - 1 and prev_j == curr_j:
                raw_alignment.append(('delete', curr_i - 1, None))
            elif prev_i == curr_i and prev_j == curr_j - 1:
                raw_alignment.append(('insert', None, curr_j - 1))
            else:
                break
            curr_i, curr_j = prev_i, prev_j
        raw_alignment.reverse()

        # Réorganiser pour que les suppressions précèdent strictement les insertions
        ordered = []
        idx = 0
        while idx < len(raw_alignment):
            if raw_alignment[idx][0] == 'pair':
                ordered.append(raw_alignment[idx])
                idx += 1
            else:
                chunk = []
                while idx < len(raw_alignment) and raw_alignment[idx][0] in ('delete', 'insert'):
                    chunk.append(raw_alignment[idx])
                    idx += 1
                dels = [op for op in chunk if op[0] == 'delete']
                inss = [op for op in chunk if op[0] == 'insert']
                ordered.extend(dels)
                ordered.extend(inss)
        return ordered

    @classmethod
    def word_diff_single_unit(
        cls,
        u_old: str,
        u_new: str,
        is_collab: bool = False,
        author_name: str = ""
    ) -> Tuple[str, int, int, int, int]:
        """Effectue une comparaison mot à mot chirurgicale au sein d'une unique unité textuelle."""
        token_pattern = re.compile(
            r'\$\$.*?\$\$|(?<!\$)\$(?!\$)(?:\\.|[^\$\\\n])+(?<!\$)\$(?!\$)|<!--.*?-->|'
            r'(?<!`)`{3}(?!`)(?:[^`\n]|`{1,2}(?!`))+`{3}(?!`)|(?<!`)`{2}(?!`)(?:[^`\n]|`(?!=`))+`{2}(?!`)|(?<!`)`[^`\n]+`(?!`)|'
            r'\s+|\w+|[^\w\s]',
            re.DOTALL | re.UNICODE
        )

        old_is_q = all(l.strip().startswith('>') for l in u_old.splitlines() if l.strip())
        new_is_q = all(l.strip().startswith('>') for l in u_new.splitlines() if l.strip())

        clean_old = "\n".join(re.sub(r'^>+\s*', '', l) for l in u_old.splitlines()) if old_is_q else u_old
        clean_new = "\n".join(re.sub(r'^>+\s*', '', l) for l in u_new.splitlines()) if new_is_q else u_new

        tok_old = token_pattern.findall(clean_old)
        tok_new = token_pattern.findall(clean_new)

        matcher = difflib.SequenceMatcher(None, tok_old, tok_new, autojunk=False)
        parts = []
        local_add = local_del = collab_add = collab_del = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                parts.append("".join(tok_new[j1:j2]))
            elif tag == 'delete':
                chk = "".join(tok_old[i1:i2])
                if cls.has_substantive_words(chk):
                    if is_collab:
                        collab_del += 1
                    else:
                        local_del += 1
                    parts.append(cls.format_del(chk, is_collab=is_collab, author=author_name))
                else:
                    parts.append(chk)
            elif tag == 'insert':
                chk = "".join(tok_new[j1:j2])
                if cls.has_substantive_words(chk):
                    if is_collab:
                        collab_add += 1
                    else:
                        local_add += 1
                    parts.append(cls.format_ins(chk, is_collab=is_collab, author=author_name))
                else:
                    parts.append(chk)
            elif tag == 'replace':
                c_d = "".join(tok_old[i1:i2])
                c_i = "".join(tok_new[j1:j2])
                if cls.has_substantive_words(c_d):
                    if is_collab:
                        collab_del += 1
                    else:
                        local_del += 1
                    parts.append(cls.format_del(c_d, is_collab=is_collab, author=author_name))
                else:
                    parts.append(c_d)
                if cls.has_substantive_words(c_i):
                    if is_collab:
                        collab_add += 1
                    else:
                        local_add += 1
                    parts.append(cls.format_ins(c_i, is_collab=is_collab, author=author_name))
                else:
                    parts.append(c_i)

        res = "".join(parts)
        if old_is_q and new_is_q:
            res = "\n".join(f"> {l}" if l.strip() else ">" for l in res.splitlines())
        return res, local_add, local_del, collab_add, collab_del

    @classmethod
    def diff_unit_pair(
        cls,
        u_old: str,
        u_new: str,
        is_collab: bool = False,
        author_name: str = "",
        threshold: float = PARAGRAPH_BLOCK_DIFF_THRESHOLD
    ) -> Tuple[str, int, int, int, int]:
        """Compare une paire d'unités appariées, appliquant le mode bloc si le taux de modification dépasse le seuil."""
        if u_old.strip() == u_new.strip():
            return u_new, 0, 0, 0, 0

        t_old = cls.get_unit_type(u_old)
        t_new = cls.get_unit_type(u_new)

        if t_old == 'image' and t_new == 'image':
            clean_img = u_new.strip()
            clean_img = re.sub(
                r'!\[(.*?)\]\((.*?)\)',
                lambda m: f"![{re.sub(r'</?(?:ins|del|span)\b[^>]*>', '', m.group(1))}]({m.group(2)})",
                clean_img
            )
            return clean_img, 0, 0, 0, 0

        if t_old == 'math' and t_new == 'math':
            l_add = 0 if is_collab else 1
            l_del = 0 if is_collab else 1
            c_add = 1 if is_collab else 0
            c_del = 1 if is_collab else 0
            return f"{u_old.strip()}\n\n{u_new.strip()}", l_add, l_del, c_add, c_del

        clean_old = re.sub(r'^>+\s*', '', u_old, flags=re.MULTILINE)
        clean_new = re.sub(r'^>+\s*', '', u_new, flags=re.MULTILINE)
        w_old = re.findall(r'\b\w+\b', clean_old)
        w_new = re.findall(r'\b\w+\b', clean_new)

        tok_re = re.compile(
            r'\$\$.*?\$\$|(?<!\$)\$(?!\$)(?:\\.|[^\$\\\n])+(?<!\$)\$(?!\$)|<!--.*?-->|'
            r'(?<!`)`{3}(?!`)(?:[^`\n]|`{1,2}(?!`))+`{3}(?!`)|(?<!`)`{2}(?!`)(?:[^`\n]|`(?!=`))+`{2}(?!`)|(?<!`)`[^`\n]+`(?!`)|'
            r'\s+|\w+|[^\w\s]',
            re.DOTALL | re.UNICODE
        )
        t_o = tok_re.findall(clean_old)
        t_n = tok_re.findall(clean_new)
        m = difflib.SequenceMatcher(None, t_o, t_n, autojunk=False)
        opcodes = m.get_opcodes()
        mod_segments = [op for op in opcodes if op[0] in ('delete', 'insert', 'replace')]
        change_rate = 1.0 - m.ratio()

        del_w = sum(len(re.findall(r'\b\w+\b', "".join(t_o[i1:i2]))) for tag, i1, i2, j1, j2 in opcodes if tag in ('delete', 'replace'))
        ins_w = sum(len(re.findall(r'\b\w+\b', "".join(t_n[j1:j2]))) for tag, i1, i2, j1, j2 in opcodes if tag in ('insert', 'replace'))
        total_w = len(w_old) + len(w_new)
        rate = (del_w + ins_w) / total_w if total_w > 0 else 0.0

        if change_rate > threshold or rate > threshold or len(mod_segments) > 6:
            del_b = cls.format_del(u_old, is_collab=is_collab, author=author_name)
            ins_b = cls.format_ins(u_new, is_collab=is_collab, author=author_name)
            l_del = 0 if is_collab else len([l for l in u_old.splitlines() if cls.has_substantive_words(l)])
            l_add = 0 if is_collab else len([l for l in u_new.splitlines() if cls.has_substantive_words(l)])
            c_del = len([l for l in u_old.splitlines() if cls.has_substantive_words(l)]) if is_collab else 0
            c_add = len([l for l in u_new.splitlines() if cls.has_substantive_words(l)]) if is_collab else 0
            return f"{del_b}\n\n{ins_b}", l_add, l_del, c_add, c_del
        else:
            return cls.word_diff_single_unit(u_old, u_new, is_collab=is_collab, author_name=author_name)

    @classmethod
    def diff_section_lines(
        cls,
        old_lines: List[str],
        new_lines: List[str],
        is_collab: bool = False,
        author_name: str = "",
        head_lines: Optional[List[str]] = None,
        in_callout_diff: bool = False,
        block_diff_threshold: float = PARAGRAPH_BLOCK_DIFF_THRESHOLD
    ) -> Tuple[List[str], int, int, int, int]:
        """
        Compare chirurgicalement les lignes d'une section spécifique par alignement unitaire paragraphe par paragraphe.
        Retourne : (clean_lines, local_add, local_del, collab_add, collab_del)
        """
        old_text = "\n".join(old_lines)
        new_text = "\n".join(new_lines)

        if old_text.strip() == new_text.strip():
            return list(new_lines), 0, 0, 0, 0

        if not cls.has_substantive_words(old_text) and not cls.has_substantive_words(new_text):
            return list(new_lines), 0, 0, 0, 0

        # Masquage atomique des tables
        old_masked, old_tables = cls.mask_tables_in_text(old_text)
        new_masked, new_tables = cls.mask_tables_in_text(new_text)

        u_old = cls.split_section_units(old_masked)
        u_new = cls.split_section_units(new_masked)

        aligned = cls.align_section_units(u_old, u_new)

        res_parts = []
        tot_l_add = tot_l_del = tot_c_add = tot_c_del = 0

        for op, i, j in aligned:
            if op == 'pair':
                p_str, la, ld, ca, cd = cls.diff_unit_pair(u_old[i], u_new[j], is_collab=is_collab, author_name=author_name, threshold=block_diff_threshold)
                res_parts.append(p_str)
                tot_l_add += la
                tot_l_del += ld
                tot_c_add += ca
                tot_c_del += cd
            elif op == 'delete':
                if cls.get_unit_type(u_old[i]) == 'math':
                    res_parts.append(u_old[i].strip())
                else:
                    res_parts.append(cls.format_del(u_old[i], is_collab=is_collab, author=author_name))
                cnt = len([l for l in u_old[i].splitlines() if cls.has_substantive_words(l)])
                if is_collab:
                    tot_c_del += cnt
                else:
                    tot_l_del += cnt
            elif op == 'insert':
                if cls.get_unit_type(u_new[j]) == 'math':
                    res_parts.append(u_new[j].strip())
                else:
                    res_parts.append(cls.format_ins(u_new[j], is_collab=is_collab, author=author_name))
                cnt = len([l for l in u_new[j].splitlines() if cls.has_substantive_words(l)])
                if is_collab:
                    tot_c_add += cnt
                else:
                    tot_l_add += cnt

        diff_text = "\n\n".join(res_parts)
        for tok, tbl in new_tables.items():
            diff_text = diff_text.replace(tok, tbl)

        diff_text = cls.sanitize_katex_in_diff(diff_text)
        diff_text = cls.sanitize_inline_code_in_diff(diff_text)
        diff_text = re.sub(
            r'!\[(.*?)\]\((.*?)\)',
            lambda m: f"![{re.sub(r'</?(?:ins|del|span)\b[^>]*>', '', m.group(1))}]({m.group(2)})",
            diff_text
        )

        raw_lines = diff_text.splitlines()
        clean_lines = cls.sanitize_table_pipes_in_diff(raw_lines)
        return clean_lines, tot_l_add, tot_l_del, tot_c_add, tot_c_del

    @classmethod
    def generate_diff_annotated_body(
        cls,
        old_text: str,
        new_text: str,
        is_collab: bool = False,
        author_name: str = "",
        head_text: Optional[str] = None,
        block_diff_threshold: float = PARAGRAPH_BLOCK_DIFF_THRESHOLD
    ) -> Tuple[str, str, int, List[str]]:
        """
        Découpe en sections AST et produit le corps annoté ainsi que la Tree TOC.
        Retourne : (annotated_body, tree_toc, total_diff_count, modified_sections).
        """
        old_sections = cls.split_into_sections(old_text)
        new_sections = cls.split_into_sections(new_text)

        old_sec_map: Dict[str, List[SectionBlock]] = {}
        for sec in old_sections:
            norm = sec.normalized_title
            old_sec_map.setdefault(norm, []).append(sec)

        used_old_secs: Set[SectionBlock] = set()
        total_diff_count = 0
        section_stats: Dict[str, Dict[str, int]] = {}
        annotated_document_lines: List[str] = []

        for new_sec in new_sections:
            norm = new_sec.normalized_title
            matching_old = cls.find_matching_section(norm, old_sec_map, used_old_secs)
            if matching_old is None and new_sec is new_sections[0] and old_sections and old_sections[0] not in used_old_secs:
                # Alignement systématique de l'en-tête / préambule initial pour éviter tout faux delta
                matching_old = old_sections[0]

            if matching_old:
                used_old_secs.add(matching_old)

            sec_display_name = new_sec.title if new_sec.title != "Préambule" else "Introduction & Préambule"
            if new_sec.heading:
                annotated_document_lines.append(new_sec.heading)
                annotated_document_lines.append("")

            b_lines = matching_old.lines if matching_old is not None else []
            c_lines = new_sec.lines

            sec_lines, l_add, l_del, c_add, c_del = cls.diff_section_lines(
                b_lines, c_lines,
                is_collab=is_collab,
                author_name=author_name,
                block_diff_threshold=block_diff_threshold
            )
            annotated_document_lines.extend(sec_lines)
            annotated_document_lines.append("")

            diff_cnt = l_add + l_del + c_add + c_del
            if diff_cnt > 0:
                total_diff_count += diff_cnt
                section_stats[sec_display_name] = {
                    "local_add": l_add,
                    "local_del": l_del,
                    "collab_add": c_add,
                    "collab_del": c_del
                }

        # Traiter sections supprimées
        for old_sec in old_sections:
            if old_sec not in used_old_secs and old_sec.title != "Préambule":
                if not cls.has_substantive_words("\n".join(old_sec.lines)):
                    continue
                del_count = len([l for l in old_sec.lines if cls.has_substantive_words(l)])
                if del_count > 0:
                    total_diff_count += del_count

        # Génération Tree TOC
        tree_lines = []
        if total_diff_count > 0 and section_stats:
            sec_items = list(section_stats.items())
            for idx, (sec_name, stats) in enumerate(sec_items):
                is_last = (idx == len(sec_items) - 1)
                branch = "└──" if is_last else "├──"
                anchor = re.sub(r'[^a-zA-Z0-9\s\-]+', '', sec_name).strip().lower().replace(' ', '-')

                l_add = stats.get("local_add", 0)
                l_del = stats.get("local_del", 0)
                c_add = stats.get("collab_add", 0)
                c_del = stats.get("collab_del", 0)

                stat_parts = []
                if l_add > 0:
                    stat_parts.append(f"🟢 +{l_add}")
                if l_del > 0:
                    stat_parts.append(f"🔴 -{l_del}")
                if c_add > 0:
                    stat_parts.append(f"🔵 +{c_add}")
                if c_del > 0:
                    stat_parts.append(f"🟠 -{c_del}")

                stat_str = " / ".join(stat_parts) if stat_parts else "0 delta"
                tree_lines.append(f"> {branch} 📍 **[{sec_name}](#{anchor})** *({stat_str})*<br>")
        else:
            valid_secs = [s for s in new_sections if s.title != "Préambule" and (s.heading or cls.has_substantive_words("\n".join(s.lines)))]
            for idx, sec in enumerate(valid_secs):
                is_last = (idx == len(valid_secs) - 1)
                branch = "└──" if is_last else "├──"
                sec_name = sec.title if sec.title != "Préambule" else "Introduction & Préambule"
                anchor = re.sub(r'[^a-zA-Z0-9\s\-]+', '', sec_name).strip().lower().replace(' ', '-')
                tree_lines.append(f"> {branch} 📍 **[{sec_name}](#{anchor})**<br>")

        tree_toc = "\n".join(tree_lines)
        annotated_body = "\n".join(annotated_document_lines)
        annotated_body = re.sub(r'\n{3,}', '\n\n', annotated_body).strip()
        annotated_body = cls.sanitize_katex_in_diff(annotated_body)

        return annotated_body, tree_toc, total_diff_count, list(section_stats.keys())

    @classmethod
    def validate_revisions_up_to_line(cls, text: str, commit_line: int) -> Tuple[str, int, int]:
        """
        Valide chirurgicalement les révisions antérieures à commit_line (1-indexed).
        Retourne : (updated_text, validated_count, remaining_count).
        """
        lines = text.splitlines()
        validated_lines: List[str] = []
        in_deleted_callout = False
        val_count = 0
        rem_count = 0

        for idx, line in enumerate(lines):
            line_num = idx + 1
            if line_num < commit_line:
                s = line.strip()
                if s.startswith("> [!CAUTION]") and "🔴 Section Supprimée" in s:
                    in_deleted_callout = True
                    val_count += 1
                    continue
                if in_deleted_callout:
                    if s.startswith(">") or not s:
                        continue
                    else:
                        in_deleted_callout = False

                ins_matches = re.findall(r'<ins\b[^>]*>(.*?)</ins>|<span\b[^>]*style="[^"]*#(?:dcfce7|dbeafe)[^"]*"[^>]*>(.*?)</span>', line, flags=re.DOTALL)
                del_matches = re.findall(r'<del\b[^>]*>(.*?)</del>|<span\b[^>]*style="[^"]*#(?:fee2e2|ffedd5)[^"]*"[^>]*>(.*?)</span>', line, flags=re.DOTALL)
                val_count += (len(ins_matches) + len(del_matches))

                clean_line = re.sub(r'<del\b[^>]*>.*?</del>', '', line)
                clean_line = re.sub(r'<span\b[^>]*style="[^"]*#(?:fee2e2|ffedd5)[^"]*"[^>]*>.*?</span>', '', clean_line)
                clean_line = re.sub(r'<ins\b[^>]*>(.*?)</ins>', r'\1', clean_line)
                clean_line = re.sub(r'<span\b[^>]*style="[^"]*#(?:dcfce7|dbeafe)[^"]*"[^>]*>(.*?)</span>', r'\1', clean_line)
                clean_line = re.sub(r'</?span[^>]*>', '', clean_line)
                clean_line = re.sub(r'[ \t]{2,}', ' ', clean_line)
                validated_lines.append(clean_line)
            else:
                in_deleted_callout = False
                ins_matches = re.findall(r'<ins\b[^>]*>(.*?)</ins>|<span\b[^>]*style="[^"]*#(?:dcfce7|dbeafe)[^"]*"[^>]*>(.*?)</span>', line, flags=re.DOTALL)
                del_matches = re.findall(r'<del\b[^>]*>(.*?)</del>|<span\b[^>]*style="[^"]*#(?:fee2e2|ffedd5)[^"]*"[^>]*>(.*?)</span>', line, flags=re.DOTALL)
                rem_count += (len(ins_matches) + len(del_matches))
                validated_lines.append(line)

        updated_text = "\n".join(validated_lines)
        return updated_text, val_count, rem_count

    @classmethod
    def extract_paragraph_diff_texts(cls, para: str) -> Tuple[str, str]:
        """Extrait (text_before, text_after) d'un bloc avec diff inline."""
        cleaned = re.sub(
            r'(?:^>*\s*)?<span\b[^>]*>(?:🛡️|🚨|⚠️)\s*(?:Score IA|P\(AI\))\s*:?.*?</span>\s*',
            '',
            para,
            flags=re.MULTILINE
        )

        tb = cleaned
        tb = re.sub(r'<ins\b[^>]*>.*?</ins>', '', tb, flags=re.DOTALL)
        tb = re.sub(r'<span\b[^>]*style="[^"]*#(?:dcfce7|dbeafe)[^"]*"[^>]*>.*?</span>', '', tb, flags=re.DOTALL)
        tb = re.sub(r'<del\b[^>]*>(.*?)</del>', r'\1', tb, flags=re.DOTALL)
        tb = re.sub(r'<span\b[^>]*style="[^"]*#(?:fee2e2|ffedd5)[^"]*"[^>]*>(.*?)</span>', r'\1', tb, flags=re.DOTALL)
        tb = re.sub(r'</?(?:span|del|ins|br)\b[^>]*>', '', tb)
        tb = re.sub(r'\n+', ' ', tb)
        tb = re.sub(r'[ \t]{2,}', ' ', tb).strip()

        ta = cleaned
        ta = re.sub(r'<del\b[^>]*>.*?</del>', '', ta, flags=re.DOTALL)
        ta = re.sub(r'<span\b[^>]*style="[^"]*#(?:fee2e2|ffedd5)[^"]*"[^>]*>(.*?)</span>', '', ta, flags=re.DOTALL)
        ta = re.sub(r'<ins\b[^>]*>(.*?)</ins>', r'\1', ta, flags=re.DOTALL)
        ta = re.sub(r'<span\b[^>]*style="[^"]*#(?:dcfce7|dbeafe)[^"]*"[^>]*>(.*?)</span>', r'\1', ta, flags=re.DOTALL)
        ta = re.sub(r'</?(?:span|del|ins|br)\b[^>]*>', '', ta)
        ta = re.sub(r'\n+', ' ', ta)
        ta = re.sub(r'[ \t]{2,}', ' ', ta).strip()

        return tb, ta
