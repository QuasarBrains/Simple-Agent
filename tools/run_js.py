from tools.index import Tool
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from utils.pubsub import PubSub
from typing import Any

def run(ps: PubSub, args: Any):
    if not args or "url" not in args:
        return "Error running web_request: No URL provided."
    if not "script" in args:
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

run_js = Tool(
    name="run_js",
    description="Run JavaScript code on a webpage",
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
                "description": "The JavaScript code to run on the webpage.",
            },
        },
        "required": ["url", "script"],
    },
)
