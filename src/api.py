"""Phase 3: tiny HTTP API so the agent can be deployed on Cloud Run."""
from fastapi import FastAPI
from pydantic import BaseModel
from src.agent.graph import run

app = FastAPI(title="exec-profile-agent")


class Req(BaseModel):
    name: str
    title: str
    company: str


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/profile")
def profile(r: Req):
    return run(r.name, r.title, r.company).model_dump()
