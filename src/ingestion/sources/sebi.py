import requests
from bs4 import BeautifulSoup
import json
import os
import time
import re
from datetime import datetime
from urllib.parse import urljoin
from config import Config


class SebiNotification:
    def __init__(self, start_date, end_date, delay=1):
        self.start_date = start_date
        self.end_date = end_date
        self.delay = delay

        self.base_list_url = "https://www.sebi.gov.in/sebiweb/ajax/home/getnewslistinfo.jsp"
        self.listing_ref = "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=6&smid=0"
        self.session = requests.Session()

        self.headers = {
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": self.listing_ref
        }

        self.payload = {
            "nextValue": "1",
            "next": "s",
            "search": "",
            "fromDate": self.start_date,
            "toDate": self.end_date,
            "fromYear": "",
            "toYear": "",
            "deptId": "-1",
            "sid": "1",
            "ssid": "-1",
            "smid": "0",
            "ssidhidden": "6",
            "intmid": "-1",
            "sText": "Legal",
            "ssText": "-- All Sub Section --",
            "smText": "",
            "doDirect": "-1"
        }

  
        self.download_dir = os.path.join(Config.DOWNLOAD_DIR, "sebi")
        self.json_file = os.path.join(Config.DOWNLOAD_DIR, "sebi_notifications.json")

        os.makedirs(self.download_dir, exist_ok=True)
        open(self.json_file, "w").close()


    def get_pdf_url(self, html_url):
        try:
            resp = self.session.get(html_url, timeout=30)
            soup = BeautifulSoup(resp.text, "html.parser")

            iframe = soup.find("iframe")
            if iframe and iframe.get("src"):
                src = iframe["src"]
                if src.startswith("http"):
                    return src
                if "file=" in src:
                    match = re.search(r"file=([^&]+)", src)
                    if match:
                        return urljoin("https://www.sebi.gov.in", match.group(1))

                return urljoin("https://www.sebi.gov.in", src.lstrip("./"))

            scripts = soup.find_all("script")
            for script in scripts:
                if script.string:
                    pdf_matches = re.findall(r'https://www\.sebi\.gov\.in/sebi_data/attachdocs/[^"\']+\.pdf', script.string)
                    if pdf_matches:
                        return pdf_matches[0]

            pdf_matches = re.findall(r'https://www\.sebi\.gov\.in/sebi_data/attachdocs/[^"\'\s]+\.pdf', resp.text)
            if pdf_matches:
                return pdf_matches[0]

            pdf_links = soup.find_all("a", href=re.compile(r'\.pdf$'))
            for link in pdf_links:
                href = link.get("href")
                if href:
                    return urljoin(html_url, href)

            embed = soup.find("embed", src=re.compile(r'\.pdf'))
            if embed and embed.get("src"):
                return urljoin(html_url, embed["src"])

            return None

        except Exception:
            return None


    def download_pdf(self, pdf_url, title):
        try:
            safe_title = re.sub(r'[^\w\s-]', '', title).strip()
            safe_title = re.sub(r'[-\s]+', '_', safe_title)

            original_name = pdf_url.split("/")[-1]
            if not original_name.endswith('.pdf'):
                original_name += '.pdf'

            fname = f"{safe_title}_{original_name}"[:150]
            if not fname.endswith('.pdf'):
                fname += '.pdf'

            out_path = os.path.join(self.download_dir, fname)

            if os.path.exists(out_path):
                return out_path

            r = self.session.get(pdf_url, stream=True, timeout=30)
            if r.status_code == 200:
                with open(out_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                return out_path
            return None

        except Exception:
            return None

    def fetch_page(self, page):
        self.payload["nextValue"] = str(page)
        self.payload["next"] = "n" if page > 1 else "s"

        try:
            resp = self.session.post(self.base_list_url, data=self.payload, headers=self.headers, timeout=30)
            if resp.status_code == 200:
                return resp.text
            return None
        except Exception:
            return None

    def parse_list_page(self, html):
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.select("table tr")[1:]
        data = []

        for r in rows:
            cols = r.find_all("td")
            if len(cols) < 2:
                continue

            date = cols[0].get_text(strip=True)
            a = cols[1].find("a")
            if a:
                detail_url = a["href"]
                if not detail_url.startswith("http"):
                    detail_url = urljoin("https://www.sebi.gov.in", detail_url)

                data.append({
                    "date": date,
                    "title": a.get_text(strip=True),
                    "detail_url": detail_url
                })
        return data

    def save_record(self, record):
        existing_urls = [r.get("detail_url") for r in self.saved_records]
        if record["detail_url"] not in existing_urls:
            self.saved_records.append(record)
            with open(self.json_file, "w", encoding="utf-8") as f:
                json.dump(self.saved_records, f, indent=2, ensure_ascii=False)
            return True
        return False

    def crawl(self, max_pages=200):
        print(f"Starting SEBI crawl from {self.start_date} to {self.end_date}")

        for page in range(1, max_pages + 1):
            html = self.fetch_page(page)
            if not html:
                break

            entries = self.parse_list_page(html)
            if not entries:
                print("No more notifications found.")
                break

            print(f"Page {page}: {len(entries)} notifications")

            for item in entries:
                pdf_url = self.get_pdf_url(item["detail_url"])
                file_path = None

                if pdf_url:
                    file_path = self.download_pdf(pdf_url, item["title"])

                record = {
                    "source": "SEBI",
                    "source_url": self.listing_ref,
                    "source_type": "Notification",
                    "date": item["date"],
                    "title": item["title"],
                    "detail_url": item["detail_url"],
                    "type": "File" if pdf_url else "Text",
                    "file_url": pdf_url,
                    "file_path": file_path,
                    "downloaded_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }

                self.save_record(record)
                time.sleep(self.delay)

        print("Crawl complete.")
        print(f"Total records: {len(self.saved_records)}")


if __name__ == "__main__":
    crawler = SebiNotification("01-01-2015", "10-11-2025", delay=1)
    crawler.crawl()