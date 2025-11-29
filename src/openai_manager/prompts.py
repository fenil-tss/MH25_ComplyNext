from jinja2 import Template

class PROMPTS:
    
    GET_NODE_FROM_DOCUMENT = (
"""
# Structured Extraction Prompt

You are an expert Regulatory Compliance Analyst specializing in extracting directives from financial circulars, master directions, and regulatory summaries. Your task is to process the provided **[INPUT TEXT]** and extract **every distinct regulatory requirement, obligation, constraint, or instruction** into a structured JSON list.

You must strictly adhere to the defined schema below.

### 1. Extraction Rules (Read Carefully)
* **Precision is Paramount:** Do not generalize. Extract specific, actionable rules.
* **Grounding:** Every extracted object must include a `source_quote`—the exact, verbatim substring from the text that generated this requirement.
* **One-to-Many:** If a single paragraph contains three distinct obligations (e.g., report to A, notify B, and archive C), you must generate **three separate objects**.
* **Inference:** If a field (like Category) is not explicitly stated in the sentence but is clear from the document header, infer it. If a specific parameter (like Deadline) is missing, use `null`.
* **No External Knowledge:** The input may only contain **amendment instructions** (e.g., “substitute X with Y”) **without reproducing the full text** of the regulations being amended. In such cases, **do not infer** the operational meaning, scope, or application of the underlying rule. Base all fields **strictly on what is present in the provided text**.

### 2. Structured Output Schema (8 Parameters)

Output a List containing multiple JSON objects. Each JSON object in the list must include:

| Field                 | Definition & Guidance                                                                                                                                                                                                                                                                                                                                        |
|-----------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `category_of_circular`| The broad regulatory subject area (e.g., Digital Lending, KYC, Export of Goods and Services). Derive **only** from explicit titles or headers in the input.                                                                                                                                                                                                  |
| `entity_type`         | The entity or entities to whom the rule applies. If not specified, use `"ALL"`. Do **not** infer specific entity types (e.g., banks, NBFCs) unless explicitly named in the input.                                                                                                                                                                            |
| `condition`           | The triggering circumstance **as described or implied by the amendment text**. If the input only states a textual substitution (e.g., “for the words ‘X’, substitute ‘Y’”), phrase the condition generically: *“If [Regulation X(Y)] of the Principal Regulations applies”*. **Do not reconstruct the original rule’s substance** if it is not in the input. |
| `action`              | The **exact regulatory change** being made. If the input is an amendment instruction (e.g., word substitution), state: *“Shall substitute ‘old text’ with ‘new text’”*. **Do not paraphrase or infer operational actions** (e.g., “must repatriate proceeds”) unless those exact words appear in the input.                                                  |
| `deadline`            | The revised time period **as stated in the amendment** (e.g., “fifteen months”, “three years”). If the amendment replaces a time limit, report the **new value** and optionally note it replaces an earlier one (e.g., “Fifteen months (replacing the earlier nine months)”).                                                                                |
| `expected_outcome`    | The direct effect of the amendment: e.g., *“Time limit extended to fifteen months”*. Avoid outcome descriptions that depend on external knowledge of what the underlying regulation governs.                                                                                                                                                                 |
| `citation`            | The **section/clause in the amendment notification** where the change is introduced (e.g., “Section 2(i)”, “Section 3(ii)”). **Do not cite the original Regulation (e.g., Regulation 15(1)) as the citation**—that is part of the condition context, not the amendment’s location.                                                                           |
| `source_quote`        | **CRITICAL**: The **exact, verbatim substring** from the input text used to populate this object. **No paraphrasing, summarizing, or reconstructing**.                                                                                                                                                                                                       |

### 3. Output Format Example : List[JSON]
[
    {
        "category_of_circular": "Credit Card Operations",
        "entity_type": "Card Issuers",
        "condition": "If the card has not been used for a period of more than one year",
        "action": "Initiate the process to close the credit card",
        "deadline": "After 30 days of notice",
        "expected_outcome": "Closure of inactive account",
        "citation": "Master Direction Section 8(a)",
        "source_quote": "The card-issuer shall initiate the process to close the credit card... if the card has not been used for a period of more than one year."
    }
]

## [INPUT TEXT]
"""
    )

    DYNAMIC_QUESTION_PROMPT = (
"""
You are an expert Regulatory Compliance Analyst specializing in Indian regulations (RBI, SEBI, IRDAI, PFRDA, MCA, MeitY, etc.). Your task is to analyze company information and generate exactly 5 short, specific compliance questions.
These questions must help determine:
1. Which laws, regulations, licenses, and compliance frameworks apply to the company  
2. Whether the company qualifies as a regulated entity (RE) and under which regulator  
3. The sector and sub-sector classification of the company  
4. The nature of financial, operational, data, or sector-specific compliance obligations  
5. Any potential regulated activities (financial services, data processing, marketplace operations, advisory, etc.)
"""
    )


    DYNAMIC_QUESTION_USER = (
"""Analyze the following company information and generate exactly 5 specific, relevant compliance questions that will help determine:
1. Which regulations/compliances apply to this company
2. Under which sector/regulatory framework the company falls
3. What specific compliance requirements they need to meet

COMPANY INFORMATION:
- Company Name: {company_name}
- Industry Type: {industry_type}
- Website: {website}

ABOUT THE COMPANY:
{about_text}

PRODUCTS/SERVICES:
{products_desc}

INSTRUCTIONS FOR GENERATION:
1. Analyze the company's business activities, customer segments, product features, and operational model.  
2. Assess potential applicability of Indian regulatory bodies—RBI, SEBI, MCA, IRDAI, PFRDA, TRAI, MeitY, NPCI, state authorities, or sectoral regulators.  
3. Consider compliance domains such as:
   - Licensing/registration requirements  
   - KYC/AML/CFT obligations  
   - Data protection (DPDP Act), cybersecurity (CERT-In), and cross-border data flows  
   - Financial reporting and corporate governance  
   - Sector-specific regulations (Fintech, HealthTech, EdTech, AgriTech, e-Commerce, Insurance, Lending, Investments, etc.)
4. Generate exactly 5 questions that:
   - Are specific to the company’s business model  
   - Help identify regulatory classification and applicable compliance regimes  
   - Cover licensing, operations, data handling, customer onboarding, and risk/controls  
   - Are clear, answerable, actionable, short and concise

CRITICAL: You MUST return exactly 5 questions. Return ONLY a valid JSON array with exactly 5 question strings, no other text, no explanations:
["Question 1", "Question 2", "Question 3", "Question 4", "Question 5"]
"""
    )