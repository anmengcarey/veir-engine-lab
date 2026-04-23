"""
websearch_test.py
Confirms that the OpenAI API key has access to the web search tool
via the Responses API (gpt-4o / gpt-4o-mini with built-in web search).
"""

import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise EnvironmentError("OPENAI_API_KEY not found. Set it in your .env file.")

client = OpenAI(api_key=api_key)

print("Testing OpenAI web search capability...")
print("-" * 50)

try:
    response = client.responses.create(
        model="gpt-4o-mini",
        tools=[{"type": "web_search_preview"}],
        input="What is today's date and top tech headline right now?",
    )

    # Print the output text
    for item in response.output:
        if hasattr(item, "content"):
            for block in item.content:
                if hasattr(block, "text"):
                    print("Response:", block.text)

    print("-" * 50)
    print("Web search is AVAILABLE on this API key.")

except Exception as e:
    error_msg = str(e)
    print(f"Error: {error_msg}")
    if "tool" in error_msg.lower() or "not supported" in error_msg.lower() or "permission" in error_msg.lower():
        print("Web search does NOT appear to be available for this API key/tier.")
    else:
        print("An unexpected error occurred — check your API key and account status.")
