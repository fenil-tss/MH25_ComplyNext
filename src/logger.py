import logging
from env import Config

logging.basicConfig(
    level= Config.LOGGING_LEVEL,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[logging.StreamHandler()]  # ensure console output
)
root_logger = logging.getLogger()

