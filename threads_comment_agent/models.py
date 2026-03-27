"""
Модуль для работы с локальными моделями (Ollama, GPT4All)
"""
import requests
import json
from typing import Optional

class LocalLLM:
    """Интерфейс для локальных LLM"""

    def __init__(self, config: dict):
        self.config = config
        self.model_type = config.get("model", "ollama")

    def generate_comment(self, post_content: str, tone: str = "friendly") -> str:
        """Генерирует комментарий к посту"""

        if self.model_type == "ollama":
            return self._generate_ollama(post_content, tone)
        elif self.model_type == "gpt4all":
            return self._generate_gpt4all(post_content, tone)
        else:
            raise ValueError(f"Unsupported model type: {self.model_type}")

    def _generate_ollama(self, post_content: str, tone: str) -> str:
        """Генерирует через Ollama"""
        try:
            url = self.config.get("ollama_url", "http://localhost:11434")
            model = self.config.get("ollama_model", "mistral")

            prompt = f"""Напиши краткий комментарий ({self.config.get('max_length', 280)} символов макс) на русском языке.
Тон: {tone}
Контекст поста: {post_content}
Требования:
- Не начинай с эмодзи
- Будь кратким и по-дружески
- Не спрашивай вопросов
- Ответь только текстом комментария, без пояснений"""

            response = requests.post(
                f"{url}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False
                }
            )

            if response.status_code == 200:
                result = response.json().get("response", "").strip()
                return result[:self.config.get("max_length", 280)]
            else:
                print(f"Ollama error: {response.status_code}")
                return None

        except Exception as e:
            print(f"Ollama connection error: {e}")
            return None

    def _generate_gpt4all(self, post_content: str, tone: str) -> str:
        """Генерирует через GPT4All"""
        try:
            from gpt4all import GPT4All

            model_name = self.config.get("gpt4all_model", "orca-mini")
            model = GPT4All(model_name)

            prompt = f"""Напиши краткий комментарий ({self.config.get('max_length', 280)} символов макс) на русском языке.
Тон: {tone}
Контекст поста: {post_content}
Требования:
- Не начинай с эмодзи
- Будь кратким и по-дружески
- Не спрашивай вопросов"""

            response = model.generate(prompt, max_tokens=100)
            return response[:self.config.get("max_length", 280)]

        except Exception as e:
            print(f"GPT4All error: {e}")
            return None

    def generate_with_template(self, post_content: str, templates: list, tone: str = "friendly") -> str:
        """Генерирует комментарий на основе шаблонов"""
        import random

        # Сначала генерируем основной текст
        comment_text = self.generate_comment(post_content, tone)

        if not comment_text:
            return None

        # Выбираем случайный шаблон и вставляем текст
        template = random.choice(templates)
        result = template.format(comment=comment_text)

        return result[:self.config.get("max_length", 280)]
