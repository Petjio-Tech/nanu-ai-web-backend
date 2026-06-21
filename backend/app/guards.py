import json
import requests
from fastapi import HTTPException
from .settings import settings
from .prompts import prompts
import re

GEMINI_MODEL = "gemini-2.5-flash"

def gemini_generate_text(system: str, user: str) -> str:
    api_key = settings.GEMINI_API_KEY.strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not configured.")

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={api_key}"
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": f"SYSTEM:\n{system}\n\nUSER:\n{user}"}]}
        ],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
    }
    try:
        r = requests.post(url, json=payload, timeout=45)
        r.raise_for_status()
    except requests.HTTPError as exc:
        status_code = exc.response.status_code if exc.response is not None else 502
        response_text = (exc.response.text or "").strip() if exc.response is not None else ""
        if status_code == 401:
            raise HTTPException(
                status_code=502,
                detail="Gemini authentication failed. Check GEMINI_API_KEY and API access for this model.",
            ) from exc
        raise HTTPException(
            status_code=502,
            detail=response_text or "Gemini request failed.",
        ) from exc
    data = r.json()
    return (
        data.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text", "")
        .strip()
    )


def is_in_scope(user_message: str, history: str = "") -> tuple[bool, str]:
    system = prompts.classifier()
    user_payload = (
        f"Conversation so far:\n{history}\n\nLatest message to classify:\n{user_message}"
        if history
        else user_message
    )
    out = gemini_generate_text(system=system, user=user_payload)

    # ---- ADD THIS BLOCK ----
    out = out.strip()
    if out.startswith("```"):
        out = out.split("```", 2)[1]  # remove starting fence token
        out = out.replace("json", "", 1).strip()  # tolerate ```json
    if out.endswith("```"):
        out = out.rsplit("```", 1)[0].strip()
    # ------------------------

    try:
        obj = json.loads(out)
        allowed = bool(obj.get("allowed"))
        reason = str(obj.get("reason", ""))
        return allowed, reason
    except Exception:
        return False, "Unable to classify the query reliably."