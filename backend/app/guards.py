import json
import requests
from .settings import settings
from .prompts import prompts
import re

GEMINI_MODEL = "gemini-2.5-flash"
MEMORY_REQUEST_PATTERN = re.compile(r"\b(remember|save|store|note)\b", re.IGNORECASE)
PROFILE_MEMORY_PATTERNS = [
    re.compile(r"\b(my|preferred)\s+name\s+is\s+\w+", re.IGNORECASE),
    re.compile(r"\bcall\s+me\s+\w+", re.IGNORECASE),
    re.compile(r"\bmy\s+(dog|cat|pet)['’]s\s+name\s+is\b", re.IGNORECASE),
    re.compile(r"\bmy\s+(dog|cat|pet)\s+is\s+\d+\s*(year|years|yr|yrs|month|months)\b", re.IGNORECASE),
    re.compile(r"\b(my\s+)?(dog|cat|pet)\b.*\b(weight|kg|kilogram|lb|pound|breed|species|gender|male|female)\b", re.IGNORECASE),
    re.compile(r"\b(my\s+)?(dog|cat|pet)\b.*\b(vaccin|allerg|medical|condition|history)\w*\b", re.IGNORECASE),
    re.compile(r"\b(my\s+)?(dog|cat|pet)\b.*\b(scared|afraid|anxious|nervous|temperament|behavio[u]?r|reactive|aggressive|friendly|shy)\b", re.IGNORECASE),
    re.compile(r"\b(feeding|walk)\s+(time|times|schedule|preference|preferences)\b", re.IGNORECASE),
]

def gemini_generate_text(system: str, user: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"SYSTEM:\n{system}\n\nUSER:\n{user}"}]}
        ],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 512},
    }
    r = requests.post(url, json=payload, timeout=45)
    r.raise_for_status()
    data = r.json()
    return (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
        .strip()
    )


def _extract_classifier_json(output_text: str) -> dict:
    out = output_text.strip()
    if out.startswith("```"):
        out = re.sub(r"^```(?:json)?\s*", "", out, flags=re.IGNORECASE)
        out = re.sub(r"\s*```$", "", out)
    try:
        return json.loads(out)
    except Exception:
        match = re.search(r"\{.*\}", out, flags=re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def is_memory_request(user_message: str) -> bool:
    return bool(MEMORY_REQUEST_PATTERN.search(user_message))


def is_allowed_profile_memory(user_message: str) -> bool:
    return any(pattern.search(user_message) for pattern in PROFILE_MEMORY_PATTERNS)


def should_persist_message(user_message: str, allowed: bool, category: str) -> bool:
    if not allowed:
        return False
    if category in {"pet_care", "petjio"}:
        return True
    if category == "profile_setup":
        return is_allowed_profile_memory(user_message)
    return False


def is_in_scope(user_message: str) -> tuple[bool, str, str]:
    system = prompts.classifier()
    out = gemini_generate_text(system=system, user=user_message)

    try:
        obj = _extract_classifier_json(out)
        allowed = bool(obj.get("allowed"))
        reason = str(obj.get("reason", ""))
        category = str(obj.get("category", "out_of_scope"))
        if not allowed and is_allowed_profile_memory(user_message):
            return True, "Profile setup detected by guard fallback.", "profile_setup"
        return allowed, reason, category
    except Exception:
        if is_allowed_profile_memory(user_message):
            return True, "Profile setup detected by guard fallback.", "profile_setup"
        return False, "Unable to classify the query reliably.", "out_of_scope"