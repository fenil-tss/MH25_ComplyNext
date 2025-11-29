import re
import json
import requests
import os
import csv
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from typing import List, Dict, Set, Optional


# =====================================================
#                BASIC HELPERS
# =====================================================

def fetch_html(url: str) -> Optional[str]:
    """Fetch page HTML with timeout and realistic headers."""
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/129.0 Safari/537.36"
            )
        }
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.text
    except Exception as e:
        print(f"[ERROR] Failed to fetch {url}: {e}")
        return None


def normalize_base_url(url: str) -> str:
    """Return clean base URL (scheme + domain)."""
    if not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}"


def soupify(html: str):
    return BeautifulSoup(html, "html.parser")


# =====================================================
#     EMAIL / PHONE EXTRACTION
# =====================================================

def extract_emails(soup) -> Set[str]:
    emails = set()
    text = soup.get_text(" ", strip=True)
    email_pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    emails.update(re.findall(email_pattern, text))

    for a in soup.find_all("a", href=True):
        if a["href"].startswith("mailto:"):
            email = a["href"][7:].split("?")[0]
            emails.add(email)
    return emails


def extract_phones(soup) -> Set[str]:
    text = soup.get_text(" ", strip=True)
    phone_pattern = r"\+?\d[\d\-\s()]{7,}\d"
    phones = set()
    for match in re.findall(phone_pattern, text):
        cleaned = re.sub(r"\s+", " ", match).strip()
        if len(cleaned.replace("-", "").replace(" ", "").replace("(", "").replace(")", "")) >= 8:
            phones.add(cleaned)
    return phones


# =====================================================
#            LINK DISCOVERY
# =====================================================

def find_links(soup, base_url: str, keywords: List[str]) -> List[str]:
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"].lower()
        text = a.get_text(strip=True).lower()

        if any(k in href or k in text for k in keywords):
            full_url = urljoin(base_url, a["href"])
            links.append(full_url)

    # Remove duplicates but preserve order
    seen = set()
    unique_links = []
    for link in links:
        if link not in seen:
            seen.add(link)
            unique_links.append(link)
    return unique_links


# =====================================================
#       CLEAN TEXT EXTRACTION UTILS
# =====================================================

def strip_layout(soup):
    """Remove noise tags."""
    for tag in ["script", "style", "noscript", "header", "footer", "nav", "aside", "svg"]:
        for t in soup.find_all(tag):
            t.decompose()
    return soup


def extract_section_text(soup, keywords: List[str], min_len: int = 100) -> str:
    soup = strip_layout(soup)
    page_text_lower = soup.get_text().lower()

    if not any(k in page_text_lower for k in keywords):
        return ""

    candidates = []

    # Try to find meaningful blocks containing keywords
    for elem in soup.find_all(text=True):
        if not elem.strip():
            continue
        if any(k in elem.lower() for k in keywords):
            parent = elem
            for _ in range(4):  # climb up a few levels
                if parent is None:
                    break
                if parent.name in ["div", "section", "article", "main", "li"]:
                    text = parent.get_text(" ", strip=True)
                    if len(text) > min_len:
                        candidates.append(text)
                parent = parent.parent

    if candidates:
        return max(candidates, key=len)[:3000]

    # Fallback: get all main text
    main_text = soup.get_text(" ", strip=True)
    return main_text[:3000] if len(main_text) > min_len else ""


def extract_product_details(soup, page_url: str) -> Dict[str, str]:
    """Extract structured product/service info from a single page."""
    soup = strip_layout(soup)

    title = soup.find("h1")
    if not title:
        title = soup.find("title")
    title_text = title.get_text(strip=True) if title else ""

    desc = soup.find("meta", attrs={"name": "description"})
    if desc:
        description = desc.get("content", "").strip()
    else:
        og_desc = soup.find("meta", property="og:description")
        description = og_desc.get("content", "").strip() if og_desc else ""

    if len(description) < 50:
        description = extract_section_text(
            soup,
            keywords=["product", "service", "solution", "feature", "benefit", "overview"],
            min_len=80
        )

    return {
        "title": title_text or "Product/Service Page",
        "description": description or "No description found.",
        "url": page_url
    }


def meta_description(soup) -> str:
    tag = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", property="og:description")
    return tag["content"].strip() if tag and tag.get("content") else ""



def scrape_company(url: str) -> Dict:
    base_url = normalize_base_url(url)
    print(f"[INFO] Starting scrape for: {base_url}")

    home_html = fetch_html(base_url)
    if not home_html:
        print("[ERROR] Could not load homepage.")
        return {}

    home_soup = soupify(home_html)

    # Keywords
    contact_keywords = ["contact", "support", "help", "reach", "team", "get in touch"]
    about_keywords = ["about", "about-us", "story", "company", "who-we-are", "mission", "vision"]
    product_keywords = [
        "product", "products", "service", "services", "solution", "solutions",
        "offering", "platform", "technology", "software", "tool", "what we do",
        "our work", "portfolio", "features", "pricing", "plans"
    ]

    contact_links = find_links(home_soup, base_url, contact_keywords)[:4]
    about_links = find_links(home_soup, base_url, about_keywords)[:3]
    product_links = find_links(home_soup, base_url, product_keywords)[:10]

    # ===================================
    # 1. Collect contact info
    # ===================================
    all_emails = set()
    all_phones = set()
    pages_to_scan = [base_url] + contact_links + about_links + product_links[:3]

    checked = set()
    for page in pages_to_scan:
        if page in checked:
            continue
        checked.add(page)
        html = fetch_html(page)
        if not html:
            continue
        soup = soupify(html)
        all_emails.update(extract_emails(soup))
        all_phones.update(extract_phones(soup))

    # ===================================
    # 2. About section
    # ===================================
    about_text = ""
    about_url = ""

    for link in about_links + [base_url]:
        html = fetch_html(link)
        if not html:
            continue
        soup = soupify(html)
        text = extract_section_text(soup, keywords=["about", "mission", "vision", "founded", "team"])
        if text and len(text) > 120:
            about_text = text
            about_url = link
            break

    if not about_text:
        about_text = meta_description(home_soup) or "No about information found."

    # ===================================
    # 3. Products / Services
    # ===================================
    products_services = []

    seen_urls = set()
    for link in product_links:
        if link in seen_urls:
            continue
        seen_urls.add(link)

        print(f"[INFO] Extracting product details from: {link}")
        html = fetch_html(link)
        if not html:
            continue

        soup = soupify(html)
        prod_info = extract_product_details(soup, link)

        if len(prod_info["description"]) > 50:
            products_services.append(prod_info)

    # Fallback if none found
    if not products_services:
        fallback = extract_product_details(home_soup, base_url)
        if len(fallback["description"]) > 100:
            products_services.append(fallback)

    # ===================================
    # FINAL RESULT
    # ===================================
    result = {
        "website": base_url,
        "scraped_at": __import__("datetime").datetime.now().isoformat(),
        "emails": sorted(all_emails),
        "phones": sorted(all_phones),
        "about": {
            "text": about_text,
            "source_url": about_url or base_url
        },
        "products_services": products_services,
        "product_pages_visited": len(products_services),
    }

    return result


# =====================================================
#              CSV → MERGED JSON HANDLING
# =====================================================

RESULT_JSON = "merged_results.json"


def load_existing_results():
    if os.path.exists(RESULT_JSON):
        try:
            with open(RESULT_JSON, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return []
    return []


def append_result(data: dict):
    existing = load_existing_results()
    existing.append(data)

    with open(RESULT_JSON, "w", encoding="utf-8") as f:
        json.dump(existing, f, indent=4, ensure_ascii=False)

    print(f"[APPEND] Saved -> {data.get('website')}")


def scrape_from_csv(csv_path: str, url_column: str = "url"):
    if not os.path.exists(csv_path):
        print(f"[ERROR] CSV file not found: {csv_path}")
        return

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if url_column not in reader.fieldnames:
            print(f"[ERROR] Column '{url_column}' not found in CSV.")
            print("Available columns:", reader.fieldnames)
            return

        for row in reader:
            url = row[url_column].strip()
            if not url:
                continue

            print("\n" + "=" * 80)
            print(f"[SCRAPING] {url}")
            print("=" * 80)

            data = scrape_company(url)
            if data:
                append_result(data)



if __name__ == "__main__":
    print("CSV → Company Scraper → JSON Merger\n")

    csv_path = input("Enter CSV file path: ").strip()
    url_column = input("Enter CSV column name containing URLs (default: url): ").strip()

    if not url_column:
        url_column = "url"

    scrape_from_csv(csv_path, url_column)
