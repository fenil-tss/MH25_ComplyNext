import os
import io
import base64
import json
import time
import tiktoken
import functools
from config import Config
from openai import OpenAI
from .prompts import PROMPTS
from traceback import format_exc
from utils import root_logger


def retry(func):
    """
    Generic retry decorator for class methods or standalone functions.
    """
    delay = 1
    backoff = 1

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        cur_attempt = 0
        cur_delay = delay

        for cur_attempt in range(Config.OPENAI_RETRY):
            try:
                return func(*args, **kwargs)
            
            except Exception as e:
                root_logger.warning(
                    f"{func.__name__} attempt {cur_attempt} failed: {e}. "
                    f"Retrying in {cur_delay}s..."
                )
                time.sleep(cur_delay)
                cur_delay *= backoff  # exponential backoff

        root_logger.exception(
            f"{func.__name__} failed after {Config.OPENAI_RETRY} attempts: {format_exc()}"
        )
        
    return wrapper


class OPENAI_MANAGER:
    TIMEOUT = Config.OPENAI_TIMEOUT
    RETRY_TIMES = Config.OPENAI_RETRY
    CACHE_PATH = os.path.join(Config.DOWNLOAD_DIR, "embedding.cache")

    def __init__(self):
        self.openai_client = OpenAI(
            api_key=Config.OPENAI_API_KEY,
            max_retries=self.RETRY_TIMES,
            timeout=self.TIMEOUT,
        )
        self.embedding_cache = {}
        self._load_embedding_cache()
    

    def _load_embedding_cache(self):
        self.embedding_cache = {}
        try:
            if os.path.exists(self.CACHE_PATH):
                with open(self.CACHE_PATH, "r") as fp:
                    self.embedding_cache.update(json.load(fp))
        except Exception:
            root_logger.error(f"Error in loading embedding cache : {format_exc()}")

    def _save_embedding_cache(self):
        with open(self.CACHE_PATH, "w") as fp:
            json.dump(self.embedding_cache, fp)

    def trim(self, text, encoding_name="cl100k_base", max_tokens=32768):
        encoding = tiktoken.get_encoding(encoding_name)
        tokens = encoding.encode(text)
        tokens = tokens[:max_tokens]
        return encoding.decode(tokens)

    @retry
    def get_embeddings(self, text, **models_kwargs):
        """
        Returns vector embeddings for the given text.
        """
        cleaned = text.strip()
        if (cleaned) and (cleaned not in self.embedding_cache):    
            response = self.openai_client.embeddings.create(
                model=Config.EMBEDDING_MODEL,
                dimensions=Config.EMBEDDING_SIZE,
                input=cleaned,
                **models_kwargs,
            )
            embedding = response.data[0].embedding
            self.embedding_cache[cleaned] = embedding
        
        return self.embedding_cache.get(cleaned)
        

    def _to_base64(self, image):
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return image_base64

    def get_text_from_image(self, image, **model_kwargs):
        image_base64 = self._to_base64(image)
        prompt = PROMPTS.GET
        self._execute(prompt, **model_kwargs)

    def get_text_from_text(self, prompt, text, **models_kwargs):
        prompt = "\n".join(["/no_think", prompt, text.strip()])
        return self._execute(prompt, **models_kwargs)

    @retry
    def get_nodes_from_document(self, document):
        # Let exception raise here so retry can catch it. 
        results = openai_manager.openai_client.responses.create(
            model=Config.OPENAI_GPT4,
            input=[
                {"role": "system", "content": PROMPTS.GET_NODE_FROM_DOCUMENT},
                {"role": "user", "content": document},
            ],
            temperature=0,
        )
        try:
            results = json.loads(results.output[0].content[0].text)
        except Exception as e:
            results = []
        return results
    
    @retry
    def enrich_node(self, doc_node):
        try:
            for field in ["category_of_circular", "entity_type", "condition"]:
                value = doc_node.get(field)
                embedding = None
                if value:
                    embedding = self.get_embeddings(value)
                doc_node[f"{field}_em"] = embedding
        except Exception as e:
            root_logger.error(format_exc())
        return doc_node

    @retry
    def generate_dynamic_questions(self, user_prompt):
        response = self.openai_client.chat.completions.create(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[
                {"role": "system", "content": PROMPTS.DYNAMIC_QUESTION_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3
        )
        content = response.choices[0].message.content.strip()
        return content
    

openai_manager = OPENAI_MANAGER()


if __name__ == "__main__":
    print("Testing embeddings model...")
    embeddings = openai_manager.get_embeddings(
        "Open AI new Embeddings models is great."
    )
    print(embeddings, len(embeddings))
