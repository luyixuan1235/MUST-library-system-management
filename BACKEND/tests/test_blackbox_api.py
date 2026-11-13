# -*- coding: utf-8 -*-
"""
Black-box Test Suite (BB-01 .. BB-12) for Library Seat Management System.

Designed against the REAL FastAPI + SQLAlchemy implementation:
- Equivalence Partitioning (EP)
- Boundary Value Analysis (BVA)
- Decision Table Testing ( Seat & Floor Colors, Report Upload )
- State Transition & Scenario Testing ( Report -> Confirm Toggle -> Lock -> Clear )
- Role-Based Access Control ( Student vs Admin vs Anonymous )
"""
from __future__ import annotations

import io
import os
import sys
import time
from pathlib import Path
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# Ensure BACKEND root is importable
BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.auth import get_password_hash
from backend.db import Base, get_db
from backend.main import create_app
from backend.models import Report, Seat, User
from backend.routes import auth as auth_routes


@pytest.fixture()
def test_ctx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated in-memory SQLite DB + FastAPI TestClient with seeded users & seats."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    # Reset active-user set between tests
    auth_routes._active_users.clear()

    # Seed default student, admin, and 4 F1 seats
    db = TestingSessionLocal()
    student = User(username="student01", pass_hash=get_password_hash("123456"), role="student")
    admin = User(username="admin01", pass_hash=get_password_hash("123456"), role="admin")
    db.add_all([student, admin])
    db.add_all(
        [
            Seat(seat_id="F1-01", floor_id="F1", has_power=False, is_empty=True),
            Seat(seat_id="F1-02", floor_id="F1", has_power=True, is_empty=True),
            Seat(seat_id="F1-03", floor_id="F1", has_power=False, is_empty=False),
            Seat(seat_id="F1-04", floor_id="F1", has_power=True, is_empty=False),
            Seat(seat_id="F2-01", floor_id="F2", has_power=False, is_empty=False),
            Seat(seat_id="F2-02", floor_id="F2", has_power=True, is_empty=False),
        ]
    )
    db.commit()
    db.refresh(student)
    db.refresh(admin)

    app = create_app()

    def override_get_db() -> Generator:
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        # Prevent background YOLO scheduler from touching real disk DB during black-box tests
        if hasattr(app.state, "scheduler") and app.state.scheduler:
            app.state.scheduler.start = lambda: setattr(app.state.scheduler, "started", True)
            app.state.scheduler.shutdown = lambda: setattr(app.state.scheduler, "started", False)
        yield client, TestingSessionLocal, student.id, admin.id

    db.close()


def _login_token(client: TestClient, username: str, password: str) -> str:
    res = client.post("/auth/login", data={"username": username, "password": password})
    assert res.status_code == 200, res.text
    return res.json()["access_token"]


# ---------------------------------------------------------------------------
# BB-01: Login Equivalence Partitioning & Session Lifecycle
# ---------------------------------------------------------------------------
def test_bb01_login_equivalence_classes(test_ctx):
    client, _, student_id, admin_id = test_ctx

    # Valid student credentials -> 200 + bearer token + role=student
    r_stu = client.post("/auth/login", data={"username": "student01", "password": "123456"})
    assert r_stu.status_code == 200
    body_stu = r_stu.json()
    assert body_stu["role"] == "student"
    assert body_stu["user_id"] == student_id
    assert body_stu["token_type"] == "bearer"
    assert body_stu["access_token"]

    # Valid admin credentials -> 200 + bearer token + role=admin
    r_adm = client.post("/auth/login", data={"username": "admin01", "password": "123456"})
    assert r_adm.status_code == 200
    assert r_adm.json()["role"] == "admin"
    assert r_adm.json()["user_id"] == admin_id

    # Invalid password -> 401 Unauthorized
    r_bad_pw = client.post("/auth/login", data={"username": "student01", "password": "wrong"})
    assert r_bad_pw.status_code == 401
    assert r_bad_pw.json()["detail"] == "Incorrect username or password"

    # Non-existent user -> 401 Unauthorized
    r_no_user = client.post("/auth/login", data={"username": "ghost", "password": "123456"})
    assert r_no_user.status_code == 401


# ---------------------------------------------------------------------------
# BB-02: Registration & Username Uniqueness
# ---------------------------------------------------------------------------
def test_bb02_register_and_duplicate_rejection(test_ctx):
    client, _, _, _ = test_ctx

    # 1st registration -> 200, default role='student'
    r1 = client.post("/auth/register", json={"username": "newstudent", "password": "123456"})
    assert r1.status_code == 200
    assert r1.json()["role"] == "student"
    assert r1.json()["username"] == "newstudent"

    # Duplicate registration -> 400 Bad Request ("Username already registered")
    r2 = client.post("/auth/register", json={"username": "newstudent", "password": "654321"})
    assert r2.status_code == 400
    assert r2.json()["detail"] == "Username already registered"


# ---------------------------------------------------------------------------
# BB-03: Query Seats by Floor & Single Seat Lookup
# ---------------------------------------------------------------------------
def test_bb03_list_seats_by_floor_and_single_seat(test_ctx):
    client, _, _, _ = test_ctx

    r_f1 = client.get("/seats", params={"floor": "F1"})
    assert r_f1.status_code == 200
    seats_f1 = r_f1.json()
    assert len(seats_f1) == 4
    assert all(s["floor_id"] == "F1" for s in seats_f1)

    r_f2 = client.get("/seats", params={"floor": "F2"})
    assert r_f2.status_code == 200
    seats_f2 = r_f2.json()
    assert len(seats_f2) == 2
    assert all(s["floor_id"] == "F2" for s in seats_f2)

    # Single seat: existing vs non-existing
    r_one = client.get("/seats/F1-02")
    assert r_one.status_code == 200
    assert r_one.json()["seat_id"] == "F1-02"
    assert r_one.json()["seat_color"] == "#00A1FF"  # empty + power -> Blue

    r_404 = client.get("/seats/F9-99")
    assert r_404.status_code == 404
    assert r_404.json()["detail"] == "seat not found"


# ---------------------------------------------------------------------------
# BB-04: Floor Color Boundary Value Analysis (>50%, 50%, 1%, 0%)
# ---------------------------------------------------------------------------
def test_bb04_floor_color_boundaries(test_ctx):
    client, SessionLocal, _, _ = test_ctx
    db = SessionLocal()

    # Clear existing seats and construct 4 floors with exact boundary ratios:
    # F_GREEN: 51/100 (51% > 50%) -> #60D937
    # F_FIFTY: 1/2    (50% <= 50%) -> #FEAE03
    # F_ONE:   1/100  (1% <= 50%)  -> #FEAE03
    # F_ZERO:  0/2    (0% == 0)    -> #FF0000
    db.query(Seat).delete()
    for i in range(100):
        db.add(Seat(seat_id=f"FG-{i:03d}", floor_id="FG", is_empty=(i < 51)))
        db.add(Seat(seat_id=f"FO-{i:03d}", floor_id="FO", is_empty=(i < 1)))
    db.add_all(
        [
            Seat(seat_id="FF-01", floor_id="FF", is_empty=True),
            Seat(seat_id="FF-02", floor_id="FF", is_empty=False),
            Seat(seat_id="FZ-01", floor_id="FZ", is_empty=False),
            Seat(seat_id="FZ-02", floor_id="FZ", is_empty=False),
        ]
    )
    db.commit()
    db.close()

    res = client.get("/floors")
    assert res.status_code == 200
    by_floor = {f["floor_id"]: f for f in res.json()}

    assert by_floor["FG"]["floor_color"] == "#60D937"  # 51% -> Green
    assert by_floor["FF"]["floor_color"] == "#FEAE03"  # 50% -> Yellow
    assert by_floor["FO"]["floor_color"] == "#FEAE03"  # 1%  -> Yellow
    assert by_floor["FZ"]["floor_color"] == "#FF0000"  # 0%  -> Red (resolves ambiguity #1)


# ---------------------------------------------------------------------------
# BB-05: Text Report Submission (Valid vs Non-existent Seat)
# ---------------------------------------------------------------------------
def test_bb05_submit_text_report(test_ctx):
    client, _, student_id, _ = test_ctx

    # Valid seat report without images
    r_ok = client.post(
        "/reports",
        data={"seat_id": "F1-03", "reporter_id": str(student_id), "text": "Bag left for hours"},
    )
    assert r_ok.status_code == 200
    report = r_ok.json()
    assert report["seat_id"] == "F1-03"
    assert report["status"] == "pending"
    assert report["images"] == []

    # Seat is now marked is_reported=True and seat_color turns Yellow (#FEAE03) in API
    s_after = client.get("/seats/F1-03").json()
    assert s_after["is_reported"] is True
    assert s_after["seat_color"] == "#FEAE03"

    # Non-existent seat -> 400 Bad Request ("seat_id not found")
    r_bad = client.post(
        "/reports",
        data={"seat_id": "NO-SEAT", "reporter_id": str(student_id), "text": "Invalid"},
    )
    assert r_bad.status_code == 400
    assert r_bad.json()["detail"] == "seat_id not found"


# ---------------------------------------------------------------------------
# BB-06: Image Report Upload (JPG/PNG allowed vs Unsupported Extension)
# ---------------------------------------------------------------------------
def test_bb06_submit_image_report_validation(test_ctx):
    client, _, student_id, _ = test_ctx

    fake_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    r_img = client.post(
        "/reports",
        data={"seat_id": "F1-01", "reporter_id": str(student_id), "text": "With photo"},
        files=[("images", ("evidence.png", io.BytesIO(fake_png), "image/png"))],
    )
    assert r_img.status_code == 200
    body = r_img.json()
    assert len(body["images"]) == 1
    assert body["images"][0].startswith(f"report/{body['id']}/")
    assert body["images"][0].endswith(".png")

    # Clean up test report directory written under BACKEND/config/report/{id}
    import shutil
    report_dir = BACKEND_ROOT / "config" / "report" / str(body["id"])
    if report_dir.exists():
        shutil.rmtree(report_dir, ignore_errors=True)

    # Unsupported extension (.exe / .gif) -> 400 Bad Request, transaction rolled back
    r_bad_ext = client.post(
        "/reports",
        data={"seat_id": "F1-02", "reporter_id": str(student_id), "text": "Bad file"},
        files=[("images", ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream"))],
    )
    assert r_bad_ext.status_code == 400
    assert "Unsupported file extension" in r_bad_ext.json()["detail"]
    # Verify F1-02 was NOT marked reported due to rollback
    assert client.get("/seats/F1-02").json()["is_reported"] is False


# ---------------------------------------------------------------------------
# BB-07: Role-Based Access Control (Anonymous & Student blocked from /admin/*)
# ---------------------------------------------------------------------------
def test_bb07_rbac_protection_on_admin_endpoints(test_ctx):
    client, _, _, _ = test_ctx
    student_token = _login_token(client, "student01", "123456")
    stu_headers = {"Authorization": f"Bearer {student_token}"}

    # Anonymous -> 401
    assert client.get("/admin/anomalies").status_code == 401

    # Student token -> 403 Forbidden ("Admin privileges required")
    for method, url in [
        ("GET", "/admin/anomalies"),
        ("GET", "/admin/reports/1"),
        ("POST", "/admin/reports/1/confirm"),
        ("DELETE", "/admin/anomalies/F1-01"),
        ("POST", "/admin/seats/F1-01/lock"),
    ]:
        resp = client.request(method, url, headers=stu_headers)
        assert resp.status_code == 403
        assert resp.json()["detail"] == "Admin privileges required"


# ---------------------------------------------------------------------------
# BB-08 & BB-09: Admin Confirm Toggle, Seat Lock (5 min), and Clear Anomaly
# (Resolves ambiguity #2 with real code behavior)
# ---------------------------------------------------------------------------
def test_bb08_bb09_admin_confirm_toggle_lock_and_clear(test_ctx):
    client, _, student_id, _ = test_ctx
    admin_token = _login_token(client, "admin01", "123456")
    headers = {"Authorization": f"Bearer {admin_token}"}

    # 1. Student reports occupied seat F1-03 (is_empty=False, has_power=False)
    rep = client.post(
        "/reports",
        data={"seat_id": "F1-03", "reporter_id": str(student_id), "text": "Hogging"},
    ).json()
    report_id = rep["id"]

    # 2. Admin lists anomalies -> F1-03 appears with last_report_id
    anomalies = client.get("/admin/anomalies", headers=headers).json()
    assert len(anomalies) == 1
    assert anomalies[0]["seat_id"] == "F1-03"
    assert anomalies[0]["last_report_id"] == report_id
    assert anomalies[0]["is_reported"] is True
    assert anomalies[0]["is_malicious"] is False

    # 3. Admin confirms anomaly (1st toggle):
    #    - is_malicious becomes True
    #    - report.status becomes 'confirmed'
    #    - admin_color inverts: occupied(False) + no_power(False) -> Green (#60D937)
    c1 = client.post(f"/admin/reports/{report_id}/confirm", headers=headers)
    assert c1.status_code == 200
    assert c1.json()["is_malicious"] is True
    assert c1.json()["admin_color"] == "#60D937"
    assert client.get(f"/admin/reports/{report_id}", headers=headers).json()["status"] == "confirmed"

    # 4. Admin locks seat for 5 minutes (as done by Flutter _toggleAnomaly)
    now = int(time.time())
    lock_res = client.post("/admin/seats/F1-03/lock", params={"minutes": 5}, headers=headers)
    assert lock_res.status_code == 200
    assert lock_res.json()["lock_until_ts"] >= now + 295

    # 5. Admin toggles confirm again (2nd toggle -> dismiss):
    #    - is_malicious becomes False
    #    - report.status becomes 'dismissed'
    c2 = client.post(f"/admin/reports/{report_id}/confirm", headers=headers)
    assert c2.status_code == 200
    assert c2.json()["is_malicious"] is False
    assert client.get(f"/admin/reports/{report_id}", headers=headers).json()["status"] == "dismissed"

    # 6. Admin clears anomaly (DELETE /admin/anomalies/F1-03):
    #    - is_reported=False, is_malicious=False
    #    - seat disappears from /admin/anomalies
    clr = client.delete("/admin/anomalies/F1-03", headers=headers)
    assert clr.status_code == 200
    assert clr.json()["is_reported"] is False
    assert clr.json()["is_malicious"] is False
    assert client.get("/admin/anomalies", headers=headers).json() == []


# ---------------------------------------------------------------------------
# BB-10: Seat Statistics & Manual Floor Refresh Fallback
# ---------------------------------------------------------------------------
def test_bb10_seat_stats_and_floor_refresh_fallback(test_ctx):
    client, _, _, _ = test_ctx

    # Stats for existing seat
    st = client.get("/stats/seats/F1-01")
    assert st.status_code == 200
    assert st.json()["seat_id"] == "F1-01"
    assert "daily_empty_seconds" in st.json()

    # Refresh configured floor F2 -> auto-seeds missing seats from F2.json (4 total)
    ref_f2 = client.post("/floors/F2/refresh")
    assert ref_f2.status_code == 200
    assert len(ref_f2.json()) == 4

    # Refresh unconfigured floor F3 (no F3.json) -> gracefully falls back to DB seats (0 seats)
    ref_f3 = client.post("/floors/F3/refresh")
    assert ref_f3.status_code == 200
    assert ref_f3.json() == []
