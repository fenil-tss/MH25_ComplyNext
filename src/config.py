import os
import logging
import dotenv

dotenv.load_dotenv()

class Config:
    
    ## DATABASE CONFIG
    PG_HOST = os.getenv("PG_HOST")
    PG_PORT = os.getenv("PG_PORT")
    PG_USER = os.getenv("PG_USER")
    PG_PASSWORD = os.getenv("PG_PASSWORD")
    PG_DATABASE = os.getenv("PG_DATABASE")

    ## SETUP
    DOWNLOAD_DIR = "downloads"
    
    ## AI CONFIG
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    OPENAI_TIMEOUT = 60
    OPENAI_RETRY = 3
    OPENAI_GPT4 = "gpt-4.1"
    
    ## EMBEDDINGS CONFIG
    EMBEDDING_MODEL= "text-embedding-3-small"
    EMBEDDING_SIZE = 1536

    ## LOGGING
    LOGGING_LEVEL = logging.DEBUG
