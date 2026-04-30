from __future__ import annotations

import json
import os
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from core.shared import PROJECT_ROOT, seed_project_envs


@dataclass(slots=True)
class OllamaClientError(RuntimeError):
    classification: str
    message: str

    def __str__(self) -> str:
        return self.message


class OllamaClient:
    def __init__(self, endpoint: str, model: str, timeout_seconds: float) -> None:
        if not endpoint:
            raise OllamaClientError("config_error", "OLLAMA_ENDPOINT is required for the intent parser")
        if not model:
            raise OllamaClientError("config_error", "OLLAMA_MODEL is required for the intent parser")
        if timeout_seconds <= 0:
            raise OllamaClientError("config_error", "OLLAMA_INTENT_TIMEOUT must be greater than zero")
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls, project_root: Path | None = None) -> "OllamaClient":
        root = project_root or PROJECT_ROOT
        seed_project_envs(root)
        endpoint = os.environ.get("OLLAMA_ENDPOINT", "").strip()
        model = os.environ.get("OLLAMA_MODEL", "").strip()
        timeout_raw = os.environ.get("OLLAMA_INTENT_TIMEOUT", "15").strip()
        try:
            timeout_seconds = float(timeout_raw)
        except ValueError as exc:
            raise OllamaClientError(
                "config_error",
                f"OLLAMA_INTENT_TIMEOUT must be numeric, got {timeout_raw!r}",
            ) from exc
        return cls(endpoint=endpoint, model=model, timeout_seconds=timeout_seconds)

    def generate(self, prompt: str, *, system_prompt: str) -> str:
        if not prompt.strip():
            raise OllamaClientError("code_error", "Intent parser prompt must not be empty")
        body = json.dumps(
            {
                "model": self.model,
                "prompt": prompt,
                "system": system_prompt,
                "stream": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.endpoint}/api/generate",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise OllamaClientError(
                "missing_runtime",
                f"Ollama request failed with HTTP {exc.code} at {self.endpoint}",
            ) from exc
        except urllib.error.URLError as exc:
            reason = exc.reason
            if isinstance(reason, socket.timeout):
                raise OllamaClientError(
                    "missing_runtime",
                    f"Ollama request timed out after {self.timeout_seconds:g}s",
                ) from exc
            raise OllamaClientError(
                "missing_runtime",
                f"Could not reach Ollama at {self.endpoint}: {reason}",
            ) from exc
        except TimeoutError as exc:
            raise OllamaClientError(
                "missing_runtime",
                f"Ollama request timed out after {self.timeout_seconds:g}s",
            ) from exc
        except json.JSONDecodeError as exc:
            raise OllamaClientError("code_error", "Ollama returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise OllamaClientError("code_error", "Ollama returned a non-object response")
        raw_response = payload.get("response")
        if not isinstance(raw_response, str) or not raw_response.strip():
            raise OllamaClientError("code_error", "Ollama response did not include response text")
        return raw_response
