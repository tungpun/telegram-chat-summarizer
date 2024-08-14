
import threading

from collections import defaultdict

import schedule
import time
import json


from communication import GroupChatScrapper, EnvoyBot
from summarization import Summarizer

from config import *


def split_into_blocks(content, lines_per_block=30):
    lines = content.split('\n')
    blocks = [lines[i:i + lines_per_block] for i in range(0, len(lines), lines_per_block)]
    return ['\n'.join(block) for block in blocks]


if __name__ == "__main__":

    # Validate user prompts
    for c in app_config.chats_to_summarize:
        with open(c.summarization_prompt_path, "r") as f:
            Summarizer.validate_summarization_prompt(f.read())

    # Declare global LLM context storage
    llm_contexts = defaultdict(dict)
    llm_contexts_lock = threading.Lock()


    def chat_callback(input_message_text, sender, context_name, send_message_func):
        with llm_contexts_lock:
            envoy_bot.set_typing_status([sender], llm_contexts_lock.locked)
            if not context_name in llm_contexts or not sender in llm_contexts[context_name]:
                send_message_func(f"No context is available for {context_name} yet")
                return
            logger.info(f"Chatting with: {sender}")
            response = llm_contexts[context_name][sender].predict(human_input=input_message_text)
            logger.debug(f"Response to message \"{input_message_text}\" from {sender}: \"{response}\"")
            send_message_func(response)


    summarizer = Summarizer(app_config.openai_api_key)
    group_chat_scrapper = GroupChatScrapper(app_config.telegram_api_id, app_config.telegram_api_hash)
    envoy_bot = EnvoyBot(
        app_config.telegram_bot_auth_token,
        app_config.telegram_summary_receivers,
        [c.id for c in app_config.chats_to_summarize],
        chat_callback
    )


    def summarization_job(chat_cfg, summarization_prompt, summary_receivers):
        logger.info(f"Running summarization job for: {chat_cfg.id}")
        with llm_contexts_lock:

            logger.info("Seting typing status")
            # Set the "typing" status for the bot
            envoy_bot.set_typing_status(summary_receivers, llm_contexts_lock.locked)

            # Scrap messages for the given chat
            messages, chat_title = group_chat_scrapper.get_message_history(int(chat_cfg.id), chat_cfg.lookback_period_seconds)


            logger.info(
                f"Scrapped {len(messages)} messages for {chat_cfg.id} over the last {chat_cfg.lookback_period_seconds} seconds")
            serialized_messages = json.dumps({"messages": messages}, ensure_ascii=False)

            
            logger.info("Summarizing messages")
            # Summarize messages
            summary, context = summarizer.summarize(serialized_messages, summarization_prompt)

            logger.info("Sending summary")
            # Send the summary and update LLM context
            for u in summary_receivers:
                llm_contexts[chat_cfg.id][u] = context
                logger.info(f"Sending summary for {chat_cfg.id} to {u}")
                logger.debug(f"Summary for {chat_title}: {summary}")
                chat_lookback_period_hours = int(chat_cfg.lookback_period_seconds / 60 / 60)
                content = f"Summary for <b>{chat_cfg.id}</b> for the last {chat_lookback_period_hours} hours:\n\n{summary}"
                
                for block in split_into_blocks(content):
                    envoy_bot.send_summary(
                        u,
                        block,
                        chat_cfg.id
                    )
                    time.sleep(1)

            logger.info("Summarization job finished")



    # Setup recurring summarization jobs
    for chat_config in app_config.chats_to_summarize:
        with open(chat_config.summarization_prompt_path, "r") as f:
            chat_summarization_prompt = f.read()
        schedule.every(chat_config.lookback_period_seconds).seconds.do(
            job_func=summarization_job,
            chat_cfg=chat_config,
            summarization_prompt=chat_summarization_prompt,
            summary_receivers=app_config.telegram_summary_receivers
        )

    # Run the jobs for the first time
    schedule.run_all()
    while True:
        schedule.run_pending()
        time.sleep(5)
