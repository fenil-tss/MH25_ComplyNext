import logging
from config import Config
from openai import OpenAI
from langchain_openai import OpenAIEmbeddings


#############################################
# LOGGING
#############################################
logging.basicConfig(
    level= Config.LOGGING_LEVEL,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler()]  # ensure console output
)
root_logger = logging.getLogger()

## Disable library logging
logging.getLogger("openai._base_client").setLevel(logging.ERROR)
logging.getLogger("httpcore.http11").setLevel(logging.ERROR)
logging.getLogger("httpcore.connection").setLevel(logging.ERROR)
logging.getLogger("httpx").setLevel(logging.ERROR)

#############################################
# OPENAI
#############################################
openai_client = OpenAI(
    api_key=Config.OPENAI_API_KEY,
    max_retries=Config.OPENAI_RETRY,
    timeout=Config.OPENAI_TIMEOUT
)

openai_embed_model= OpenAIEmbeddings(
    model=Config.EMBEDDING_MODEL,
    dimensions=Config.EMBEDDING_SIZE,
    client=openai_client
)
