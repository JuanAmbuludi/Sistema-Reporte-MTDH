"""Dynamic export API used by the Streamlit report studio."""
from .context import build_report_context


def generate_xlsx(context):
    from .excel import generate_xlsx as generate
    return generate(context)


def table_xlsx(rows, layout, **options):
    from .excel import table_xlsx as build
    return build(rows, layout, **options)


def generate_pdf(context):
    from .pdf import generate_pdf as generate
    return generate(context)


def generate_docx(context):
    from .word import generate_docx as generate
    return generate(context)


def generate_pptx(context):
    from .pptx import generate_pptx as generate
    return generate(context)


__all__ = ["build_report_context", "generate_xlsx", "generate_pdf", "generate_docx", "generate_pptx", "table_xlsx"]
