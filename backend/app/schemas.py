from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: str | None = None


class Source(BaseModel):
    url: str
    title: str | None = None


class ChatResponse(BaseModel):
    answer: str
    refused: bool = False
    sources: list[Source] = []
    session_id: str
