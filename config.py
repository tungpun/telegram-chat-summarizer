import logging
import argparse
from pydantic import BaseModel, Field
from typing import List, Union


parser = argparse.ArgumentParser()
parser.add_argument("path_to_config")
args = parser.parse_args()


class SummarizationConfig(BaseModel):
    id: Union[str, int]
    lookback_period_seconds: int
    summarization_prompt_path: str


class AppConfig(BaseModel):
    log_level: str = Field(default="INFO")
    telegram_api_id: int
    telegram_api_hash: str
    telegram_bot_auth_token: str
    openai_api_key: str
    chats_to_summarize: List[SummarizationConfig]
    telegram_summary_receivers: List[str]



app_config = AppConfig.parse_file(args.path_to_config)



# Initialize logger
logger = logging.getLogger("CSB")
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(levelname)s - %(message)s'))
logger.addHandler(handler)
logger.setLevel(app_config.log_level)
logger.info("Started!")
