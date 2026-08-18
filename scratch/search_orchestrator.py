import re
import sys

# Reconfigure stdout to use utf-8 to avoid encoding errors on windows terminal
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

def search_file(filepath, pattern):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    for i, line in enumerate(lines, 1):
        if re.search(pattern, line, re.IGNORECASE):
            # Print with error replacement just in case
            safe_line = line.strip().encode('utf-8', errors='replace').decode('utf-8')
            print(f"{i}: {safe_line}")

print("--- orchestrator.py search: telegram ---")
search_file("c:/Users/асус/Desktop/клод/антигравити, всякое/content-factory/scripts/orchestrator.py", r"telegram|notify|tg_")
