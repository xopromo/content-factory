import os
import sys
from pathlib import Path

# Load env variables
ROOT = Path(__file__).parent.parent
sys.path.append(str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except ImportError:
    pass

# Clear keys to force Pollinations fallback
os.environ["GEMINI_KEY"] = ""
os.environ["GROQ_KEY"] = ""
os.environ["GROQ_KEY_2"] = ""
os.environ["MISTRAL_KEY"] = ""
os.environ["CEREBRAS_KEY"] = ""

# Ensure mock is disabled
os.environ["MOCK_LLM"] = "0"

from scripts.utils.llm_client import run_claude_common, run_fast_common

print("Testing run_fast_common with Pollinations...")
try:
    res, tokens = run_fast_common("Say hello in one word", quality="simple")
    print(f"run_fast_common Success: '{res}' ({tokens} tokens)")
except Exception as e:
    print(f"run_fast_common Failed: {e}")

print("\nTesting run_claude_common with Pollinations...")
try:
    res, tokens = run_claude_common("Say hello in one word")
    print(f"run_claude_common Success: '{res}' ({tokens} tokens)")
except Exception as e:
    print(f"run_claude_common Failed: {e}")
