import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from applypilot.modules.profile.ingestion.extractors import (
    PdfExtractor,
    TexExtractor,
    TextExtractor,
)


def test_extractor_protocol_compliance():
    pdf_ext = PdfExtractor()
    tex_ext = TexExtractor()
    assert isinstance(pdf_ext, TextExtractor)
    assert isinstance(tex_ext, TextExtractor)


def test_tex_extractor_non_existent_file(tmp_path: Path):
    extractor = TexExtractor()
    with pytest.raises(FileNotFoundError):
        extractor.extract_text(tmp_path / "missing_resume.tex")


def test_tex_extractor_cleans_macros_and_comments(tmp_path: Path):
    tex_file = tmp_path / "resume.tex"
    tex_content = r"""
    % This is a header comment that should be stripped
    \documentclass[11pt]{article}
    \usepackage{hyperref}
    \usepackage{xcolor}

    \begin{document}
    \textbf{张三} \\
    \href{mailto:zhangsan@example.com}{zhangsan@example.com} | 13800138000 | 成绩前 5\%
    \vspace{2mm}
    \section{教育经历}
    \begin{itemize}
        \item 清华大学 \hfill 计算机科学与技术 (硕士) \hfill 2023.09 - 2026.06
        \item \textit{主修课程}: 机器学习, 分布式系统
    \end{itemize}

    \section{实习经历}
    \begin{center}
    \textbf{阿里巴巴} -- 算法工程师实习生 \hfill 2024.06 - 2024.12
    \end{center}
    \begin{itemize}
        \item 负责大模型检索增强 (RAG) 系统开发与性能优化。
    \end{itemize}
    \end{document}
    """
    tex_file.write_text(tex_content, encoding="utf-8")

    extractor = TexExtractor()
    cleaned = extractor.extract_text(tex_file)

    # Comments stripped
    assert "This is a header comment" not in cleaned

    # Escaped % preserved as %
    assert "5%" in cleaned

    # Macros stripped / unwrapped
    assert "\\textbf" not in cleaned
    assert "\\textit" not in cleaned
    assert "\\href" not in cleaned
    assert "\\vspace" not in cleaned
    assert "\\section" not in cleaned
    assert "\\begin" not in cleaned
    assert "\\end" not in cleaned
    assert "\\documentclass" not in cleaned
    assert "\\usepackage" not in cleaned

    # Core content preserved
    assert "张三" in cleaned
    assert "zhangsan@example.com" in cleaned
    assert "13800138000" in cleaned
    assert "清华大学" in cleaned
    assert "计算机科学与技术" in cleaned
    assert "硕士" in cleaned
    assert "2023.09 - 2026.06" in cleaned
    assert "机器学习" in cleaned
    assert "阿里巴巴" in cleaned
    assert "算法工程师实习生" in cleaned
    assert "大模型检索增强" in cleaned


def test_pdf_extractor_non_existent_file(tmp_path: Path):
    extractor = PdfExtractor()
    with pytest.raises(FileNotFoundError):
        extractor.extract_text(tmp_path / "missing.pdf")


def test_pdf_extractor_extracts_and_normalizes_text(tmp_path: Path):
    pdf_file = tmp_path / "sample.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    mock_page_1 = MagicMock()
    mock_page_1.extract_text.return_value = "  李四  \n\n  清华大学  计算机科学与技术  \n"
    mock_page_2 = MagicMock()
    mock_page_2.extract_text.return_value = "项目经历:   RAG 问答引擎   \n\n"

    mock_reader = MagicMock()
    mock_reader.is_encrypted = False
    mock_reader.pages = [mock_page_1, mock_page_2]

    extractor = PdfExtractor()
    with patch("pypdf.PdfReader", return_value=mock_reader) as mock_pdf_reader:
        result = extractor.extract_text(pdf_file)
        assert mock_pdf_reader.call_count == 1
        assert "李四" in result
        assert "清华大学 计算机科学与技术" in result
        assert "项目经历: RAG 问答引擎" in result


def test_tex_extractor_nested_macros_and_special_escapes(tmp_path: Path):
    tex_file = tmp_path / "nested.tex"
    tex_content = r"""
    \begin{tabular}{ll}
    \textbf{\textit{重点项目}}: & \underline{智能求职代理系统} \\
    \textbf{技术栈}: & Python \& PyTorch \& FastAPI \\
    \textbf{预算}: & \$50,000 \#1 \\
    \end{tabular}
    """
    tex_file.write_text(tex_content, encoding="utf-8")

    extractor = TexExtractor()
    cleaned = extractor.extract_text(tex_file)

    assert "重点项目" in cleaned
    assert "智能求职代理系统" in cleaned
    assert "Python & PyTorch & FastAPI" in cleaned
    assert "$50,000 #1" in cleaned
    assert "\\textbf" not in cleaned
    assert "\\textit" not in cleaned
    assert "\\underline" not in cleaned


def test_pdf_extractor_empty_pages_handling(tmp_path: Path):
    pdf_file = tmp_path / "empty.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    mock_page_1 = MagicMock()
    mock_page_1.extract_text.return_value = ""
    mock_page_2 = MagicMock()
    mock_page_2.extract_text.return_value = None

    mock_reader = MagicMock()
    mock_reader.is_encrypted = False
    mock_reader.pages = [mock_page_1, mock_page_2]

    extractor = PdfExtractor()
    with patch("pypdf.PdfReader", return_value=mock_reader):
        result = extractor.extract_text(pdf_file)
        assert result == ""


def test_tex_extractor_residual_grouping_braces(tmp_path: Path):
    tex_file = tmp_path / "grouping.tex"
    tex_content = r"{\Large 张三} {\small 软件工程师}"
    tex_file.write_text(tex_content, encoding="utf-8")

    extractor = TexExtractor()
    cleaned = extractor.extract_text(tex_file)

    assert "{" not in cleaned
    assert "}" not in cleaned
    assert "张三 软件工程师" in cleaned


def test_pdf_extractor_encrypted_raises_value_error(tmp_path: Path):
    pdf_file = tmp_path / "protected.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 dummy")

    mock_reader = MagicMock()
    mock_reader.is_encrypted = True

    extractor = PdfExtractor()
    with patch("pypdf.PdfReader", return_value=mock_reader):
        with pytest.raises(ValueError, match="Cannot read password-protected PDF"):
            extractor.extract_text(pdf_file)


def test_pdf_extractor_corrupted_raises_value_error(tmp_path: Path):
    import pypdf.errors

    pdf_file = tmp_path / "corrupted.pdf"
    pdf_file.write_bytes(b"not a valid pdf content")

    extractor = PdfExtractor()
    with patch("pypdf.PdfReader", side_effect=pypdf.errors.PdfReadError("EOF marker not found")):
        with pytest.raises(ValueError, match="Invalid or corrupted PDF document"):
            extractor.extract_text(pdf_file)


