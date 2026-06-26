from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import settings
from .schemas import ChatRequest, ChatResponse, Source
from .prompts import prompts
from .guards import is_in_scope, gemini_generate_text
from .rag import RAGStore, make_engine
from .memory import ChatMemory


rag_store: RAGStore | None = None
chat_memory: ChatMemory | None = None

MAX_HISTORY_TURNS = 4


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_store, chat_memory
    engine = make_engine()
    rag_store = RAGStore(engine)
    rag_store.ensure_schema()
    chat_memory = ChatMemory(engine)
    chat_memory.ensure_schema()
    yield


app = FastAPI(title="Nanu AI Web API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://petjio.in",
        "https://www.petjio.in",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _format_history(turns) -> str:
    if not turns:
        return ""
    return "\n".join(f"{t.role.upper()}: {t.content}" for t in turns)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    user_message = req.message.strip()

    session_id = chat_memory.get_or_create_session(req.session_id)
    history_turns = chat_memory.get_recent_turns(session_id, max_turns=MAX_HISTORY_TURNS)
    history_text = _format_history(history_turns)

    allowed, _reason = is_in_scope(user_message, history_text)
    if not allowed:
        answer = prompts.refusal(settings.PETJIO_ANDROID_APP_URL)
        chat_memory.add_message(session_id, "user", user_message)
        chat_memory.add_message(session_id, "assistant", answer)
        return ChatResponse(answer=answer, refused=True, sources=[], session_id=session_id)

    retrieved = rag_store.query(user_message, top_k=settings.RAG_TOP_K)

    context_blocks = []
    sources = []
    seen_source_urls = set()
    for ch in retrieved:
        context_blocks.append(f"URL: {ch.url}\nTITLE: {ch.title or ''}\nCONTENT:\n{ch.content}")
        if ch.url not in seen_source_urls:
            sources.append(Source(url=ch.url, title=ch.title))
            seen_source_urls.add(ch.url)

    context = "\n\n---\n\n".join(context_blocks)

    system = prompts.system(settings.PETJIO_ANDROID_APP_URL)
    user = f"""
Conversation so far (may be empty - use it to resolve pronouns/follow-ups, but
prioritize the latest question):
{history_text}

User question:
{user_message}

Petjio context (may be empty):
{context}

Instruction:
- Answer formally and concisely.
- If the user asks to book or do an action, provide the app link instead.
- Include a short "Sources" section listing only the relevant URLs from the context you used.
""".strip()

    answer = gemini_generate_text(system=system, user=user)

    chat_memory.add_message(session_id, "user", user_message)
    chat_memory.add_message(session_id, "assistant", answer)

    return ChatResponse(answer=answer, refused=False, sources=sources, session_id=session_id)