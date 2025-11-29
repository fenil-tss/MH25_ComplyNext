import streamlit as st
import streamlit_authenticator as stauth
import yaml
from pathlib import Path
import pandas as pd
import sys
from datetime import datetime

# Get the absolute path to ensure it works regardless of working directory
frontend_dir = Path(__file__).resolve().parent
src_dir = frontend_dir.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
if str(frontend_dir) not in sys.path:
    sys.path.insert(0, str(frontend_dir))

# Import local modules (relative to frontend directory)
from components.navbar import load_navbar
from auth import get_authenticator

# Import company scraper (from src directory)
from ingestion.companies.company import scrape_company

# Import OpenAI client directly (avoiding langchain to prevent typing_extensions issues)
import os
import json
from dotenv import load_dotenv
from openai import OpenAI
from config import Config
load_dotenv()

COMPANY_PROFILE_QUESTION_SET = [
    {
        "id": "q1",
        "text": "Q1. What is your primary regulatory registration/license in India?",
        "type": "text_with_examples",
        "examples": [
            "Scheduled Commercial Bank (e.g., SBI, ICICI, HDFC Bank)",
            "Small Finance Bank (SFB)"
        ],
        "placeholder": "Enter your primary license or registration"
    },
    {
        "id": "q2",
        "text": "Q2. If you are an NBFC, what is your RBI sub-category? (Skip if not NBFC)",
        "type": "text_with_examples",
        "examples": [
            "Deposit-taking NBFC (NBFC-D)",
            "Core Investment Company (CIC)"
        ],
        "placeholder": "Enter your NBFC sub-category or type N/A"
    },
    {
        "id": "q3",
        "text": "Q3. Do you hold any of the following operational roles? (Select all that apply)",
        "type": "multi_checkbox",
        "options": [
            "Acquiring bank for merchant payments (e.g., POS, e-commerce)",
            "Card issuer (credit/debit/prepaid)",
            "Sponsor bank for Business Correspondents (BCs)",
            "Agency bank for RBI/government banking",
            "Currency chest operator",
            "Member of Cheque Truncation System (CTS)",
            "Clearing member of CCIL",
            "None of the above"
        ]
    },
    {
        "id": "q4",
        "text": "Q4. Do you or your group engage in any of the following cross-border financial activities? (Select all that apply)",
        "type": "multi_checkbox",
        "options": [
            "Receiving foreign investment (e.g., FDI, FPI, FVCI)",
            "Making overseas investments (e.g., ODI, JV/WOS abroad)",
            "Raising external commercial borrowings (ECB) or issuing masala bonds",
            "Operating a foreign currency (FCY) or NRE/FCNR account in India",
            "Acting as a Foreign Portfolio Investor (FPI) or sub-account",
            "Being a Non-Resident Indian (NRI) / OCI investing in India",
            "Exporting goods/services (and holding EEFC account)",
            "None of the above"
        ]
    },
    {
        "id": "q5",
        "text": "Q5. Which of the following best describes your incorporation/status?",
        "type": "multi_checkbox",
        "options": [
            "Company registered in India (MCA)",
            "Co-operative society (state-registered)",
            "Foreign company / branch office in India",
            "Limited Liability Partnership (LLP)",
            "Individual / Proprietorship / Partnership firm",
            "Trust / Society / Section 8 Company",
            "Others"
        ]
    },
    {
        "id": "q6",
        "text": "Q6. Is your company operating in India?",
        "type": "binary",
        "options": ["Yes", "No"]
    },
    {
        "id": "q7",
        "text": "Q7. Do you engage in any of the following activities? (Select all that apply)",
        "type": "multi_checkbox",
        "options": [
            "Accepting public deposits",
            "Lending (retail, SME, corporate, microfinance)",
            "Investing in securities (bonds, equities, G-Secs)",
            "Operating ATMs (not owned by a bank)",
            "Providing payment services (e.g., wallets, UPI apps, payment gateways)",
            "Acting as a market-maker in G-Secs / forex",
            "Holding a Gilt / SGL account with RBI",
            "None of the above"
        ]
    },
    {
        "id": "q8",
        "text": "Q8. If your business is involved in payments, which category best describes your role?",
        "type": "text_with_examples",
        "examples": [
            "Third-Party App Provider (TPAP)",
            "Payment Instrument Issuer (e.g., PPI wallets, prepaid cards)"
        ],
        "placeholder": "Describe your payments role or type N/A"
    },
    {
        "id": "q9",
        "text": "Q9. How many employees does your organization currently have?",
        "type": "input",
        "placeholder": "Enter the current employee count"
    },
    {
        "id": "q10",
        "text": "Q10. What are the top compliance challenges or pain points you want to address?",
        "type": "text_area",
        "placeholder": "Describe your top compliance challenges"
    }
]


def render_company_profile_questionnaire(prefix: str, stored_responses: dict | None = None) -> dict:
    """Render the standardized company profile questionnaire and return responses."""
    stored_responses = stored_responses or {}
    responses = {}

    for idx, question in enumerate(COMPANY_PROFILE_QUESTION_SET):
        st.markdown(f"**{question['text']}**")
        question_type = question["type"]
        placeholder = question.get("placeholder", "")
        widget_base = f"{prefix}_{question['id']}"
        stored_value = stored_responses.get(question["id"])

        if question_type == "text_with_examples":
            st.caption("Examples:")
            for example in question.get("examples", []):
                st.markdown(f"* {example}")
            responses[question["id"]] = st.text_input(
                label=f"{question['text']} ({question['id']})",
                value=stored_value or "",
                placeholder=placeholder,
                key=f"{widget_base}_text",
                label_visibility="collapsed"
            )
        elif question_type == "multi_checkbox":
            st.caption("Select all that apply.")
            selected_options = stored_value if isinstance(stored_value, list) else []
            selections = []
            for option_idx, option in enumerate(question.get("options", [])):
                checked = st.checkbox(
                    option,
                    value=option in selected_options,
                    key=f"{widget_base}_option_{option_idx}"
                )
                if checked:
                    selections.append(option)
            responses[question["id"]] = selections
        elif question_type == "binary":
            options = question.get("options", [])
            default_index = options.index(stored_value) if stored_value in options else 0
            responses[question["id"]] = st.radio(
                label=f"{question['text']} ({question['id']})",
                options=options,
                index=default_index if options else 0,
                key=f"{widget_base}_radio",
                horizontal=True,
                label_visibility="collapsed"
            )
        elif question_type == "input":
            responses[question["id"]] = st.text_input(
                label=f"{question['text']} ({question['id']})",
                value=stored_value or "",
                placeholder=placeholder,
                key=f"{widget_base}_input",
                label_visibility="collapsed"
            )
        elif question_type == "text_area":
            responses[question["id"]] = st.text_area(
                label=f"{question['text']} ({question['id']})",
                value=stored_value or "",
                placeholder=placeholder,
                key=f"{widget_base}_textarea",
                height=140,
                label_visibility="collapsed"
            )
        else:
            responses[question["id"]] = stored_value or ""

        if idx < len(COMPANY_PROFILE_QUESTION_SET) - 1:
            st.markdown("---")

    return responses

# ===================== LLM QUESTION GENERATION =====================
def generate_compliance_questions(scraped_data: dict, company_name: str, industry_type: str) -> list:

    # Prepare context from scraped data
    about_text = scraped_data.get("about", {}).get("text", "")
    products_services = scraped_data.get("products_services", [])
    website = scraped_data.get("website", "")
    
    # Build products/services description
    products_desc = ""
    if products_services:
        products_desc = "\n".join([
            f"- {p.get('title', 'N/A')}: {p.get('description', 'N/A')[:200]}"
            for p in products_services[:5]  # Limit to first 5
        ])
    
    # Create comprehensive prompt for LLM
    system_prompt = """You are an expert Regulatory Compliance Analyst specializing in Indian regulations (RBI, SEBI, IRDAI, PFRDA, MCA, MeitY, etc.). Your task is to analyze company information and generate exactly 5 short, specific compliance questions.
    These questions must help determine:
1. Which laws, regulations, licenses, and compliance frameworks apply to the company  
2. Whether the company qualifies as a regulated entity (RE) and under which regulator  
3. The sector and sub-sector classification of the company  
4. The nature of financial, operational, data, or sector-specific compliance obligations  
5. Any potential regulated activities (financial services, data processing, marketplace operations, advisory, etc.)"""
    
    user_prompt = f"""Analyze the following company information and generate exactly 5 specific, relevant compliance questions that will help determine:
1. Which regulations/compliances apply to this company
2. Under which sector/regulatory framework the company falls
3. What specific compliance requirements they need to meet

COMPANY INFORMATION:
- Company Name: {company_name}
- Industry Type: {industry_type}
- Website: {website}

ABOUT THE COMPANY:
{about_text[:1000] if about_text else "No about information available"}

PRODUCTS/SERVICES:
{products_desc if products_desc else "No products/services information available"}

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
    
    # Initialize OpenAI client directly (no langchain dependency)
    openai_client = OpenAI(
        api_key=Config.OPENAI_API_KEY or os.getenv("OPENAI_API_KEY"),
        timeout=60,
        max_retries=3
    )
    
    # Retry logic: Try up to 3 times to get valid questions from GPT
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            # Call OpenAI API directly
            response = openai_client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3
            )
            
            content = response.choices[0].message.content.strip()
            
            # Try to extract JSON from response
            # Remove markdown code blocks if present
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            # Try to parse as JSON array directly
            try:
                questions = json.loads(content)
            except json.JSONDecodeError:
                # If direct parse fails, try to extract array from JSON object
                if content.startswith("{") and "questions" in content.lower():
                    parsed = json.loads(content)
                    # Look for questions in various possible keys
                    for key in ["questions", "question_list", "items", "data"]:
                        if key in parsed and isinstance(parsed[key], list):
                            questions = parsed[key]
                            break
                    else:
                        raise ValueError("Could not find questions array in JSON response")
                else:
                    raise
            
            # Validate we got a list
            if not isinstance(questions, list):
                raise ValueError(f"Expected a list, got {type(questions)}")
            
            # Validate we have exactly 5 questions
            if len(questions) == 5:
                # Validate all are strings
                if all(isinstance(q, str) and q.strip() for q in questions):
                    return questions
                else:
                    raise ValueError("Not all questions are valid strings")
            elif len(questions) > 5:
                # If GPT gave more than 5, take first 5
                return [str(q).strip() for q in questions[:5] if str(q).strip()]
            else:
                # If GPT gave fewer than 5, ask it to generate more
                if attempt < max_retries - 1:
                    user_prompt = f"""You previously generated {len(questions)} questions, but I need exactly 5. 

Previous questions: {json.dumps(questions)}

Please generate exactly 5 questions total. Return ONLY a valid JSON array with exactly 5 question strings:
["Question 1", "Question 2", "Question 3", "Question 4", "Question 5"]"""
                    continue
                else:
                    raise ValueError(f"GPT generated only {len(questions)} questions, need exactly 5")
                    
        except json.JSONDecodeError as e:
            last_error = f"JSON parsing error: {str(e)}"
            if attempt < max_retries - 1:
                user_prompt = f"""Your previous response was not valid JSON. Please return ONLY a valid JSON array with exactly 5 question strings, no other text:
["Question 1", "Question 2", "Question 3", "Question 4", "Question 5"]"""
                continue
        except Exception as e:
            last_error = str(e)
            if attempt < max_retries - 1:
                continue
    
    # If we get here, all retries failed
    raise Exception(
        f"Failed to generate compliance questions after {max_retries} attempts. "
        f"Last error: {last_error}. "
        f"Please ensure your OpenAI API key is valid and the model is accessible."
    )

# ===================== CONFIGURATION =====================
# Get absolute paths for config and CSS files (relative to frontend directory)
CONFIG_FILE = frontend_dir / "config.yaml"
CSS_FILE = frontend_dir / "style.css"

# Load custom CSS (if exists)
if CSS_FILE.exists():
    with open(CSS_FILE, 'r', encoding='utf-8') as f:
        st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# Load config
if not CONFIG_FILE.exists():
    st.error("config.yaml not found! Please create it.")
    st.stop()

with open(CONFIG_FILE, 'r', encoding='utf-8') as file:
    config = yaml.safe_load(file)

# ===================== INITIALIZE SESSION STATE =====================
if "authentication_status" not in st.session_state:
    st.session_state.authentication_status = None
if "company_details" not in st.session_state:
    st.session_state.company_details = {
        "company_name": "", "company_email": "", "company_phone": "",
        "industry_type": "", "address": "", "website": ""
    }
if "scraped_data" not in st.session_state:
    st.session_state.scraped_data = None
if "show_scraped_form" not in st.session_state:
    st.session_state.show_scraped_form = False
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []
if "compliance_questions" not in st.session_state:
    st.session_state.compliance_questions = None
if "show_questions_form" not in st.session_state:
    st.session_state.show_questions_form = False
if "question_answers" not in st.session_state:
    st.session_state.question_answers = {}
if "company_profile_responses" not in st.session_state:
    st.session_state.company_profile_responses = {}

st.set_page_config(page_icon="assets/logo.png")

# ===================== LOGIN PAGE =====================
if not st.session_state.get("authentication_status"):
    st.set_page_config(page_title="ComplyNext - Login", page_icon="Scale", layout="centered")

    st.markdown("""
    <div class="header" style="text-align: center; padding: 2rem;">
        <h1>Welcome to ComplyNext</h1>
        <h3>AI-Powered Regulatory Compliance Platform</h3>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        authenticator = get_authenticator()
        authenticator.login(location='main')

        st.markdown("""
            <div style="text-align: center; margin: 25px 0; color: #666; position: relative;">
                <span style="background: white; padding: 0 15px; z-index: 1; position: relative;">OR</span>
                <hr style="position: absolute; top: 50%; left: 0; right: 0; border: 1px solid #ddd; margin: 0;" />
            </div>
        """, unsafe_allow_html=True)

        if config.get('oauth2', {}).get('google', {}).get('client_id'):
            authenticator.experimental_guest_login(
                button_name='Continue with Google',
                provider='google',
                oauth2=config['oauth2'],
                use_container_width=True
            )
        else:
            st.button("Continue as Guest (Demo Mode)", 
                     on_click=lambda: st.session_state.update(authentication_status=None, name="Guest User", username="guest"))

    if st.session_state["authentication_status"]:
        st.success(f"Welcome {st.session_state['name']}! Redirecting...")
        st.rerun()
    elif st.session_state["authentication_status"] is False:
        st.error("Username or password is incorrect")
    elif st.session_state["authentication_status"] is None and st.session_state.get("name") == "Guest User":
        st.session_state.authentication_status = True
        st.session_state.name = "Guest User"
        st.session_state.username = "guest"
        st.rerun()

    st.stop()

# ===================== USER IS LOGGED IN =====================
else:
    st.set_page_config(
        page_title="ComplyNext - Compliance Management",
        page_icon="Scale",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # ===================== COMPLIANCE QUESTIONS FORM (Check FIRST before onboarding) =====================
    # Show questions form if questions are generated (even if company_name exists)
    if (st.session_state.show_questions_form and 
        st.session_state.compliance_questions and 
        not st.session_state.show_scraped_form):
        
        # Hide sidebar during questions
        st.markdown("""
        <style>
            section[data-testid="stSidebar"] {display: none !important;}
            .main > div {padding-top: 3rem; max-width: 900px; margin: 0 auto;}
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown("# 📝 Compliance Assessment")
        st.markdown("### Please answer the following questions")
        st.info("These questions are generated based on your company's profile and industry to help us understand your compliance requirements better.")
        st.markdown("---")
        
        questions = st.session_state.compliance_questions
        
        with st.form(key="compliance_questions_form"):
            answers = {}
            for idx, question in enumerate(questions):
                st.markdown(f"#### Question {idx + 1} of {len(questions)}")
                st.markdown(f"**{question}**")
                answer = st.text_area(
                    f"Your Answer",
                    key=f"answer_{idx}",
                    height=120,
                    placeholder="Please provide a detailed answer...",
                    label_visibility="collapsed"
                )
                answers[idx] = {
                    "question": question,
                    "answer": answer
                }
                if idx < len(questions) - 1:  # Don't add divider after last question
                    st.markdown("---")
            
            col1, col2, col3 = st.columns([1, 1, 4])
            with col1:
                submit_answers = st.form_submit_button("✅ Submit Answers", use_container_width=True, type="primary")
            with col2:
                skip_questions = st.form_submit_button("Skip for Now", use_container_width=True)
            
            if submit_answers:
                # Check if all questions are answered
                all_answered = all(answers[i]["answer"].strip() for i in range(len(questions)))
                
                if all_answered:
                    st.session_state.question_answers = answers
                    st.session_state.show_questions_form = False
                    # Mark onboarding as complete
                    st.session_state.company_details["questionnaire_completed"] = True
                    st.success("✅ Thank you! Your answers have been saved. We'll use this information to provide personalized compliance recommendations.")
                    st.balloons()
                    st.rerun()
                else:
                    st.warning("⚠️ Please answer all questions before submitting.")
            
            if skip_questions:
                st.session_state.show_questions_form = False
                st.info("You can answer these questions later from your Company Profile page.")
                st.rerun()
        
        st.stop()  # Stop here to prevent showing onboarding or dashboard
    
    # ===================== ONBOARDING: FORCE COMPANY PROFILE IF NOT FILLED =====================
    if not st.session_state.company_details.get("company_name"):
        st.markdown("""
        <style>
            section[data-testid="stSidebar"] {display: none !important;}
            .main > div {padding-top: 3rem; max-width: 800px; margin: 0 auto;}
        </style>
        """, unsafe_allow_html=True)

        st.markdown("# Welcome to ComplyNext!")
        st.markdown("### Let's set up your company profile to personalize your compliance experience")

        temp_form_data = st.session_state.get("temp_form_data", {})
        industry_options = [
            "", "Information Technology", "Finance", "E-Commerce", "Manufacturing",
            "Education", "Construction", "Retail", "Small Corporative Bank",
            "Small Finance Bank", "Other"
        ]
        stored_questionnaire_prefill = temp_form_data.get("company_profile_responses", st.session_state.company_profile_responses)
        auto_fetch_clicked = False
        onboarding_question_answers = stored_questionnaire_prefill or {}

        with st.form(key="onboarding_form"):
            st.subheader("Company Information")

            c1, c2 = st.columns(2)
            with c1:
                company_name = st.text_input(
                    "Company Name *",
                    value=temp_form_data.get("company_name", ""),
                    placeholder="Acme Fintech Pvt Ltd"
                )
                company_email = st.text_input(
                    "Company Email *",
                    value=temp_form_data.get("company_email", ""),
                    placeholder="compliance@acme.com"
                )
                company_phone = st.text_input(
                    "Phone Number",
                    value=temp_form_data.get("company_phone", ""),
                    placeholder="+91 98765 43210"
                )
            with c2:
                industry_prefill = temp_form_data.get("industry_type", "")
                industry_index = industry_options.index(industry_prefill) if industry_prefill in industry_options else 0
                industry_type = st.selectbox(
                    "Industry Type *",
                    industry_options,
                    index=industry_index
                )
                website = st.text_input(
                    "Website",
                    value=temp_form_data.get("website", ""),
                    placeholder="https://acme.com"
                )

            address = st.text_area(
                "Registered Address *",
                value=temp_form_data.get("address", ""),
                placeholder="123 Business Street, Mumbai, India"
            )
            # gst_number = st.text_input("GST Number (Optional)")
            # cin_number = st.text_input("CIN Number (Optional)")

            st.markdown("---")
            st.subheader("Regulatory Profile Questionnaire")
            st.caption("Answer these questions to help us classify your regulatory profile.")
            onboarding_question_answers = render_company_profile_questionnaire(
                prefix="onboarding_cp",
                stored_responses=stored_questionnaire_prefill
            )

            st.markdown("---")
            # Auto-fetch button (inside form, before main submit button)
            if website:
                auto_fetch_clicked = st.form_submit_button("🔍 Auto Fetch Company Details", use_container_width=False)
            
            col1, col2 = st.columns([1, 5])
            with col1:
                submitted = st.form_submit_button("Complete Setup →", use_container_width=True, type="primary")

        # Handle auto-fetch button click (must be checked first)
        if auto_fetch_clicked and website:
            # Store current form values before scraping
            st.session_state.temp_form_data = {
                "company_name": company_name if 'company_name' in locals() else "",
                "company_email": company_email if 'company_email' in locals() else "",
                "company_phone": company_phone if 'company_phone' in locals() else "",
                "industry_type": industry_type if 'industry_type' in locals() else "",
                "address": address if 'address' in locals() else "",
                "website": website if 'website' in locals() else "",
                "company_profile_responses": onboarding_question_answers
            }
            with st.spinner("Fetching company details from website..."):
                try:
                    scraped_data = scrape_company(website)
                    
                    if scraped_data and scraped_data.get("website"):
                        st.session_state.scraped_data = scraped_data
                        st.session_state.show_scraped_form = True
                        st.success("Details fetched successfully ✅")
                        st.rerun()
                    else:
                        st.error("Failed to fetch data from website. Please check the URL.")
                except Exception as e:
                    st.error(f"Error scraping website: {str(e)}")
        
        # If form is submitted with a website URL, automatically scrape
        elif submitted:
            try:
                # Get form values - they should be available after form submission
                form_website = website if 'website' in locals() else ""
                form_company_name = company_name if 'company_name' in locals() else ""
                form_company_email = company_email if 'company_email' in locals() else ""
                form_company_phone = company_phone if 'company_phone' in locals() else ""
                form_industry_type = industry_type if 'industry_type' in locals() else ""
                form_address = address if 'address' in locals() else ""
                
                # Store form values in session state
                st.session_state.temp_form_data = {
                    "company_name": form_company_name,
                    "company_email": form_company_email,
                    "company_phone": form_company_phone,
                    "industry_type": form_industry_type,
                    "address": form_address,
                    "website": form_website,
                    "company_profile_responses": onboarding_question_answers
                }
                
                # If website is provided and we haven't shown scraped form yet, scrape
                if form_website and not st.session_state.show_scraped_form:
                    with st.spinner("Scraping website details..."):
                        try:
                            scraped_data = scrape_company(form_website)
                            if scraped_data and scraped_data.get("website"):
                                st.session_state.scraped_data = scraped_data
                                st.session_state.show_scraped_form = True
                                st.rerun()
                        except Exception as e:
                            st.error(f"Error scraping website: {str(e)}")
                
                # If no website or after scraping, save the details
                elif not form_website or st.session_state.show_scraped_form:
                    if form_company_name and form_company_email and form_industry_type and form_address:
                        # Merge scraped data if available
                        scraped = st.session_state.scraped_data or {}
                        
                        st.session_state.company_details = {
                            "company_name": form_company_name,
                            "company_email": form_company_email or (scraped.get("emails", [""])[0] if scraped.get("emails") else ""),
                            "company_phone": form_company_phone or (scraped.get("phones", [""])[0] if scraped.get("phones") else "") or "—",
                            "industry_type": form_industry_type,
                            "address": form_address,
                            "website": form_website or scraped.get("website", "—"),
                            "scraped_data": scraped,  # Store full scraped data
                            # "gst_number": gst_number or "—",
                            # "cin_number": cin_number or "—"
                        }
                        st.session_state.company_profile_responses = onboarding_question_answers
                        st.session_state.show_scraped_form = False
                        
                        # Generate compliance questions if we have scraped data
                        if scraped and scraped.get("website"):
                            with st.spinner("🤖 Analyzing company details and generating compliance questions..."):
                                questions = generate_compliance_questions(
                                    scraped_data=scraped,
                                    company_name=form_company_name,
                                    industry_type=form_industry_type
                                )
                                st.session_state.compliance_questions = questions
                                st.session_state.show_questions_form = True
                        
                        st.success(f"Welcome aboard, {form_company_name}!")
                        st.balloons()
                        st.rerun()
                    else:
                        st.error("Please fill all required fields marked with *")
            except NameError as e:
                st.error(f"Form submission error: {str(e)}. Please try again.")

        # ===================== SCRAPED DATA REVIEW FORM =====================
        if st.session_state.show_scraped_form and st.session_state.scraped_data:
            st.markdown("---")
            st.markdown("### 📋 Scraped Company Details")
            st.info("Review and confirm the details scraped from the website. You can edit any field before saving.")
            
            scraped = st.session_state.scraped_data
            
            with st.form(key="scraped_details_form"):
                st.subheader("Contact Information")
                
                col1, col2 = st.columns(2)
                with col1:
                    # Display emails
                    emails_list = scraped.get("emails", [])
                    if emails_list:
                        selected_email = st.selectbox(
                            "Company Email *",
                            options=[""] + emails_list,
                            index=1 if emails_list else 0,
                            help="Select from scraped emails or enter manually"
                        )
                        if selected_email:
                            company_email = selected_email
                        else:
                            company_email = st.text_input("Or enter email manually", key="manual_email")
                    else:
                        company_email = st.text_input("Company Email *", placeholder="No email found, please enter")
                    
                    # Display phones
                    phones_list = scraped.get("phones", [])
                    if phones_list:
                        selected_phone = st.selectbox(
                            "Phone Number",
                            options=[""] + phones_list,
                            index=1 if phones_list else 0,
                            help="Select from scraped phone numbers"
                        )
                        company_phone = selected_phone if selected_phone else ""
                    else:
                        company_phone = st.text_input("Phone Number", placeholder="No phone found", key="manual_phone")
                
                with col2:
                    website_display = st.text_input("Website", value=scraped.get("website", ""), disabled=True)
                    scraped_at = scraped.get("scraped_at", "")
                    if scraped_at:
                        st.caption(f"Scraped on: {scraped_at}")
                
                st.markdown("---")
                st.subheader("About Company")
                
                about_text = scraped.get("about", {}).get("text", "")
                about_url = scraped.get("about", {}).get("source_url", "")
                
                if about_text:
                    about_display = st.text_area(
                        "About Company",
                        value=about_text,
                        height=200,
                        help=f"Source: {about_url}"
                    )
                else:
                    about_display = st.text_area("About Company", placeholder="No about information found", height=200)
                
                st.markdown("---")
                st.subheader("Products & Services")
                
                products_services = scraped.get("products_services", [])
                if products_services:
                    for idx, product in enumerate(products_services):
                        with st.expander(f"📦 {product.get('title', 'Product/Service')}"):
                            st.write(f"**Description:** {product.get('description', 'N/A')}")
                            st.caption(f"Source: {product.get('url', 'N/A')}")
                else:
                    st.info("No products/services information found")
                
                st.markdown("---")
                
                # Additional required fields
                st.subheader("Additional Information")
                col1, col2 = st.columns(2)
                with col1:
                    # Get values from session state if available, otherwise use empty
                    temp_data = st.session_state.get("temp_form_data", {})
                    company_name = st.text_input("Company Name *", value=temp_data.get("company_name", ""))
                    industry_type = st.selectbox("Industry Type *", [
                        "", "Information Technology", "Finance", "E-Commerce", "Manufacturing",
                        "Education", "Construction", "Retail", "Small Corporative Bank",
                        "Small Finance Bank", "Other"
                    ], index=0 if not temp_data.get("industry_type") else [
                        "", "Information Technology", "Finance", "E-Commerce", "Manufacturing",
                        "Education", "Construction", "Retail", "Small Corporative Bank",
                        "Small Finance Bank", "Other"
                    ].index(temp_data.get("industry_type", "")) if temp_data.get("industry_type") in [
                        "", "Information Technology", "Finance", "E-Commerce", "Manufacturing",
                        "Education", "Construction", "Retail", "Small Corporative Bank",
                        "Small Finance Bank", "Other"
                    ] else 0)
                with col2:
                    address = st.text_area("Registered Address *", value=temp_data.get("address", ""), placeholder="123 Business Street, Mumbai, India", height=100)
                
                col1, col2, col3 = st.columns([1, 1, 4])
                with col1:
                    save_scraped = st.form_submit_button("💾 Save Details", use_container_width=True, type="primary")
                with col2:
                    cancel_scraped = st.form_submit_button("Cancel", use_container_width=True)
                
                if save_scraped:
                    if company_name and company_email and industry_type and address:
                        st.session_state.company_details = {
                            "company_name": company_name,
                            "company_email": company_email,
                            "company_phone": company_phone or "—",
                            "industry_type": industry_type,
                            "address": address,
                            "website": scraped.get("website", website or "—"),
                            "scraped_data": scraped,
                            "about_text": about_display if about_text else ""
                        }
                        st.session_state.show_scraped_form = False
                        st.session_state.temp_form_data = {}
                        
                        # Generate compliance questions using LLM (NO hardcoded fallbacks)
                        with st.spinner("🤖 Analyzing company details and generating compliance questions..."):
                            try:
                                questions = generate_compliance_questions(
                                    scraped_data=scraped,
                                    company_name=company_name,
                                    industry_type=industry_type
                                )
                                st.session_state.compliance_questions = questions
                                st.session_state.show_questions_form = True
                                # Don't show success message here - it will show after questions are answered
                            except Exception as e:
                                st.error(f"❌ Failed to generate questions: {str(e)}")
                                st.info("Please try again or contact support if the issue persists.")
                                # Don't proceed to questions form if generation failed
                                st.session_state.show_questions_form = False
                                st.session_state.compliance_questions = None
                                st.success(f"Company details saved successfully! Welcome aboard, {company_name}!")
                        
                        st.rerun()
                    else:
                        st.error("Please fill all required fields marked with *")
                
                if cancel_scraped:
                    st.session_state.show_scraped_form = False
                    st.session_state.scraped_data = None
                    st.session_state.temp_form_data = {}
                    st.rerun()
        
        # Questions form is now handled at the top (before onboarding check) - see line 287
        st.stop()

    # ===================== MAIN APP (After Onboarding) =====================
    st.markdown("""
        <style>
        .main {padding-top: 2rem;}
        .stTabs [data-baseweb="tab-list"] button {font-size: 16px; font-weight: 600;}
        .alert-high {border-left: 5px solid #ef4444; background:#fee2e2; padding:15px; border-radius:8px; margin:10px 0;}
        .alert-medium {border-left: 5px solid #f97316; background:#ffedd5; padding:15px; border-radius:8px; margin:10px 0;}
        .alert-low {border-left: 5px solid #22c55e; background:#dcfce7; padding:15px; border-radius:8px; margin:10px 0;}
        </style>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.title(f"Hello {st.session_state['name']}!")
        st.caption("ComplyNext - AI-Powered Compliance")
        st.divider()
        # st.write(f"**{st.session_state.company_details['company_name']}**")
        # st.caption(f"{st.session_state.company_details['company_email']}")
        # st.caption(f"Industry: {st.session_state.company_details['industry_type']}")
        st.sidebar.caption(f"Logged in as: {st.session_state['username']}")

    # Navigation
    page = st.sidebar.radio(
        "Navigation",
        ["Dashboard", "Regulatory Alerts", "Document Analysis", "Impact Assessment",
         "Action Items", "Compliance Reports", "AI Assistant", "Company Profile", "Settings"],
        label_visibility="collapsed"
    )

    # Load navbar (assuming you have this component)
    load_navbar(page)
# ============================================================================
# DASHBOARD PAGE
# ============================================================================
if page == "Dashboard":
    st.markdown("Your regulatory compliance at a glance")
    
    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Compliance Score",
            value="92%",
            delta="+5%",
            delta_color="normal"
        )
    
    with col2:
        st.metric(
            label="Audit Risk Reduction",
            value="40%",
            delta="+8%",
            delta_color="normal"
        )
    
    with col3:
        st.metric(
            label="Active Regulations",
            value="24",
            delta="+3",
            delta_color="off"
        )
    
    with col4:
        st.metric(
            label="Pending Actions",
            value="3",
            delta="-2",
            delta_color="inverse"
        )
    
    st.markdown("---")
    
    # Recent Alerts and Timeline
    col_alerts, col_timeline = st.columns([2, 1])
    
    with col_alerts:
        st.subheader("🔔 Recent Regulatory Updates")
        
        alerts_data = [
            {"date": "Nov 24, 2025", "title": "RBI KYC Guidelines Update", "severity": "HIGH"},
            {"date": "Nov 22, 2025", "title": "SEBI Data Protection Circular", "severity": "MEDIUM"},
            {"date": "Nov 20, 2025", "title": "MCA Compliance Extension", "severity": "LOW"},
        ]
        
        for alert in alerts_data:
            severity_color = "red" if alert["severity"] == "HIGH" else "orange" if alert["severity"] == "MEDIUM" else "green"
            st.markdown(f"""
            <div class="alert-{alert['severity'].lower()}">
                <b>{alert['title']}</b><br>
                <small>{alert['date']} | <span style="background-color: {severity_color}; color: white; padding: 2px 8px; border-radius: 3px; font-size: 12px;">{alert['severity']}</span></small>
            </div>
            """, unsafe_allow_html=True)
    
    with col_timeline:
        st.subheader("📅 Compliance Timeline")
        
        timeline_data = {
            "✅ Complete": "18 regulations",
            "⏳ In Progress": "3 regulations",
            "❌ Not Started": "3 regulations"
        }
        
        for status, count in timeline_data.items():
            st.write(f"{status}: **{count}**")

# ============================================================================
# REGULATORY ALERTS PAGE
# ============================================================================
elif page == "Regulatory Alerts":
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        regulator = st.selectbox("Filter by Regulator", ["All Regulators", "RBI", "SEBI", "MCA"])
    
    with col2:
        severity = st.selectbox("Filter by Severity", ["All Severity", "High", "Medium", "Low"])
    
    with col3:
        search = st.text_input("Search alerts...")
    
    st.markdown("---")
    
    # Display alerts
    alerts = [
        {"id": 1, "title": "RBI Circular - KYC Amendment #1", "desc": "Update to Know Your Customer guidelines affecting onboarding process", "date": "Nov 24, 2025", "severity": "HIGH"},
        {"id": 2, "title": "RBI Circular - KYC Amendment #2", "desc": "Additional verification requirements for high-risk customers", "date": "Nov 23, 2025", "severity": "HIGH"},
        {"id": 3, "title": "SEBI Data Protection Circular #3", "desc": "New data encryption standards for customer information", "date": "Nov 22, 2025", "severity": "MEDIUM"},
        {"id": 4, "title": "MCA Compliance Extension #4", "desc": "Extended timeline for annual compliance filings", "date": "Nov 20, 2025", "severity": "LOW"},
        {"id": 5, "title": "RBI Circular - AML Guidelines #5", "desc": "Enhanced anti-money laundering procedures", "date": "Nov 19, 2025", "severity": "HIGH"},
    ]
    
    for alert in alerts:
        severity_class = alert["severity"].lower()
        col1, col2 = st.columns([4, 1])
        
        with col1:
            st.markdown(f"""
            <div class="alert-{severity_class}"> us
                <b>{alert['title']}</b><br>f
                <small>{alert['desc']}</small><br>
                <small>Released: {alert['date']}</small>
            </div>
            """, unsafe_allow_html=True)
        
        with col2:
            if st.button("View Details", key=f"alert_{alert['id']}"):
                st.session_state.selected_alert = alert['id']
                st.info(f"Details for {alert['title']}")


# ============================================================================
# COMPANY PROFILE PAGE (NEW)
# ============================================================================
# ============================================================================
    # COMPANY PROFILE (Editable after onboarding)
    # ============================================================================
elif page == "Company Profile":
    st.markdown("## Company Profile")
    st.success("Onboarding complete! You can update your details anytime.")
    with st.form("update_company_form"):
        details = st.session_state.company_details
        c1, c2 = st.columns(2)
        with c1:
            company_name = st.text_input("Company Name *", value=details["company_name"])
            company_email = st.text_input("Company Email *", value=details["company_email"])
            company_phone = st.text_input("Phone", value=details["company_phone"])
        with c2:
            industry_type = st.selectbox("Industry Type *", [
                "Information Technology", "Finance", "E-Commerce", "Manufacturing",
                "Education", "Construction", "Retail", "Small Corporative Bank",
                "Small Finance Bank", "Other"
            ], index=["Information Technology", "Finance", "E-Commerce", "Manufacturing",
                      "Education", "Construction", "Retail", "Small Corporative Bank",
                      "Small Finance Bank", "Other"].index(details["industry_type"]))
            website = st.text_input("Website", value=details["website"])
        address = st.text_area("Address *", value=details["address"])
        # gst_number = st.text_input("GST Number", value=details["gst_number"] if details["gst_number"] != "—" else "")
        # cin_number = st.text_input("CIN Number", value=details["cin_number"] if details["cin_number"] != "—" else "")
        submitted = st.form_submit_button("Update Details")
        if submitted:
            if company_name and company_email and industry_type and address:
                st.session_state.company_details.update({
                    "company_name": company_name, "company_email": company_email,
                    "company_phone": company_phone or "—", "industry_type": industry_type,
                    "address": address, "website": website or "—",
                    # "gst_number": gst_number or "—", "cin_number": cin_number or "—"
                })
                st.success("Company profile updated!")
                st.rerun()
            else:
                st.error("Required fields missing")

    st.markdown("---")
    st.markdown("## Company Regulatory Profile Questionnaire")
    st.caption("Answer these 10 questions to complete the Company Profile section. Follow the guidance in brackets—examples, multiple checkboxes, binary choices, or manual inputs.")

    with st.form("company_profile_questionnaire_form"):
        latest_responses = render_company_profile_questionnaire(
            prefix="profile_cp",
            stored_responses=st.session_state.company_profile_responses
        )
        save_company_profile_questions = st.form_submit_button("Save Questionnaire Responses", use_container_width=True, type="primary")

    if save_company_profile_questions:
        st.session_state.company_profile_responses = latest_responses
        st.success("Company profile questionnaire updated!")
        st.rerun()

    # ===================== COMPLIANCE QUESTIONNAIRE RESPONSES (Editable) =====================
    st.markdown("---")
    st.markdown("## Compliance Questionnaire Responses")
    
    # Check if questions and answers exist
    question_answers = st.session_state.get("question_answers", {})
    compliance_questions = st.session_state.get("compliance_questions", [])
    
    if question_answers and len(question_answers) > 0:
        # Use questions from answers if available, otherwise use compliance_questions
        questions_list = compliance_questions if compliance_questions else [question_answers[i].get("question", f"Question {i+1}") for i in sorted(question_answers.keys())]
        
        with st.form("update_questionnaire_form"):
            st.info("You can update your compliance questionnaire responses below. All fields are editable.")
            
            updated_answers = {}
            sorted_indices = sorted(question_answers.keys())
            for idx in sorted_indices:
                qa_data = question_answers[idx]
                # Get question from answer data first, fallback to questions_list, then default
                question = qa_data.get("question", "")
                if not question and questions_list:
                    # Convert idx to list position (assuming 0-based indexing)
                    list_idx = sorted_indices.index(idx)
                    if list_idx < len(questions_list):
                        question = questions_list[list_idx]
                    else:
                        question = f"Question {idx + 1}"
                elif not question:
                    question = f"Question {idx + 1}"
                
                current_answer = qa_data.get("answer", "")
                
                st.markdown(f"#### Question {idx + 1}")
                st.markdown(f"**{question}**")
                
                updated_answer = st.text_area(
                    f"Your Answer",
                    value=current_answer,
                    key=f"questionnaire_answer_{idx}",
                    height=120,
                    placeholder="Enter your answer here...",
                    label_visibility="collapsed"
                )
                
                updated_answers[idx] = {
                    "question": question,
                    "answer": updated_answer
                }
                
                if idx < len(question_answers) - 1:
                    st.markdown("---")
            
            col1, col2 = st.columns([1, 5])
            with col1:
                update_questionnaire = st.form_submit_button("Update Responses", use_container_width=True, type="primary")
            
            if update_questionnaire:
                # Validate all answers are filled
                all_answered = all(updated_answers[i]["answer"].strip() for i in updated_answers.keys())
                
                if all_answered:
                    st.session_state.question_answers = updated_answers
                    st.success("✅ Questionnaire responses updated successfully!")
                    st.rerun()
                else:
                    st.warning("⚠️ Please provide answers for all questions before updating.")
    elif compliance_questions and len(compliance_questions) > 0:
        # Questions exist but no answers yet - show message
        st.info("📝 You haven't answered the compliance questionnaire yet. Please complete it from the onboarding flow.")
        with st.expander("View Questions"):
            for idx, question in enumerate(compliance_questions):
                st.markdown(f"**Question {idx + 1}:** {question}")
                if idx < len(compliance_questions) - 1:
                    st.markdown("---")
    else:
        # No questions or answers
        st.info("📝 No compliance questionnaire has been generated yet. Questions will appear here after you complete the onboarding process.")

# ============================================================================
# DOCUMENT ANALYSIS PAGE
# ============================================================================
elif page == "Document Analysis":
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Compare Regulations")
        
        prev_version = st.selectbox("Previous Version", ["RBI KYC Guidelines v2024", "SEBI Guidelines v2024"])
        latest_version = st.selectbox("Latest Version", ["RBI KYC Guidelines v2025", "SEBI Guidelines v2025"])
        
        if st.button("Analyze Changes", use_container_width=True):
            st.success("Analysis Complete!")
            
            st.markdown("### Key Changes Identified")
            
            st.markdown("""
            <div class="change-removed">
                <b>❌ Removed</b><br>
                <small>Section 3.2: Manual document verification acceptable</small>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("""
            <div class="change-added">
                <b>✅ Added</b><br>
                <small>Section 3.2: Digital verification mandatory for all customers</small>
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("""
            <div class="change-modified">
                <b>🔄 Modified</b><br>
                <small>Section 4.1: Timeline extended from 30 to 45 days</small>
            </div>
            """, unsafe_allow_html=True)
    
    with col2:
        st.subheader("AI Interpretation")
        
        st.info("""
        **What Changed:** Manual KYC verification is no longer acceptable.
        
        **Why It Matters:** This increases compliance requirements and may require system updates.
        
        **Action Required:** Update onboarding system to use digital verification by Dec 31, 2025.
        """)

# ============================================================================
# IMPACT ASSESSMENT PAGE
# ============================================================================
elif page == "Impact Assessment":
    
    categories = ["Product & Onboarding", "Risk & Compliance", "Operations", "Technology"]
    
    impact_descriptions = {
        "Product & Onboarding": "Changes require updates to KYC flow, customer verification process, and documentation templates.",
        "Risk & Compliance": "New compliance requirements add 5-7 steps to audit checklist. Risk score increases without mitigation.",
        "Operations": "Manual process review required. Estimated 40 hours of team effort for implementation.",
        "Technology": "API integrations need update. Estimated 2-3 weeks for development and testing."
    }
    
    for category in categories:
        with st.expander(f"#### {category} - High Impact"):
            col1, col2 = st.columns([1, 4])
            
            with col1:
                st.metric("Impact Level", "High")
            
            with col2:
                st.progress(0.75)
            
            st.markdown(f"**Description:** {impact_descriptions[category]}")

# ============================================================================
# ACTION ITEMS PAGE
# ============================================================================
elif page == "Action Items":
    
    actions = [
        {"task": "Update KYC process documentation", "owner": "Compliance Team", "deadline": "Dec 10, 2025", "status": "In Progress"},
        {"task": "Deploy digital verification API", "owner": "Engineering", "deadline": "Dec 20, 2025", "status": "Not Started"},
        {"task": "Audit current customer data", "owner": "Risk Team", "deadline": "Dec 5, 2025", "status": "Completed"},
        {"task": "Train staff on new guidelines", "owner": "HR", "deadline": "Dec 15, 2025", "status": "In Progress"},
    ]
    
    # Create DataFrame
    df = pd.DataFrame(actions)
    
    # Display with conditional formatting
    for idx, action in enumerate(actions):
        status_color = "🟢" if action["status"] == "Completed" else "🟡" if action["status"] == "In Progress" else "🔴"
        
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col1:
            st.markdown(f"**{action['task']}**")
            st.caption(f"Owner: {action['owner']} | Due: {action['deadline']}")
        
        with col2:
            st.write(f"{status_color} {action['status']}")
        
        with col3:
            st.button("Edit", key=f"edit_{idx}")
        
        st.divider()

# ============================================================================
# COMPLIANCE REPORTS PAGE
# ============================================================================
elif page == "Compliance Reports":
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Monthly Compliance Summary")
        
        report_data = {
            "Regulations Reviewed": "24",
            "Actions Completed": "18",
            "Pending Actions": "3",
            "Non-Compliance Risk": "2%"
        }
        
        for metric, value in report_data.items():
            st.metric(metric, value)
        
        st.download_button(
            label="📥 Download Report",
            data="Report data here",
            file_name="compliance_report.pdf",
            mime="application/pdf",
            use_container_width=True
        )
    
    with col2:
        st.subheader("Generate Custom Report")
        
        report_type = st.selectbox(
            "Select Report Type",
            ["Audit Trail Report", "Risk Assessment Report", "Regulatory Timeline"]
        )
        
        time_period = st.selectbox(
            "Time Period",
            ["Last 30 Days", "Last 90 Days", "Last Year"]
        )
        
        if st.button("Generate Report", use_container_width=True):
            st.success(f"✅ Generated {report_type} for {time_period}")

# ============================================================================
# AI ASSISTANT PAGE (Chatbot)
# ============================================================================
elif page == "AI Assistant":
    st.markdown("Ask questions about regulations, compliance requirements, and implementation guidance")
    
    # Initialize chat history
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = [
            {
                "role": "assistant",
                "content": "Hello! I'm ComplyNext AI Assistant. I can help you understand regulations, explain compliance requirements, answer questions about recent updates, and guide you through implementation steps. What would you like to know?",
                "sources": []
            }
        ]
    
    # Display chat history
    for message in st.session_state.chat_history:
        with st.chat_message(message["role"]):
            st.write(message["content"])
            
            if message.get("sources"):
                st.caption("**Sources:**")
                for source in message["sources"]:
                    st.caption(f"📄 {source['name']} ({source['type']})")
    
    # Suggested questions (shown on first load)
    if len(st.session_state.chat_history) == 1:
        st.markdown("---")
        st.subheader("Suggested Questions:")
        
        suggested_questions = [
            "What are the new KYC requirements?",
            "How do I comply with SEBI data protection?",
            "What changed in MCA regulations?",
            "Timeline for implementation?"
        ]
        
        cols = st.columns(2)
        for idx, question in enumerate(suggested_questions):
            with cols[idx % 2]:
                if st.button(question, use_container_width=True):
                    st.session_state.chat_input = question
    
    # Chat input
    st.markdown("---")
    user_input = st.chat_input("Ask about regulations, compliance requirements, or implementation...")
    
    if user_input:
        # Add user message
        st.session_state.chat_history.append({
            "role": "user",
            "content": user_input,
            "sources": []
        })
        
        with st.chat_message("user"):
            st.write(user_input)
        
        # Simulate bot response
        bot_response = {
            "role": "assistant",
            "content": """Based on the latest RBI guidelines, here's what you need to know:

1. **KYC verification must now be digital-only** - Manual verification is no longer acceptable
2. **Timeline extended to 45 days** - You have more time for implementation
3. **Enhanced due diligence for high-risk customers** - Additional verification steps required

Would you like me to explain the business impact or help with implementation steps?""",
            "sources": [
                {"name": "RBI Circular 2025-11-24", "type": "regulation"},
                {"name": "KYC Guidelines v2025", "type": "document"}
            ]
        }
        
        st.session_state.chat_history.append(bot_response)
        
        with st.chat_message("assistant"):
            st.write(bot_response["content"])
            st.caption("**Sources:**")
            for source in bot_response["sources"]:
                st.caption(f"📄 {source['name']} ({source['type']})")
        
        st.rerun()
    
    st.markdown("---")
    st.caption("⚠️ ComplyNext AI uses RAG to retrieve and interpret regulations. Always verify critical compliance decisions with your legal team.")

# ============================================================================
# SETTINGS PAGE
# ============================================================================
elif page == "Settings":
    
    tab1, tab2, tab3 = st.tabs(["Regulatory Sources", "Notifications", "Integration"])
    
    with tab1:
        st.subheader("Regulatory Sources")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write("Select which regulatory sources to monitor:")
        
        rbi = st.checkbox("🏦 RBI", value=True)
        sebi = st.checkbox("📊 SEBI", value=True)
        mca = st.checkbox("📋 MCA", value=True)
        gazette = st.checkbox("📰 Gazette of India", value=True)
        
        if st.button("Save Source Settings", use_container_width=True):
            st.success("✅ Settings saved successfully!")
    
    with tab2:
        st.subheader("Notification Preferences")
        
        email_alerts = st.checkbox("📧 Email Alerts", value=True)
        high_priority = st.checkbox("⚠️ High Priority Only", value=False)
        weekly_digest = st.checkbox("📅 Weekly Digest", value=True)
        
        if st.button("Save Notification Settings", use_container_width=True):
            st.success("✅ Settings saved successfully!")
    
    with tab3:
        st.subheader("Integrations")
        
        st.write("Connect to external services:")
        
        if st.button("🔗 Connect to Slack", use_container_width=True):
            st.info("Redirecting to Slack authorization...")
        
        if st.button("📧 Connect to Email", use_container_width=True):
            st.info("Email integration configured")
        
        if st.button("📊 Connect to Jira", use_container_width=True):
            st.info("Jira integration configured")

