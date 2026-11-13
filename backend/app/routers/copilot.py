from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..db import get_db
from ..services.copilot import chat

router = APIRouter(prefix="/api/copilot", tags=["copilot"])


class Msg(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[Msg]


@router.post("/chat")
def copilot_chat(req: ChatRequest, db: Session = Depends(get_db)):
    return chat(db, [m.model_dump() for m in req.messages][-20:])
