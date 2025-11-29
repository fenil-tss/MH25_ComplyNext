import json
from datetime import datetime
from ingestion.sources.rbi import RBICrawler
from ingestion.doc_loader import get_content_from_file
from openai_manager.connector import openai_manager
from database_manager import dao
from utils import root_logger


def run_rbi_scraper():
    start_date = datetime(2025, 1, 1)
    end_date = datetime.now().date()
    crawler = RBICrawler(
        start_date=start_date.strftime("%Y-%m-%d"), 
        end_date=end_date.strftime("%Y-%m-%d"),
        results_per_page=10
    )
    crawler.crawl()
    return crawler.json_file


def load_documents_in_database(jsonpath):
    all_existing_docs = dao.get_all_existing_documents()
    documents_list = map(json.loads, open(jsonpath, errors='ignore').readlines())
    for document in documents_list:
        doc_name = document['filepath']
        if document['fileurl'] in all_existing_docs:
            root_logger.debug(f"Skipping existing document : {doc_name}")
            continue

        document_text = get_content_from_file(document)
        if not document_text:
            root_logger.debug(f"Skipping unreadable document : {doc_name}")
            continue
        
        if document_text != openai_manager.trim(document_text, max_tokens=1024 * 8):
            continue

        nodes = openai_manager.get_nodes_from_document(document_text)
        if not nodes:
            root_logger.debug(f"Skipping document with zero nodes : {doc_name}")
            continue
        
        dao.save_document_and_nodes(document, nodes)


if __name__ == '__main__':
    # jsonpath = run_rbi_scraper()
    jsonpath = "downloads/rbi_notifications.json"
    load_documents_in_database(jsonpath)
