from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from course_cutover import CourseMove, app, choose_target

NOW = datetime(2030, 4, 1, tzinfo=timezone.utc)


def request_data(**changes):
    values = dict(operation_id="course-42-cutover", domain="school.example", name="learn",
                  previous_target="old.school.example", delivery_target="new.school.example",
                  course="Algebra", learner_deadline=NOW + timedelta(days=1),
                  educator_report_ready=True, delivery_checked=True, action="cutover",
                  previous_ttl=3600, prepared_at=NOW - timedelta(hours=2))
    return CourseMove(**(values | changes))


def test_deadline_blocks_cutover_but_preserves_rollback():
    move = request_data(learner_deadline=NOW + timedelta(minutes=15))
    with pytest.raises(HTTPException) as rejected:
        choose_target(move, NOW)
    assert rejected.value.status_code == 409
    assert choose_target(move.model_copy(update={"action": "rollback"}), NOW) == move.previous_target
    assert choose_target(request_data(), NOW) == "new.school.example"


def test_wait_and_reporting_are_real_gates():
    for changes in ({"prepared_at": NOW}, {"educator_report_ready": False}, {"delivery_checked": False}):
        with pytest.raises(HTTPException):
            choose_target(request_data(**changes), NOW)


def test_service_resolves_zone_before_rollback_write(monkeypatch):
    monkeypatch.setenv("INFRAI_API_KEY", "test-credential")
    calls = []
    def send(**kwargs):
        calls.append(kwargs)
        if kwargs["method"] == "GET":
            data = {"zone_id": "zone-42"}
        else:
            assert kwargs["json"]["zone_id"] == "zone-42"
            data = {"record_id": "record-42"}
        return httpx.Response(200, json={"ok": True, "data": data},
                              request=httpx.Request(kwargs["method"], kwargs["url"]))
    monkeypatch.setattr(httpx, "request", send)
    move = request_data(action="rollback")
    response = TestClient(app).post("/course-cutover", json=move.model_dump(mode="json"))
    assert response.status_code == 200
    assert response.json()["target"] == move.previous_target
    assert [call["method"] for call in calls] == ["GET", "PUT"]
    assert calls[1]["headers"]["Idempotency-Key"] == move.operation_id
