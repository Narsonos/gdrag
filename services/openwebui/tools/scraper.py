"""
title: Simple Web Scrape
author: Narsonos
description: A simple web scraping tool, that does not use jina as the original one.
original_author: Pyotr Growpotkin
original_author_url: https://github.com/christ-offer/
original_git_url: https://github.com/christ-offer/open-webui-tools
version: 0.0.1
license: None
requirements: httpx bs4
"""

import httpx
from typing import Callable, Any
import re, bs4 
from pydantic import BaseModel, Field

import unittest


def extract_title(text):
    """
    Extracts the title from a string containing structured text.

    :param text: The input string containing the title.
    :return: The extracted title string, or None if the title is not found.
    """
    match =  re.search(r"<title>(.*?)</title>", text, re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


def clean_urls(text) -> str:
    """
    Cleans URLs from a string containing structured text.

    :param text: The input string containing the URLs.
    :return: The cleaned string with URLs removed.
    """
    return re.sub(r"\((http[^)]+)\)", "", text)


class EventEmitter:
    def __init__(self, event_emitter: Callable[[dict], Any] = None):
        self.event_emitter = event_emitter

    async def progress_update(self, description):
        await self.emit(description)

    async def error_update(self, description):
        await self.emit(description, "error", True)

    async def success_update(self, description):
        await self.emit(description, "success", True)

    async def emit(self, description="Unknown State", status="in_progress", done=False):
        if self.event_emitter:
            await self.event_emitter(
                {
                    "type": "status",
                    "data": {
                        "status": status,
                        "description": description,
                        "done": done,
                    },
                }
            )


class Tools:
    class Valves(BaseModel):
        pass

    class UserValves(BaseModel):
        CLEAN_CONTENT: bool = Field(
            default=True,
            description="Remove links and image urls from scraped content",
        )

    def __init__(self):
        self.valves = self.Valves()

    async def web_scrape(
        self,
        url: str,
        __event_emitter__: Callable[[dict], Any] = None,
        __user__: dict = {},
    ) -> str:
        """
        Scrape a web page and extract text using BeautifulSoup.

        :param url: The URL of the web page to scrape.
        :return: The scraped and processed webpage content, or an error message.
        """
        emitter = EventEmitter(__event_emitter__)
        if "valves" not in __user__:
            __user__["valves"] = self.UserValves()

        await emitter.progress_update(f"Scraping {url}")

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as e:
            exception_desc = str(e)
            error_message = f'Error occured while scraping: {exception_desc if exception_desc else e.__class__.__name__}'
            await emitter.error_update(f"Failed to scrape: {error_message}")
            return error_message


        await emitter.progress_update("Received content, cleaning up ...")
        #NOTE: I decided to stick with BS4 instead of trafilatura, since it does not catch what i'd like to catch for my targets
        soup = bs4.BeautifulSoup(response.text, "html.parser")
        title_tag = soup.find("title")
        title = title_tag.get_text(strip=True) if title_tag else None

        #Removing modals and trash headers
        for tag in soup(["script", "style", "header", "nav", "head", "footer"]):
            tag.decompose()
        for popup in soup.find_all(attrs={"aria-modal": "true"}):
            popup.decompose()
        for popup in soup.find_all(attrs={"role": "dialog"}):
            popup.decompose()

        #Searching for footer comment and removing all beyond
        html_str = str(soup)
        footer_index = html_str.find("<!--footer-->")
        if footer_index != -1:
            truncated_html = html_str[:footer_index]
            soup = bs4.BeautifulSoup(truncated_html, "html.parser")
        text = soup.get_text(" ", strip=True)

        content = clean_urls(text) if __user__["valves"].CLEAN_CONTENT else text
        await emitter.success_update(
            f"Successfully Scraped {title if title else url}"
        )
        return ("Title: " + title + "\n" if title else "") + content


class WebScrapeTest(unittest.IsolatedAsyncioTestCase):
    async def test_web_scrape(self):
        url = "https://toscrape.com"
        content = await Tools().web_scrape(url)
        self.assertTrue(content.startswith('Title: Scraping Sandbox'))



if __name__ == "__main__":
    print("Running tests...")
    unittest.main()
