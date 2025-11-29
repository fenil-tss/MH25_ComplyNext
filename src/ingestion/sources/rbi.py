import os
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from datetime import datetime
from config import Config
from utils import root_logger

class RBICrawler:
    BASE_URL = "https://website.rbi.org.in/web/rbi/notifications"

    def __init__(
        self,
        start_date,
        end_date,
        results_per_page=10,
        delay=1,
        json_file="rbi_notifications.json",
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.delta = results_per_page
        self.delay = delay
        self.session = requests.Session()
        self.download_dir = os.path.join(Config.DOWNLOAD_DIR, "rbi")
        self.json_file = os.path.join(Config.DOWNLOAD_DIR, json_file)
        os.makedirs(self.download_dir, exist_ok=True)
        open(self.json_file, "w").close()


    def fetch_page(self, start=1):
        """Fetch a single page of notifications"""
        params = {
            "publishDateFrom": self.start_date,
            "publishDateTo": self.end_date,
            "delta": self.delta,
            "start": start,
        }
        response = self.session.get(self.BASE_URL, params=params)
        response.raise_for_status()
        return response.text

    def parse_notifications(self, html):
        """Parse notification data from HTML"""
        soup = BeautifulSoup(html, "html.parser")
        notifications = []

        for div in soup.find_all("div", class_="col-12 grid-view-col"):
            try:
                inner = div.find("div", class_="notification-row-each-inner")

                # Date
                date_tag = inner.find("span", class_="notification-ymd")
                date = date_tag.get_text(strip=True) if date_tag else ""

                # Detail URL and Title
                a_tag = inner.find("a", class_="mtm_list_item_heading")
                detail_url = a_tag["href"] if a_tag else ""
                title_span = inner.find(
                    "span", class_="mtm_list_item_heading truncatedContent"
                )
                title = title_span.get_text(strip=True) if title_span else ""

                # Description
                desc_div = inner.find("div", class_="notifications-description")
                description = desc_div.get_text(strip=True) if desc_div else ""

                # PDF link
                pdf_link_tag = inner.find("a", class_="matomo_download")
                file_url = (
                    urljoin(self.BASE_URL, pdf_link_tag["href"]) if pdf_link_tag else ""
                )

                # Download PDF if exists
                file_path = ""
                if file_url:
                    base_name = os.path.basename(file_url)
                    base_name += ".pdf"
                    file_name = os.path.join(self.download_dir, base_name)

                    if not os.path.exists(file_name):
                        r = self.session.get(file_url)
                        with open(file_name, "wb") as f:
                            f.write(r.content)
                        time.sleep(self.delay)
                    file_path = file_name

                notifications.append(
                    {
                        "source": "RBI",
                        "source_url": self.BASE_URL,
                        "Source_Type": "Notification",
                        "date": date,
                        "title": title,
                        "description": description,
                        "detail_url": detail_url,
                        "Type": "File" if file_url else "Text",
                        "fileurl": file_url,
                        "filepath": file_path,
                        "downloaded_on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )
            except Exception as e:
                print("Error parsing a notification:", e)

        return notifications

    def crawl(self):
        """Crawl all pages"""
        start = 1
        while True:
            root_logger.debug(f"Started crawling page {start}")
            html = self.fetch_page(start=start)
            notifications = self.parse_notifications(html)
            if not notifications:
                break
            else:
                self.save_json(notifications)
                root_logger.info(f"Finished crawling page {start}")
            
            start += 1
            time.sleep(self.delay)

    def save_json(self, notifications):
        files = [x['fileurl'] for x in map(json.loads, open(self.json_file, errors="ignore").readlines())]
        with open(self.json_file, "a", encoding="utf-8") as fp:
            for notification in notifications:
                if notification['fileurl'] in files:
                    continue
                fp.write(json.dumps(notification, ensure_ascii=False) + "\n")



if __name__ == "__main__":
    crawler = RBICrawler(
        start_date="2025-01-01", 
        end_date="2025-10-31",
        results_per_page=10
    )
    crawler.crawl()