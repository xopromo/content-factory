import os
import sys
import logging
from dotenv import load_dotenv

sys.path.append("scripts")
# Load .env
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT, ".env"))

from utils.llm_client import run_claude_common

# Configure basic logging to stdout to see the print statements
logging.basicConfig(level=logging.INFO)

def main():
    print("Testing run_claude_common with forced Gemini REST client (mimicking Render)...")
    import utils.llm_client as llm_client
    llm_client._gemini_client = None # Force REST client
    prompt = "Hello! Test connection. Respond with one word: OK."
    try:
        response, tokens = run_claude_common(prompt)
        print(f"Response: {response}")
        print(f"Tokens: {tokens}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
