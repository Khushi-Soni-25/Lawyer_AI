from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from backend.app.core.config import Settings
from backend.app.utils.request_context import get_logger


logger = get_logger("lawyer_ai.gemini")


class GeminiService:
    """Generate structured legal answers through the Gemini API."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = genai.Client(
            api_key=settings.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=int(settings.gemini_timeout_seconds * 1000),
                client_args={"trust_env": False},
            ),
        )
        self.system_prompt = self._load_system_prompt(settings.prompt_path)

    @staticmethod
    def _load_system_prompt(path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def generate_json(self, user_prompt: str, conversation: list[dict[str, str]]) -> dict[str, Any]:
        if not self.settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        contents = [
            {
                "role": "model" if message.get("role") == "assistant" else "user",
                "parts": [{"text": message.get("content", "")}],
            }
            for message in conversation
            if message.get("content")
        ]
        contents.append({"role": "user", "parts": [{"text": user_prompt}]})
        prompt_chars = len(user_prompt)
        conversation_chars = sum(len(message.get("content", "")) for message in conversation)
        logger.info(
            "gemini request start model=%s attempts=%s prompt_chars=%s conversation_messages=%s conversation_chars=%s",
            self.settings.gemini_model,
            self.settings.gemini_max_retries + 1,
            prompt_chars,
            len(conversation),
            conversation_chars,
        )

        last_error: Exception | None = None
        for attempt in range(self.settings.gemini_max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.settings.gemini_model,
                    contents=contents,
                    config={
                        "system_instruction": self.system_prompt,
                        "response_mime_type": "application/json",
                    },
                )
                text = str(getattr(response, "text", "") or "").strip()
                logger.info("gemini response received attempt=%s output_chars=%s", attempt + 1, len(text))
                payload = self._parse_json(text)
                if not str(payload.get("answer") or "").strip():
                    raise RuntimeError("Gemini response did not contain a usable answer.")
                return payload
            except Exception as exc:
                last_error = exc
                if not self._is_retryable_error(exc) or attempt >= self.settings.gemini_max_retries:
                    logger.error("gemini generation failed attempt=%s error=%s", attempt + 1, exc)
                    raise RuntimeError(f"Gemini request failed: {exc}") from exc
                logger.warning("transient Gemini error attempt=%s error=%s", attempt + 1, exc)
                time.sleep(min(2**attempt, 4))

        raise RuntimeError(f"Gemini request failed after retries: {last_error}")

    @staticmethod
    def _parse_json(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if not cleaned:
            return {}
        if cleaned.startswith("```"):
            cleaned = cleaned.removeprefix("```json").removeprefix("```JSON").removeprefix("```")
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()
        candidates = [cleaned]
        extracted = GeminiService._extract_json_object_text(cleaned)
        if extracted and extracted not in candidates:
            candidates.append(extracted)
        for candidate in candidates:
            try:
                payload = json.loads(candidate)
                if isinstance(payload, dict):
                    return payload
            except json.JSONDecodeError:
                continue
        return {"answer": cleaned}

    @staticmethod
    def _extract_json_object_text(text: str) -> str | None:
        start = text.find("{")
        end = text.rfind("}")
        return text[start : end + 1] if start != -1 and end > start else None

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return any(marker in text for marker in ("429", "rate limit", "resource exhausted", "timeout", "temporar", "503", "unavailable"))
