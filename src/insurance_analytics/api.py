"""Local demonstration API. Hosted deployments need an authenticated gateway."""

from functools import lru_cache

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

from .mortality import death_benefit_apv, prepare, summarize
from .reporting import premium_report
from .synthetic import applications, experience, premium_transactions
from .underwriting import train

app = FastAPI(
    title="Insurance Analytics",
    version="0.1.0",
    description="Synthetic research and human review demo.",
)


class Applicant(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    age: int = Field(ge=18, le=100)
    bmi: float = Field(gt=0, le=100)
    smoker: int = Field(ge=0, le=1)
    rx_count: int = Field(ge=0, le=100)
    a1c: float | None = Field(default=None, gt=0, le=30)
    channel: str = Field(min_length=1, max_length=80)


class ScoreBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    applicants: list[Applicant] = Field(min_length=1, max_length=1000)


class APVRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    qx: list[FiniteFloat] = Field(min_length=1, max_length=150)
    interest: float = Field(default=0.03, gt=-1)
    benefit: float = Field(default=1, ge=0)


@lru_cache(maxsize=1)
def demo_model():
    return train(applications())


@app.get("/health")
def health():
    return {"status": "ok", "data_source": "synthetic"}


@app.post("/v1/underwriting/score")
def score(batch: ScoreBatch):
    p = demo_model().predict(pd.DataFrame([a.model_dump() for a in batch.applicants]))
    return {
        "model": "synthetic-impairment-v1",
        "probabilities": p.tolist(),
        "purpose": "research_and_human_review",
    }


@app.get("/v1/mortality")
def mortality():
    return summarize(prepare(experience()), ["client"]).to_dict(orient="records")


@app.get("/v1/premiums")
def premiums():
    return premium_report(premium_transactions()).to_dict(orient="records")


@app.post("/v1/mortality/apv")
def apv(request: APVRequest):
    try:
        return {"apv": death_benefit_apv(request.qx, request.interest, request.benefit)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
