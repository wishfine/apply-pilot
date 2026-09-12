"""Multi-format resume text extractors for PDF and LaTeX files."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Protocol, runtime_checkable

import pypdf


@runtime_checkable
class TextExtractor(Protocol):
    """Protocol for extracting raw textual content from resume files."""

    def extract_text(self, file_path: Path) -> str:
        """Extract text from the given file path."""
        ...


class PdfExtractor:
    """Extracts raw text from PDF resume documents using pypdf."""

    def extract_text(self, file_path: Path) -> str:
        """Extract and normalize text content from all pages of a PDF file.

        Args:
            file_path: Path to the target PDF file.

        Returns:
            Cleaned and normalized text representation.

        Raises:
            FileNotFoundError: If the target PDF file does not exist.
            ValueError: If the PDF document is encrypted or corrupted.
        """
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"PDF file not found at: {path}")

        pages_text: list[str] = []
        with open(path, "rb") as f:
            try:
                reader = pypdf.PdfReader(f)
                if reader.is_encrypted:
                    raise ValueError(f"Cannot read password-protected PDF: {path}")
                for page in reader.pages:
                    try:
                        extracted = page.extract_text()
                        if extracted:
                            pages_text.append(extracted)
                    except Exception:
                        continue
            except pypdf.errors.PdfReadError as e:
                raise ValueError(f"Invalid or corrupted PDF document: {path}") from e

        raw_text = "\n\n".join(pages_text)
        return self._normalize_whitespace(raw_text)

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Normalize excessive whitespace while preserving meaningful line breaks."""
        lines = []
        for line in text.splitlines():
            cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
            lines.append(cleaned_line)

        joined = "\n".join(lines)
        # Collapse 3 or more consecutive newlines into double newlines
        collapsed = re.sub(r"\n{3,}", "\n\n", joined)
        return collapsed.strip()


class TexExtractor:
    """Extracts clean semantic text from LaTeX (.tex) resume sources."""

    def extract_text(self, file_path: Path) -> str:
        """Extract and clean text content from a LaTeX file.

        Strips LaTeX comments, formatting macros, environment wrappers, and styling
        tags while preserving candidate facts, structures, and content.

        Args:
            file_path: Path to the target LaTeX file.

        Returns:
            Cleaned text representation without LaTeX markup.

        Raises:
            FileNotFoundError: If the target .tex file does not exist.
        """
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"LaTeX file not found at: {path}")

        raw_tex = path.read_text(encoding="utf-8")
        return self.clean_latex(raw_tex)

    @classmethod
    def clean_latex(cls, text: str) -> str:
        """Clean LaTeX source text into readable plain text."""
        # 1. Strip comments (ignore escaped \%)
        text = re.sub(r"(?<!\\)%.*$", "", text, flags=re.MULTILINE)

        # 2. Convert escaped symbols to raw characters
        text = text.replace(r"\%", "%")
        text = text.replace(r"\&", "&")
        text = text.replace(r"\$", "$")
        text = text.replace(r"\#", "#")
        text = text.replace(r"\_", "_")

        # 3. Strip preambles, packages, and metadata commands completely
        text = re.sub(
            r"\\(?:documentclass|usepackage|geometry|hypersetup|pagestyle|thispagestyle|setlength|titlespacing\*?|titleformat\*?)(?:\[[^\[\]]*\])?\{[^{}]*\}(?:\{[^{}]*\})?",
            "",
            text,
        )

        # 4. Unwrap environment tags
        # \begin{...} and \end{...}
        text = re.sub(r"\\(?:begin|end)\{[^{}]+\}", "\n", text)

        # 5. Handle hrefs: \href{url}{text} -> text
        text = re.sub(r"\\href(?:\[.*?\])?\{[^{}]*\}\{([^{}]*)\}", r"\1", text)

        # 6. Discard styling commands with 1 or 2 arguments: \vspace{...}, \hspace{...}, \color{...}, \fontsize{...}{...}, \rule{...}{...}
        text = re.sub(
            r"\\(?:vspace\*?|hspace\*?|color|textcolor|fontsize|linespread|rule|label|ref|pageref)(?:\[.*?\])?\{[^{}]*\}(?:\{[^{}]*\})?",
            "",
            text,
        )

        # 7. Unpack formatting and structural commands with 1 argument (preserve inner text):
        # \textbf{...}, \textit{...}, \section{...}, etc.
        # Run iteratively to handle nested macros like \textbf{\textit{text}}
        pattern_wrapper = re.compile(
            r"\\(?:textbf|textit|textsl|textsc|textmd|textup|texttt|emph|underline|section\*?|subsection\*?|subsubsection\*?|paragraph\*?|large|Large|LARGE|huge|Huge|small|footnotesize|normalsize)\*?(?:\[.*?\])?\{([^{}]*)\}"
        )
        for _ in range(5):
            new_text = pattern_wrapper.sub(r"\1", text)
            if new_text == text:
                break
            text = new_text

        # 8. Handle line breaks and spacing macros
        text = re.sub(r"\\\\(?:\[.*?\])?", "\n", text)
        text = re.sub(r"\\item\b", "• ", text)
        text = re.sub(
            r"\\(?:hfill|vfill|centering|raggedright|raggedleft|newpage|clearpage|noindent|indent|hline)\b",
            " ",
            text,
        )

        # 9. Clean up residual backslash commands like \relax, \null, \Large
        text = re.sub(r"\\[a-zA-Z]+\b", "", text)

        # 10. Strip residual grouping braces like in {\Large 张三}
        text = text.replace("{", "").replace("}", "")

        # 11. Normalize whitespace
        lines = []
        for line in text.splitlines():
            cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
            if cleaned_line:
                lines.append(cleaned_line)

        joined = "\n".join(lines)
        collapsed = re.sub(r"\n{3,}", "\n\n", joined)
        return collapsed.strip()

