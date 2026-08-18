import re
from pathlib import Path

# Paths
orchestrator_path = Path(r"C:\Users\асус\Desktop\клод\антигравити, всякое\content-factory\scripts\orchestrator.py")
content = orchestrator_path.read_text(encoding="utf-8")

print("Original length:", len(content))

# 1. Replace the entire imports and SDK client initialization block
# We search from "try:\\n    from groq import Groq" to "ROOT = Path(__file__).parent.parent"
start_imports_pattern = r"try:\s+from groq import Groq as _Groq"
m_start = re.search(start_imports_pattern, content)
if not m_start:
    raise ValueError("Start of imports block not found!")

end_imports_pattern = r"ROOT = Path\(__file__\)\.parent\.parent"
m_end = re.search(end_imports_pattern, content)
if not m_end:
    raise ValueError("End of imports block not found!")

new_imports_text = """from scripts.utils.llm_client import run_fast_common, run_claude_common, _gemini_client, _groq_client
from scripts.utils.validators import (
    validate_entity_names, validate_numbers, detect_semantic_duplicates,
    assess_content_value, verify_article_logic, rewrite_for_coherence,
    finer_gate, _source_tier, _TIER_LABEL, strengthen_weak_sections,
    improve_readability_seo, reduce_excessive_headings
)
from scripts.utils.search_helper import (
    web_search_fresh, web_search_deep, format_search_for_llm, format_raw_sources
)
from scripts.agent_prompts import AGENT_PROMPTS

"""

content = content[:m_start.start()] + new_imports_text + content[m_end.start():]
print("1. Imports replaced. New length:", len(content))

# 2. Replace md_to_html function
md_to_html_start = content.find("def md_to_html(")
if md_to_html_start == -1:
    raise ValueError("def md_to_html not found!")

# Find the next header "# ── Web search" to find the end of md_to_html
web_search_start = content.find("# ── Web search")
if web_search_start == -1:
    raise ValueError("# ── Web search not found!")

new_md_to_html = """def md_to_html(md_path: Path, html_path: Path, title: str) -> Path:
    \"\"\"Конвертирует Markdown-статью в автономный HTML с дизайном проекта.\"\"\"
    import markdown as _md
    import re
    md_text = md_path.read_text(encoding="utf-8")

    # Убираем ТОЛЬКО внешний wrapper ```markdown ... ``` если LLM завернул статью в него
    outer = re.match(r"^```markdown\\s*\\n([\\s\\S]*)\\n```\\s*$", md_text.strip())
    if outer:
        md_text = outer.group(1)

    # Отделяем JSON-LD блок — два формата: raw <script> или ```json code block
    jsonld_block = ""
    # Формат 1: <script type="application/ld+json">...</script> прямо в тексте
    m = re.search(r'<script type="application/ld\\+json">([\\s\\S]*?)</script>', md_text)
    if m:
        jsonld_block = f'<script type="application/ld+json">{m.group(1)}</script>'
        md_text = md_text[:m.start()] + md_text[m.end():]
    elif "```json" in md_text and "@context" in md_text:
        # Формат 2: ```json { ... } ```
        m2 = re.search(r"```json\\s*(\\{[\\s\\S]*?\\})\\s*```", md_text)
        if m2:
            jsonld_block = f'<script type="application/ld+json">{m2.group(1)}</script>'
            md_text = md_text[:m2.start()] + md_text[m2.end():]

    # Убираем служебные секции SEO-оптимизатора — они не часть статьи
    _seo_sections = [
        r'## Целевые ключевые слова',
        r'## Оптимизированный текст',
        r'## AEO-аудит',
        r'## Schema\\.org JSON-LD',
        r'## JSON-LD',
    ]
    for _pat in _seo_sections:
        md_text = re.sub(
            rf'\\n{_pat}[^\\n]*\\n[\\s\\S]*?(?=\\n## |\\Z)',
            '',
            md_text,
        )
    # Убираем blockquote с инструкциями про плейсхолдеры JSON-LD
    md_text = re.sub(r'\\n> \\*\\*Замените плейсхолдеры\\*\\*[^\\n]*\\n?', '', md_text)
    md_text = re.sub(r'\\*\\*Замените плейсхолдеры\\*\\*[^\\n]*\\n?', '', md_text)
    # Убираем горизонтальные разделители перед служебными секциями которые остались
    md_text = re.sub(r'\\n---\\s*\\n\\s*$', '', md_text)
    # Убираем дублирующиеся горизонтальные разделители (--- подряд несколько раз)
    md_text = re.sub(r'(\\n---\\s*){2,}', '\\n---\\n', md_text)

    # Удаляем маркеры [INSUFFICIENT_SOURCES: ...] — могут содержать вложенные [...] внутри
    # Используем жадный поиск до последней ] на строке (не захватываем через границы абзаца)
    def _remove_insufficient(text: str) -> str:
        result = []
        i = 0
        while i < len(text):
            if text[i:].startswith('[INSUFFICIENT_SOURCES:'):
                depth = 0
                j = i
                while j < len(text):
                    if text[j] == '[':
                        depth += 1
                    elif text[j] == ']':
                        depth -= 1
                        if depth == 0:
                            j += 1
                            break
                    j += 1
                # Пропускаем пробелы и переводы строк после закрывающей скобки
                while j < len(text) and text[j] in (' ', '\\t', '\\n'):
                    j += 1
                i = j
            else:
                result.append(text[i])
                i += 1
        return ''.join(result)

    # Перед удалением маркеров убираем заголовки H2-H4, если после них сразу идет маркер нехватки
    md_text = re.sub(r'\\n#{2,4}[^\\n]+\\n+(?=\\[INSUFFICIENT_SOURCES:)', '\\n', md_text)
    md_text = _remove_insufficient(md_text)
    md_text = re.sub(r'\\*\\*\\*Примечание по JSON-LD:\\*\\*[^\\n]*\\n?', '', md_text)
    # Гарантируем, что статья начинается с первого H1 заголовка, убирая все метаданные до него
    h1_match = re.search(r'^# ', md_text, re.MULTILINE)
    if h1_match:
        md_text = md_text[h1_match.start():]
    # Зачищаем пустые H2-H4 заголовки в конце или в тексте
    md_text = re.sub(r'\\n(#{2,4}[^\\n]+)\\n+(?=#{1,4}|\\Z)', '\\n', md_text)
    # Для корректного рендеринга таблиц markdown добавляем пустую строку перед таблицей
    md_text = re.sub(r'(?m)^([^|\\n#][^\\n]*)\\n(\\|)', r'\\1\\n\\n\\2', md_text)

    # Очищаем заголовки-маркеры структуры из текста (Лид, Вывод)
    md_text = re.sub(r'^\\*\\*Лид\\*\\*\\s*\\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^\\*\\*Вывод\\*\\*\\s*\\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^#+\\s+\\*?\\*?Лид\\*?\\*?\\s*\\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^#+\\s+\\*?\\*?Вывод\\*?\\*?\\s*\\n?', '', md_text, flags=re.MULTILINE)
    md_text = re.sub(r'^#+\\s+[^\\n]*Schema\\.org[^\\n]*\\n?', '', md_text, flags=re.MULTILINE | re.IGNORECASE)
    md_text = re.sub(r'\\*?\\*?Примечания:\\*?\\*?.*$', '', md_text, flags=re.DOTALL)
    # Убираем случайные теги script
    md_text = re.sub(r'<script[^>]*>|</script>', '', md_text)
    md_text = re.sub(r'```json\\s*```', '', md_text, flags=re.DOTALL)

    # Убираем жирное форматирование из текста (заменяем **text** на text)
    md_text = re.sub(r'\\*\\*(.*?)\\*\\*', r'\\1', md_text)

    body_html = _md.markdown(
        md_text,
        extensions=["tables", "fenced_code", "toc"],
    )
    body_html = _make_code_collapsible(body_html)

    template_path = Path(__file__).parent / "templates" / "article_template.html"
    if template_path.exists():
        template = template_path.read_text(encoding="utf-8")
    else:
        template = "<html><head><title>{title}</title>{jsonld_block}</head><body>{body_html}</body></html>"

    html = template.format(
        title=title,
        jsonld_block=jsonld_block,
        body_html=body_html
    )

    html_path.write_text(html, encoding="utf-8")
    return html_path

"""

content = content[:md_to_html_start] + new_md_to_html + content[web_search_start:]
print("2. md_to_html replaced. New length:", len(content))

# 3. Remove all duplicate search and validation helper functions
# This is from "# ── Web search" to "def run_claude("
web_search_start = content.find("# ── Web search")
if web_search_start == -1:
    raise ValueError("# ── Web search not found after md_to_html replacement!")

run_claude_start = content.find("def run_claude(")
if run_claude_start == -1:
    raise ValueError("def run_claude not found!")

# Replace everything from "# ── Web search" up to "def run_claude" with empty string
content = content[:web_search_start] + content[run_claude_start:]
print("3. Duplicate search and validation helpers removed. New length:", len(content))

# 4. Replace run_fast and run_claude definitions
run_claude_start = content.find("def run_claude(")
if run_claude_start == -1:
    raise ValueError("def run_claude not found!")

human_review_start = content.find("# ── Human-in-the-Loop")
if human_review_start == -1:
    raise ValueError("# ── Human-in-the-Loop not found!")

new_run_helpers = """class StepResult:
    def __init__(self, step: int, agent: str):
        self.step = step
        self.agent = agent
        self.start = time.time()
        self.output: str = ""
        self.success: bool = False
        self.tokens: int = 0

    def finish(self, output: str, success: bool = True, tokens: int = 0) -> None:
        self.output = output
        self.success = success
        self.tokens = tokens
        elapsed = round(time.time() - self.start, 1)
        icon = "✅" if success else "❌"
        tg_notify(
            f"{icon} <b>Шаг {self.step:02d}</b> — {self.agent}\\n"
            f"⏱ {elapsed}с | ~{tokens} токенов"
        )


def run_claude(prompt: str, context_files: list[Path] = None, inject_feedback: bool = False) -> tuple[str, int]:
    \"\"\"Вызывает LLM для выполнения задачи агента через общий llm_client.\"\"\"
    from scripts.utils.llm_client import run_claude_common
    context = ""
    if context_files:
        for f in context_files:
            if f.exists():
                context += f"\\n\\n### {f.name}\\n{f.read_text(encoding='utf-8')}"
    return run_claude_common(prompt, context, inject_feedback)


def run_fast(prompt: str, quality: str = "strong") -> tuple[str, int]:
    \"\"\"Быстрый вызов LLM для лёгких или вспомогательных задач через общий llm_client.\"\"\"
    from scripts.utils.llm_client import run_fast_common
    return run_fast_common(prompt, quality)


"""

content = content[:run_claude_start] + new_run_helpers + content[human_review_start:]
print("4. LLM helpers replaced. New length:", len(content))

# 5. Remove AGENT_PROMPTS dictionary and _source_tier / _TIER_LABEL
# They start after human_review is defined.
# Let's find "AGENT_PROMPTS = {" and "def save_state("
agent_prompts_start = content.find("AGENT_PROMPTS = {")
if agent_prompts_start == -1:
    raise ValueError("AGENT_PROMPTS = { not found!")

save_state_start = content.find("def save_state(")
if save_state_start == -1:
    raise ValueError("def save_state not found!")

content = content[:agent_prompts_start] + content[save_state_start:]
print("5. AGENT_PROMPTS dictionary and tier helpers removed. New length:", len(content))

# Save the refactored content
orchestrator_path.write_text(content, encoding="utf-8")
print("Successfully wrote refactored scripts/orchestrator.py")
