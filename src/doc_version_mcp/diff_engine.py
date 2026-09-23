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
                curr_heading = line
                curr_level = len(match.group(1))
                raw_t = match.group(2).strip()
                for _ in range(5):
                    raw_t = re.sub(r'\\(?:textsf|textsc|textup|textmd|textrm|textnormal|text|underline)\{((?:[^{}]|{[^{}]*})*)\}', r'\1', raw_t)
                    raw_t = re.sub(r'\\textbf\{((?:[^{}]|{[^{}]*})*)\}', r'\1', raw_t)
                    raw_t = re.sub(r'\\(?:textit|emph|textsl)\{((?:[^{}]|{[^{}]*})*)\}', r'\1', raw_t)
                    raw_t = re.sub(r'\\texttt\{((?:[^{}]|{[^{}]*})*)\}', r'`\1`', raw_t)
                raw_t = re.sub(r'\\label\{[^}]+\}', '', raw_t).strip()
                raw_t = re.sub(r'^\*\*(.*?)\*\*$', r'\1', raw_t).strip()
                raw_t = re.sub(r'\s+', ' ', raw_t).strip()
                curr_title = raw_t
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

        # Espacements et sauts
        text = re.sub(r'\\label\{[^}]+\}', '', text)
        text = re.sub(r'\\(?:centering|noindent|frenchspacing|medskip|bigskip|smallskip|clearpage|newpage|vfill|hfill|raggedleft|raggedright)\b', '', text)
        text = re.sub(r'\\needspace(?:\{[^{}]*\}|\[[^\]]*\])?', '', text)
        text = re.sub(r'\\(?:vspace|hspace|setlength|addtolength)\*?\{[^}]*\}(?:\{[^}]*\})?', '', text)
        text = re.sub(r'\\(?:toprule|midrule|bottomrule|hline|addlinespace|cmidrule(?:\[[^\]]*\])?\{[^}]*\})', '', text)
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
        text = re.sub(r'\\(?:color|rowcolor|columncolor|cellcolor|arrayrulecolor)(?:\[[^\]]*\])?(?:\{[^{}]*\}|\s+[a-zA-Z0-9!_]+)?', '', text)
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
        text = re.sub(r'\\(?:bibliography|bibliographystyle)(?:\{[^}]*\}|[a-zA-Z0-9_-]+)?', '', text)

        text = re.sub(r'\\xspace\s*([,.:;!?\'"\)\}\]])', r'\1', text)
        text = re.sub(r'\\xspace\b\s*', ' ', text)
        text = text.replace('~', ' ').replace(r'\,', ' ').replace(r'\&', '&').replace(r'\_', '_').replace(r'\#', '#').replace(r'\%', '%')
        text = re.sub(r'(?<![\n:|\-])---(?![\n:|\-])', '—', text)
        text = re.sub(r'(?<![\n:|\-])--(?![\n:|\-])', '–', text)
        text = re.sub(r'\\+\s*$', '', text, flags=re.MULTILINE)
        text = re.sub(r'\\+\s*\|', '|', text)

        # Nettoyage des accolades résiduelles de groupement AVANT de restaurer math_map
        for _ in range(3):
            text = re.sub(r'(?<![\\\$a-zA-Z0-9_])\{([^{}]*)\}', r'\1', text)

        # Nettoyage des accolades fermantes orphelines
        text = re.sub(r'\*\*\}([ \t]*)', '** ', text)
        text = re.sub(r'\*\}\b', '* ', text)

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
        text = re.sub(r'</?span[^>]*>', '', text)

        lines = text.splitlines()
        clean_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith(('> [!CAUTION]', '> [!FAILURE]', '> [!FAIL]', '> [!DANGER]')):
                continue
            clean_lines.append(line)

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

        # 1. Nettoyer les balises de diff parasites collées directement aux délimiteurs $$
        text = re.sub(r'</?(?:ins|del|span)\b[^>]*>\s*\$\$\s*</?(?:ins|del|span)\b[^>]*>', '\n\n$$\n\n', text)
        text = re.sub(r'</?(?:ins|del|span)\b[^>]*>\s*\$\$', '\n\n$$\n\n', text)
        text = re.sub(r'\$\$\s*</?(?:ins|del|span)\b[^>]*>', '\n\n$$\n\n', text)

        # 2. Supprimer les délimiteurs $$ consécutifs vides résultant de collages
        text = re.sub(r'\$\$\s*\$\$', '', text)

        # 3. Pour chaque bloc $$...$$, isoler les $$ sur leurs propres lignes et éliminer tout tag HTML intérieur
        def clean_display_math(match):
            inner = match.group(1)
            clean_inner = re.sub(r'</?(?:ins|del|span)\b[^>]*>', '', inner)
            clean_inner = clean_inner.strip()
            return f"\n\n$$\n{clean_inner}\n$$\n\n"

        text = re.sub(r'\$\$(.*?)\$\$', clean_display_math, text, flags=re.DOTALL)

        # 4. Nettoyer les sauts de ligne excessifs autour des blocs math
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text

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
    def diff_section_lines(
        cls,
        old_lines: List[str],
        new_lines: List[str],
        is_collab: bool = False,
        author_name: str = "",
        head_lines: Optional[List[str]] = None
    ) -> Tuple[List[str], int, int, int, int]:
        """
        Compare chirurgicalement les lignes d'une section spécifique via difflib.SequenceMatcher(autojunk=False).
        Retourne : (clean_lines, local_add, local_del, collab_add, collab_del)
        """
        old_text = "\n".join(old_lines)
        new_text = "\n".join(new_lines)
        head_text = "\n".join(head_lines) if head_lines is not None else None

        if old_text.strip() == new_text.strip():
            return list(new_lines), 0, 0, 0, 0

        if not cls.has_substantive_words(old_text) and not cls.has_substantive_words(new_text):
            return list(new_lines), 0, 0, 0, 0

        if not old_text.strip() or not cls.has_substantive_words(old_text):
            if not cls.has_substantive_words(new_text):
                return list(new_lines), 0, 0, 0, 0
            new_masked, new_tables = cls.mask_tables_in_text(new_text)
            new_masked, new_figures = cls.mask_figures_in_text(new_masked)
            blocks = re.split(r'(\n\s*\n+)', new_masked)
            out_blocks = []
            loc_add = 0
            col_add = 0
            for b in blocks:
                if not b.strip() or re.match(r'^\s*#{1,6}\s', b) or any(tok in b for tok in list(new_tables.keys()) + list(new_figures.keys())):
                    out_blocks.append(b)
                elif cls.has_substantive_words(b):
                    if is_collab:
                        col_add += 1
                        out_blocks.append(cls.format_ins(b, is_collab=True, author=author_name))
                    else:
                        loc_add += 1
                        out_blocks.append(cls.format_ins(b, is_collab=False, author="agent"))
                else:
                    out_blocks.append(b)
            res_text = "".join(out_blocks)
            for tok, tbl in new_tables.items():
                res_text = res_text.replace(tok, tbl)
            for tok, fig in new_figures.items():
                res_text = res_text.replace(tok, fig)
            res_text = cls.sanitize_katex_in_diff(res_text)
            return res_text.splitlines(), max(1, loc_add) if (loc_add > 0 or col_add == 0) else 0, 0, col_add, 0

        if not new_text.strip() or not cls.has_substantive_words(new_text):
            del_count = len([l for l in old_lines if cls.has_substantive_words(l)])
            if is_collab:
                formatted_del = cls.format_del(old_text, is_collab=True, author=author_name)
                formatted_del = cls.sanitize_katex_in_diff(formatted_del)
                return formatted_del.splitlines(), 0, 0, 0, del_count
            else:
                formatted_del = cls.format_del(old_text, is_collab=False, author="agent")
                formatted_del = cls.sanitize_katex_in_diff(formatted_del)
                return formatted_del.splitlines(), 0, del_count, 0, 0

        # Isolation des tables et figures
        old_masked, old_tables = cls.mask_tables_in_text(old_text)
        new_masked, new_tables = cls.mask_tables_in_text(new_text)
        old_masked, old_figures = cls.mask_figures_in_text(old_masked)
        new_masked, new_figures = cls.mask_figures_in_text(new_masked)

        token_pattern = re.compile(
            r'___MD_TABLE_[A-Z0-9_]+___|___MD_FIGURE_[A-Z0-9_]+___|\$\$.*?\$\$|(?<!\$)\$(?!\$)(?:\\.|[^\$\\\n])+(?<!\$)\$(?!\$)|<!--.*?-->|\s+|\w+|[^\w\s]',
            re.DOTALL | re.UNICODE
        )
        old_tokens = token_pattern.findall(old_masked)
        new_tokens = token_pattern.findall(new_masked)

        matcher = difflib.SequenceMatcher(None, old_tokens, new_tokens, autojunk=False)
        result_parts: List[str] = []
        local_add = 0
        local_del = 0
        collab_add = 0
        collab_del = 0

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                result_parts.append("".join(new_tokens[j1:j2]))
            elif tag == 'delete':
                del_chunk = "".join(old_tokens[i1:i2])
                if cls.has_substantive_words(del_chunk):
                    if is_collab:
                        collab_del += 1
                        result_parts.append(cls.format_del(del_chunk, is_collab=True, author=author_name))
                    else:
                        local_del += 1
                        result_parts.append(cls.format_del(del_chunk, is_collab=False, author="agent"))
            elif tag == 'insert':
                add_chunk = "".join(new_tokens[j1:j2])
                if cls.has_substantive_words(add_chunk):
                    if is_collab:
                        collab_add += 1
                        result_parts.append(cls.format_ins(add_chunk, is_collab=True, author=author_name))
                    else:
                        local_add += 1
                        result_parts.append(cls.format_ins(add_chunk, is_collab=False, author="agent"))
                else:
                    result_parts.append(add_chunk)
            elif tag == 'replace':
                del_chunk = "".join(old_tokens[i1:i2])
                add_chunk = "".join(new_tokens[j1:j2])
                if cls.has_substantive_words(del_chunk):
                    if is_collab:
                        collab_del += 1
                        result_parts.append(cls.format_del(del_chunk, is_collab=True, author=author_name))
                    else:
                        local_del += 1
                        result_parts.append(cls.format_del(del_chunk, is_collab=False, author="agent"))
                if cls.has_substantive_words(add_chunk):
                    if is_collab:
                        collab_add += 1
                        result_parts.append(cls.format_ins(add_chunk, is_collab=True, author=author_name))
                    else:
                        local_add += 1
                        result_parts.append(cls.format_ins(add_chunk, is_collab=False, author="agent"))
                else:
                    result_parts.append(add_chunk)

        diff_text = "".join(result_parts)
        for t_tok, t_str in new_tables.items():
            diff_text = diff_text.replace(t_tok, t_str)
        for f_tok, f_str in new_figures.items():
            diff_text = diff_text.replace(f_tok, f_str)

        diff_text = cls.sanitize_katex_in_diff(diff_text)
        raw_lines = diff_text.splitlines()
        clean_lines = cls.sanitize_table_pipes_in_diff(raw_lines)
        return clean_lines, local_add, local_del, collab_add, collab_del

    @classmethod
    def generate_diff_annotated_body(
        cls,
        old_text: str,
        new_text: str,
        is_collab: bool = False,
        author_name: str = "",
        head_text: Optional[str] = None
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
                author_name=author_name
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
