"""
Reusable keyword extraction module extracted from test.py
Extracts affected sectors and named companies from document text using LLM.
"""
import os
import re
import json
import logging
from typing import Dict, List
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

load_dotenv()
logger = logging.getLogger(__name__)

MAX_TOKENS_PER_LLM_CALL = 30_000
MODEL_NAME = os.getenv("OPENAI_MODEL", "gpt-4o-mini")


def truncate_for_llm(text: str, max_tokens: int = MAX_TOKENS_PER_LLM_CALL) -> str:
    """Truncate text to fit within token limit."""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n[Text truncated for keyword extraction]"


def extract_keywords_llm(text: str, llm=None) -> Dict[str, List[str]]:
    """
    Extract affected sectors and named companies from document text using LLM.
    
    Args:
        text: Full document text to extract keywords from
        llm: Optional ChatOpenAI instance. If None, creates one.
    
    Returns:
        Dict with 'affected_sectors' and 'named_companies' as lists
    """
    if llm is None:
        llm = ChatOpenAI(model=MODEL_NAME, temperature=0)
    
    prompt = f"""
You are an expert compliance and regulatory analyst.

From the document below, extract:

1. All affected sectors, industries, or types of entities that are regulated, obligated, or in scope.
   Examples: "banks", "virtual asset service providers", "real estate agents", "law firms"

2. Any specific named companies or institutions explicitly mentioned as being affected or in scope.

Return ONLY this exact JSON structure (no markdown, no extra text):

{{
  "affected_sectors": ["banks", "credit unions", "cryptocurrency exchanges"],
  "named_companies": ["Binance", "HSBC", "Revolut"]
}}

Document:
{truncate_for_llm(text)}

JSON only:
"""

    try:
        resp = llm.invoke(prompt)
        content = resp.content.strip()

        # Remove ```json ... ``` blocks if present
        content = re.sub(r"^```json\s*|```$", "", content, flags=re.MULTILINE).strip()

        data = json.loads(content)

        sectors = data.get("affected_sectors", [])
        companies = data.get("named_companies", [])

        # Clean and validate
        sectors = [s.strip() for s in sectors if isinstance(s, str) and s.strip()][:40]
        companies = [c.strip() for c in companies if isinstance(c, str) and c.strip()][:40]

        return {
            "affected_sectors": sectors,
            "named_companies": companies
        }

    except json.JSONDecodeError as e:
        logger.warning(f"JSON decode failed: {e}\nRaw response:\n{content}")
    except Exception as e:
        logger.error(f"Unexpected error in LLM parsing: {e}")

    # Fallback: try to extract any quoted strings
    try:
        fallback_matches = re.findall(r'"([^"]{3,100})"', content)
        fallback = [m.strip() for m in fallback_matches if m.strip()][:40]
        return {
            "affected_sectors": fallback,
            "named_companies": []
        }
    except:
        return {
            "affected_sectors": [],
            "named_companies": []
        }

