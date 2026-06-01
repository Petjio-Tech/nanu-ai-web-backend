from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import settings
from .schemas import ChatRequest, ChatResponse, Source
from .prompts import prompts
from .guards import (
    gemini_generate_text,
    is_allowed_profile_memory,
    is_in_scope,
    is_memory_request,
    should_persist_message,
)
from .rag import RAGStore, make_engine


rag_store: RAGStore | None = None
SESSION_EXPIRY_HOURS = 24
SESSION_CONTEXT_TURNS = 10
SESSION_EXPIRED_MESSAGE = "Your session has been expired. Please consider refreshing the window for a new session"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup, load the model
    global rag_store
    engine = make_engine()
    rag_store = RAGStore(engine)
    rag_store.ensure_schema()
    yield
    # On shutdown, you could add cleanup code here if needed


app = FastAPI(title="Nanu AI Web API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    user_message = req.message.strip()
    session_id = str(req.session_id)

    if rag_store.is_session_expired(session_id, ttl_hours=SESSION_EXPIRY_HOURS):
        return ChatResponse(
            answer=SESSION_EXPIRED_MESSAGE,
            refused=True,
            sources=[],
        )

    history = rag_store.get_recent_messages(session_id, limit=SESSION_CONTEXT_TURNS * 2)
    history_text = "\n".join(f"{role.capitalize()}: {content}" for role, content in history) if history else "None"

    memory_requested = is_memory_request(user_message)
    allowed_profile_memory = is_allowed_profile_memory(user_message)
    if memory_requested and not allowed_profile_memory:
        return ChatResponse(
            answer=prompts.memory_guidance(),
            refused=True,
            sources=[],
        )

    allowed, _reason, category = is_in_scope(user_message)
    if not allowed:
        refusal = prompts.refusal(settings.PETJIO_ANDROID_APP_URL)
        return ChatResponse(
            answer=refusal,
            refused=True,
            sources=[],
        )

    # The RAG store is now guaranteed to be initialized
    retrieved = rag_store.query(user_message, top_k=settings.RAG_TOP_K)

    context_blocks = []
    sources = []
    for ch in retrieved:
        context_blocks.append(f"URL: {ch.url}\nTITLE: {ch.title or ''}\nCONTENT:\n{ch.content}")
        sources.append(Source(url=ch.url, title=ch.title))

    context = "\n\n---\n\n".join(context_blocks)

    system = prompts.system(settings.PETJIO_ANDROID_APP_URL)
    user = f"""
User question:
{user_message}

Conversation history (latest 10 turns):
{history_text}

PetJio context (may be empty):
{context}

Instruction:
- Answer formally and concisely.
- If the user asks to book or do an action, provide the app link instead.
- Include a short "Sources" section listing only the relevant URLs from the context you used.
""".strip()

    answer = gemini_generate_text(system=system, user=user)
    if should_persist_message(user_message, allowed=allowed, category=category):
        rag_store.add_message(session_id, "user", user_message)
        rag_store.add_message(session_id, "assistant", answer)

    # Return retrieved sources; the model will also include "Sources" text.
    # Later we can filter to only URLs actually cited.
    return ChatResponse(answer=answer, refused=False, sources=sources)