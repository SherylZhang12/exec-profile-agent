"""HTTP API for Cloud Run.  POST /profile  {"name","title","company","mode"?}"""
from typing import Literal
from fastapi import FastAPI
from pydantic import BaseModel
from src.agent.graph import run

app = FastAPI(title="exec-profile-agent")


class Req(BaseModel):
    name: str
    title: str
    company: str
    mode: Literal["rag", "baseline"] = "rag"


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/profile")
def profile(r: Req):
    return run(r.name, r.title, r.company, mode=r.mode).model_dump()
