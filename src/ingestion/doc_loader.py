import os
import json
import pymupdf.layout # Always keep when using pymupdf with llm
import pymupdf4llm
from utils import root_logger


def extract_cleaned_content(pdf_path):
    """
    Extract text and markdown tables using LangChain PyMuPDFLoader.
    Returns:
        cleaned_text (str)
        unique_tables (List[pd.DataFrame])
    """
    try:
        document_text = pymupdf4llm.to_markdown(
            pdf_path,
            footer=False,
            ignore_images=True
        )
    except Exception as e:
        root_logger.exception(f"PDF load failed: {pdf_path} - {e}")
        return None
    
    lines = document_text.splitlines()
    lines_to_remove = []

    # ----------------------------------------------------------
    # STEP 1: Detect markdown table blocks and fix broken tables
    # ----------------------------------------------------------
    in_table = False
    
    for idx, line in enumerate(lines):
        if line.strip().startswith("|"):
            if not in_table:
                in_table = True
        elif bool(line.strip()) is False and in_table:
            lines_to_remove.append(idx)
        else:
            if in_table:
                in_table = False
    
    # ----------------------------------------------------------
    # STEP 2: Find and remove static footer content, pictures
    # ----------------------------------------------------------
    for idx, line in enumerate(lines):
        if line.startswith((
            "**==> picture",
            "> **हिंदी आसान है** ",
        )):
            lines_to_remove.append(idx)
    
    # ----------------------------------------------------------
    # Remove the lines marked for removal with sliding index 
    # ----------------------------------------------------------
    lines_to_remove = list(set(lines_to_remove))
    for idx, line in enumerate(lines_to_remove):
        lines.pop(line-idx)

    return "\n".join(lines)


def get_content_from_file(document, save_to_local=True):
    pdffile = document["filepath"]
    resultfile = pdffile.replace(".pdf", ".txt")
    root_logger.debug(f"Processing pdffile {pdffile}")
    
    if os.path.exists(resultfile):
        raw_text = open(resultfile).read()
    else:
        raw_text = extract_cleaned_content(pdffile)
        if not raw_text:
            root_logger.error(f"Failed reading document : {pdffile}")
            return {}

        if save_to_local:
            with open(resultfile, "w") as fp:
                fp.write(raw_text)
        
    return raw_text
