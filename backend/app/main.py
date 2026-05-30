from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .settings import settings
from .schemas import ChatRequest, ChatResponse, Source
from .prompts import prompts
from .guards import is_in_scope, gemini_generate_text
from .rag import RAGStore, make_engine

app = FastAPI(title="Nanu AI Web API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = make_engine()
rag = RAGStore(engine)
rag.ensure_schema()


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

    retrieved = rag.query(user_message, top_k=settings.RAG_TOP_K)

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