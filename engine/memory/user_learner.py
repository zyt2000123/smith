from __future__ import annotations

import json
import re
from pathlib import Path

from ._files import atomic_write_text


# Confidence threshold: must see a pattern N times before writing it
_CONFIDENCE_THRESHOLD = 3

# Placeholder that marks a field as learnable
_PLACEHOLDER = "{{to_be_learned}}"

# --- Language detection ---

_ZH_RE = re.compile(r"[一-鿿]")
_JA_RE = re.compile(r"[぀-ゟ゠-ヿ]")


def _detect_language(text: str) -> str | None:
    """Return 'zh', 'ja', or 'en' based on character frequency."""
    zh_count = len(_ZH_RE.findall(text))
    ja_count = len(_JA_RE.findall(text))

    total = len(text)
    if total == 0:
        return None

    if ja_count > 5:
        return "ja"
    if zh_count / max(total, 1) > 0.1:
        return "zh"
    # Default to English if mostly ASCII
    ascii_count = sum(1 for c in text if ord(c) < 128)
    if ascii_count / max(total, 1) > 0.8:
        return "en"
    return None


# --- Verbosity detection ---

def _detect_verbosity(text: str) -> str | None:
    """Classify user message length as terse/normal/detailed."""
    word_count = len(text.split())
    if word_count <= 10:
        return "concise"
    if word_count >= 80:
        return "detailed"
    return None


# --- Technical level detection ---

_EXPERT_KEYWORDS = [
    "async", "await", "decorator", "metaclass", "coroutine",
    "mutex", "semaphore", "deadlock", "race condition",
    "O(n)", "O(log n)", "amortized",
    "SOLID", "DRY", "YAGNI", "DDD",
    "kubernetes", "k8s", "docker", "terraform",
    "microservice", "gRPC", "protobuf",
    "CI/CD", "pipeline", "rollback",
    "sharding", "replication", "WAL",
    "type hint", "generic", "protocol",
    "反射", "协程", "线程池", "事务",
]


def _detect_tech_level(text: str) -> str | None:
    """Return 'expert' if technical jargon density is high."""
    lower = text.lower()
    hits = sum(1 for kw in _EXPERT_KEYWORDS if kw.lower() in lower)
    if hits >= 2:
        return "expert"
    return None


# --- Code style detection ---

_CODE_STYLE_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\btype hint", re.IGNORECASE), "type hints"),
    (re.compile(r"\b类型注解", re.IGNORECASE), "type hints"),
    (re.compile(r"\bfunctional\b", re.IGNORECASE), "functional style"),
    (re.compile(r"\b函数式\b", re.IGNORECASE), "functional style"),
    (re.compile(r"\bOOP\b"), "OOP"),
    (re.compile(r"\b面向对象\b"), "OOP"),
    (re.compile(r"\bdataclass", re.IGNORECASE), "dataclasses"),
    (re.compile(r"\bpydantic\b", re.IGNORECASE), "pydantic"),
    (re.compile(r"\basync\b", re.IGNORECASE), "async-first"),
]


def _detect_code_style(text: str) -> str | None:
    """Return a code style hint if the user mentions one."""
    for pattern, label in _CODE_STYLE_PATTERNS:
        if pattern.search(text):
            return label
    return None


# --- Field mapping ---
# Maps learner keys to context.md field labels.
# Only interaction preferences — project/identity info belongs in durable.md.
_FIELD_MAP = {
    "language": "Preferred Language",
    "verbosity": "Communication Style",
    "tech_level": "Technical Level",
    "code_style": "Code Style",
}


class UserPreferenceLearner:
    """Observe conversation patterns and auto-fill context.md preferences.

    Uses simple heuristics (regex/keyword detection), not LLM calls.
    Tracks a confidence counter in .learner_state.json — only writes
    a preference to context.md after seeing it ``_CONFIDENCE_THRESHOLD`` times.
    """

    def __init__(self, agent_dir: Path) -> None:
        self._context_path = agent_dir / "context.md"
        self._state_path = agent_dir / ".learner_state.json"

    # --- public API ---

    async def observe(self, user_message: str, _agent_reply: str) -> list[str]:
        """Analyze a conversation turn and extract learnable preferences.

        Returns list of observations made (for logging).
        """
        observations: list[str] = []
        state = self._load_state()

        # Detect patterns from user message
        detectors: list[tuple[str, str | None]] = [
            ("language", _detect_language(user_message)),
            ("verbosity", _detect_verbosity(user_message)),
            ("tech_level", _detect_tech_level(user_message)),
            ("code_style", _detect_code_style(user_message)),
        ]

        for key, value in detectors:
            if value is None:
                continue

            counters = state.setdefault("counters", {})
            key_counters = counters.setdefault(key, {})
            key_counters[value] = key_counters.get(value, 0) + 1

            if key_counters[value] == _CONFIDENCE_THRESHOLD:
                # Reached confidence — write to context.md
                written = self._write_preference(key, value)
                if written:
                    observations.append(f"{key}={value}")
                    state.setdefault("written", {})[key] = value

        self._save_state(state)
        return observations

    # --- state persistence ---

    def _load_state(self) -> dict:
        if self._state_path.is_file():
            try:
                return json.loads(self._state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_state(self, state: dict) -> None:
        atomic_write_text(
            self._state_path,
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
        )

    # --- context.md writing ---

    def _write_preference(self, key: str, value: str) -> bool:
        """Write a learned preference into context.md.

        Only replaces ``{{to_be_learned}}`` placeholders or appends to
        the Preferences section. Never deletes user-written content.

        Returns True if something was actually written.
        """
        if not self._context_path.is_file():
            return False

        content = self._context_path.read_text(encoding="utf-8")

        # Determine which field label to target
        field_label = _FIELD_MAP.get(key)
        if field_label is None:
            return False

        # Try to replace the placeholder on the matching line
        marker = f"- {field_label}: {_PLACEHOLDER}"
        if marker in content:
            content = content.replace(marker, f"- {field_label}: {value}", 1)
            atomic_write_text(self._context_path, content)
            return True

        # If the field already has a value (not placeholder), check if we
        # should append (for code_style accumulation) or skip
        field_line_re = re.compile(
            rf"^- {re.escape(field_label)}: (.+)$", re.MULTILINE,
        )
        match = field_line_re.search(content)
        if match:
            existing = match.group(1).strip()
            if existing == _PLACEHOLDER:
                # Shouldn't happen (caught above), but handle anyway
                new_line = f"- {field_label}: {value}"
                content = content.replace(match.group(0), new_line, 1)
                atomic_write_text(self._context_path, content)
                return True
            # Already has a real value — don't overwrite user content
            return False

        # Field not found at all — append to Preferences section if it exists
        if "# Interaction Preferences" in content or "# Preferences" in content or "# 偏好" in content:
            content = content.rstrip() + f"\n- {field_label}: {value}\n"
            atomic_write_text(self._context_path, content)
            return True

        return False
