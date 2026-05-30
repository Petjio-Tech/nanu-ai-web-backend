import json
import requests
from .settings import settings
from .prompts import prompts

GEMINI_MODEL = "gemini-2.5-flash"

def gemini_generate_text(system: str, user: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={settings.GEMINI_API_KEY}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"SYSTEM:\n{system}\n\nUSER:\n{user}"}]}
        ],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 800},
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


def is_in_scope(user_message: str) -> tuple[bool, str]:
    system = prompts.classifier()
    out = gemini_generate_text(system=system, user=user_message)
    try:
        obj = json.loads(out)
        allowed = bool(obj.get("allowed"))
        reason = str(obj.get("reason", ""))
        return allowed, reason
    except Exception:
        # Fail-safe: if classifier fails, be conservative and refuse
        return False, "Unable to classify the query reliably."