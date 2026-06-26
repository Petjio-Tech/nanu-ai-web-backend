import json
import re
import requests
from fastapi import HTTPException
from .settings import settings
from .prompts import prompts

GEMINI_MODEL = "gemini-2.5-flash"

ALLOW_KEYWORDS = {
    "petjio", "nanu", "naanu", "pet coin", "petcoin", "pet-coin",
    "sos", "petjio app", "petjio service",
    "pet", "dog", "cat", "puppy", "kitten", "pup", "canine", "feline",
    "bird", "parrot", "rabbit", "hamster", "fish", "turtle",
    "reptile", "guinea pig", "ferret", "animal",
    "groom", "board", "boarding", "train", "training", "walker", "walking",
    "sitter", "sitting", "transport", "vet", "veterinar", "breed", "breeder",
    "vaccine", "vaccination", "feed", "feeding", "food", "health", "care",
    "symptom", "sick", "ill", "disease", "diet", "nutrition", "medicine",
    "flea", "tick", "worm", "neuter", "spay", "deworm",
    "service", "community", "partner", "faq", "blog", "news",
    "policy", "refund", "terms", "privacy", "coin", "reward", "loyalty",
    "booking", "book", "appointment", "emergency", "help", "support",
}

DENY_KEYWORDS = {
    "capital of", "stock market", "cryptocurrency", "bitcoin", "ethereum",
    "politics", "election", "war", "coding", "python code", "javascript",
    "recipe", "cooking", "movie", "song", "music", "weather",
    "translate", "math problem", "equation",
}


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
                detail="Gemini authentication failed. Check GEMINI_API_KEY.",
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
    """
    Scope check using keyword matching only — no Gemini API call.
    Gemini's system prompt already enforces scope at answer-generation time,
    so this gate only needs to catch obviously off-topic messages.

    Logic:
    1. If message contains a deny keyword → refuse immediately
    2. If message contains an allow keyword → allow immediately
    3. If session history contains an allow keyword → allow (resolves follow-ups like "how do I earn it?")
    4. Anything else → allow and let the system prompt handle it
    """
    msg_lower = user_message.lower()

    # Step 1: hard deny
    for kw in DENY_KEYWORDS:
        if kw in msg_lower:
            return False, f"deny_keyword:{kw}"

    # Step 2: allow on message keyword
    for kw in ALLOW_KEYWORDS:
        if kw in msg_lower:
            return True, f"keyword:{kw}"

    # Step 3: allow on history keyword (follow-up messages)
    if history:
        history_lower = history.lower()
        for kw in ALLOW_KEYWORDS:
            if kw in history_lower:
                return True, f"history:{kw}"

    # Step 4: default allow — Gemini system prompt is the real scope enforcer
    return True, "default_allow"