from tools.index import Tool
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from utils.pubsub import PubSub
from typing import Any
from bs4 import BeautifulSoup
import requests


def run(args: Any, ps: PubSub):
    if not args or "url" not in args:
        return "Error running web_request: No URL provided."
    if "script" not in args:
        return "Error running run_js: No script provided."

    url = args["url"]
    script = args["script"]

    driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()))

    try:
        driver.get(url)
        # Execute the JavaScript code
        result = driver.execute_script(script)

        return f"JavaScript result:\n```\n{result}\n```"
    except Exception as err:
        return f"Error occurred: {err}"
    finally:
        driver.quit()


run_javascript = Tool(
    name="run_javascript",
    description="Run JavaScript on a webpage and return the result.",
    function=run,
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the webpage to run the JavaScript on.",
            },
            "script": {
                "type": "string",
                "description": "The JavaScript code to run on the webpage. Make sure to return a value.",
            },
        },
        "required": ["url", "script"],
    },
)


def run_bs(args: Any, ps: PubSub):
    if not args or "url" not in args:
        return "Error running run_beautiful_soup: No URL provided."
    if "method" not in args:
        return "Error running run_beautiful_soup: No method provided."
    if "arguments" not in args:
        return "Error running run_beautiful_soup: No arguments provided."

    url = args["url"]
    method = args["method"]
    arguments = args["arguments"]

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")

        if not hasattr(soup, method):
            return f"Error: BeautifulSoup object has no method '{method}'"

        method_to_call = getattr(soup, method)
        result = method_to_call(*arguments)

        return f"BeautifulSoup result:\n```\n{result}\n```"
    except Exception as err:
        return f"Error occurred: {err}"


run_beautiful_soup = Tool(
    name="run_beautiful_soup",
    description="Run a BeautifulSoup method on a webpage and return the result.",
    function=run_bs,
    parameters={
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL of the webpage to run the BeautifulSoup method on.",
            },
            "method": {
                "type": "string",
                "description": "The BeautifulSoup method to run on the webpage.",
            },
            "arguments": {
                "type": "array",
                "items": {
                    "type": "string",
                },
                "description": "The list of arguments to pass to the BeautifulSoup method.",
            },
        },
        "required": ["url", "method", "arguments"],
    },
)
