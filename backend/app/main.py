from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import settings
from .schemas import ChatRequest, ChatResponse, Source
from .prompts import prompts
from .guards import is_in_scope, gemini_generate_text
from .rag import RAGStore, make_engine


rag_store: RAGStore | None = None


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

    allowed, _reason = is_in_scope(user_message)
    if not allowed:
        return ChatResponse(
            answer=prompts.refusal(settings.PETJIO_ANDROID_APP_URL),
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

PetJio context (may be empty):
{context}

Instruction:
- Answer formally and concisely.
- If the user asks to book or do an action, provide the app link instead.
- Include a short "Sources" section listing only the relevant URLs from the context you used.
""".strip()

    answer = gemini_generate_text(system=system, user=user)

    # Return retrieved sources; the model will also include "Sources" text.
    # Later we can filter to only URLs actually cited.
    return ChatResponse(answer=answer, refused=False, sources=sources)