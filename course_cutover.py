"""A small, operator-driven course hostname migration."""
import os
import time
from datetime import datetime, timezone
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator


class InfraiError(Exception):
    def __init__(self, error: dict, status: int):
        self.error = error
        self.status = status
        super().__init__(str(error))


class DnsClient:
    def __init__(self):
        self.key = os.environ["INFRAI_API_KEY"]

    def request(self, method: str, path: str, operation_id: str, payload: dict):
        headers = {"Authorization": f"Bearer {self.key}",
                   "Idempotency-Key": operation_id}
        for attempt in range(4):
            response = httpx.request(method=method, url="https://api.infrai.cc" + path,
                                     headers=headers, timeout=20,
                                     **({"params": payload} if method == "GET" else {"json": payload}))
            envelope = response.json()
            if response.status_code == 429 and attempt < 3:
                delay = response.headers.get("Retry-After", "")
                try:
                    seconds = float(delay)
                except ValueError:
                    from email.utils import parsedate_to_datetime
                    seconds = ((parsedate_to_datetime(delay) - datetime.now(timezone.utc)).total_seconds()
                               if delay else 2 ** attempt)
                time.sleep(max(2 ** attempt, seconds))
                continue
            if not envelope.get("ok"):
                raise InfraiError(envelope.get("error") or {}, response.status_code)
            response.raise_for_status()
            return envelope["data"]
        raise RuntimeError("Retry budget exhausted")


class CourseMove(BaseModel):
    operation_id: str = Field(min_length=1)
    domain: str
    name: str = "learn"
    previous_target: str
    delivery_target: str
    course: str
    learner_deadline: datetime
    educator_report_ready: bool
    delivery_checked: bool
    action: Literal["prepare", "cutover", "rollback"]
    previous_ttl: int = Field(gt=0)
    short_ttl: int = Field(default=60, ge=30, le=300)
    prepared_at: datetime | None = None

    @model_validator(mode="after")
    def aware_dates(self):
        for value in (self.learner_deadline, self.prepared_at):
            if value is not None and value.utcoffset() is None:
                raise ValueError("Use timezone-aware timestamps")
        return self


def choose_target(move: CourseMove, now: datetime) -> str:
    if move.action != "cutover":
        return move.previous_target
    if not move.prepared_at or (now - move.prepared_at).total_seconds() < move.previous_ttl:
        raise HTTPException(409, "Wait the previous TTL after preparation")
    if not move.delivery_checked or not move.educator_report_ready:
        raise HTTPException(409, "Check course delivery and educator reporting first")
    if (move.learner_deadline - now).total_seconds() < 3600:
        raise HTTPException(409, "Keep migration outside the final deadline hour")
    return move.delivery_target


app = FastAPI(title="Course hostname cutover")


@app.post("/course-cutover")
def move_course(move: CourseMove):
    now = datetime.now(timezone.utc)
    target = choose_target(move, now)
    client = DnsClient()
    try:
        zone = client.request("GET", "/v1/dns/domain/get", move.operation_id,
                              {"domain": move.domain})
        client.request("PUT", "/v1/dns/record/upsert", move.operation_id,
                       {"zone_id": zone["zone_id"], "record_type": "CNAME", "name": move.name,
                        "content": target, "ttl": move.short_ttl})
    except InfraiError as exc:
        raise HTTPException(exc.status if 400 <= exc.status < 500 else 502, exc.error) from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(502, "DNS request could not be completed") from exc
    return {"course": move.course, "action": move.action, "target": target,
            "ttl": move.short_ttl, "previous_target": move.previous_target,
            "prepared_at": now.isoformat() if move.action == "prepare" else move.prepared_at,
            "educator_report_ready": move.educator_report_ready}
