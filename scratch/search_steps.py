import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

filepath = "c:/Users/асус/Desktop/клод/антигравити, всякое/content-factory/scripts/voice_bot.py"
with open(filepath, 'r', encoding='utf-8') as f:
    lines = f.readlines()

def print_around(line_num, radius=6):
    start = max(1, line_num - radius)
    end = min(len(lines), line_num + radius)
    print(f"\n--- Around line {line_num} ---")
    for i in range(start, end + 1):
        print(f"{i}: {lines[i-1].rstrip()}")

print_around(1088)
print_around(1181)
print_around(1278)
print_around(1562)
print_around(1768)
print_around(1831)
