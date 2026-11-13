# -*- coding: utf-8 -*-
"""
Part 6 Integration Testing using Stubs and Drivers.

Implements both integration strategies required in SE_Practices_6.pdf:
1. Top-Down Integration Testing with Stubs (自顶向下集成测试 — 桩模块):
   - Stubs: StubFloorConfigLoader, StubVideoCapture, StubYOLODetector, StubRolloverTracker
   - Cases: IT-TD-01 .. IT-TD-04
2. Bottom-Up Integration Testing with Drivers (自底向上集成测试 — 驱动模块):
   - Drivers: SeatDetectionToRolloverDriver, ReportAdminLockIntegrationDriver,
              AuthSchedulerLifecycleDriver (with StubScheduler)
   - Cases: IT-BU-01 .. IT-BU-03
"""
from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Generator, List

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.auth import get_password_hash
from backend.db import Base, get_db
from backend.main import create_app
from backend.models import Report, Seat, User
from backend.routes import admin as admin_routes
from backend.routes import auth as auth_routes
from backend.routes import reports as report_routes
from backend.routes import seats as seat_routes
from backend.scheduler import FloorRefreshScheduler
from backend.services import roi_loader, rollover, yolo_service
from backend.services.color import compute_admin_color, compute_floor_color, compute_seat_color
from backend.services.yolo_service import Detection


# ===========================================================================
# Reusable Stub Modules (桩模块) for Top-Down Integration
# ===========================================================================
class StubVideoCapture:
    """Stub replacing cv2.VideoCapture: supplies deterministic frames without real MP4 I/O."""

    def __init__(self, opened: bool = True, total_frames: int = 30) -> None:
        self._opened = opened
        self.total_frames = total_frames
        self.pos = 0
        self.released = False

    def isOpened(self) -> bool:
        return self._opened

    def set(self, prop_id: int, val: float) -> bool:
        self.pos = int(val)
        return True

    def read(self):
        if not self._opened:
            return False, None
        frame_idx = self.pos
        self.pos += 1
        return True, {"frame_idx": frame_idx}

    def release(self) -> None:
        self.released = True


class StubYOLODetector:
    """Stub replacing YOLODetector: returns scripted Detection lists per scenario."""

    def __init__(self, scripted_detections: List[Detection]) -> None:
        self.person_name = "person"
        self.object_names = yolo_service.OBJECT_NAMES_DEFAULT
        self.scripted_detections = scripted_detections
        self.calls = 0

    def detect_frame(self, frame: Any) -> List[Detection]:
        self.calls += 1
        return list(self.scripted_detections)


class StubFloorConfigLoader:
    """Stub replacing roi_loader.load_floor_config."""

    def __init__(self, configs: Dict[str, Dict[str, Any]]) -> None:
        self.configs = configs

    def load(self, floor_id: str) -> Dict[str, Any]:
        if floor_id not in self.configs:
            raise FileNotFoundError(f"Floor config not found: {floor_id}")
        return self.configs[floor_id]


class StubRolloverTracker:
    """Stub replacing rollover.perform_rollovers_if_needed to observe calls or inject faults."""

    def __init__(self, raise_error: bool = False) -> None:
        self.raise_error = raise_error
        self.calls: List[int] = []

    def __call__(self, db: Session, now_ts: int) -> None:
        self.calls.append(now_ts)
        if self.raise_error:
            raise RuntimeError("Simulated rollover I/O failure")


class StubScheduler:
    """Stub replacing FloorRefreshScheduler in auth lifecycle driver tests."""

    def __init__(self) -> None:
        self.started = False
        self.start_count = 0
        self.shutdown_count = 0

    def start(self) -> None:
        self.started = True
        self.start_count += 1

    def shutdown(self) -> None:
        self.started = False
        self.shutdown_count += 1


# ===========================================================================
# Shared Test Config & DB Helper
# ===========================================================================
TEST_F1_CFG: Dict[str, Any] = {
    "floor_id": "F1",
    "stream_path": "stub://F1.mp4",
    "frame_size": [1920, 1080],
    "seats": [
        {"seat_id": "F1-01", "has_power": 0, "desk_roi": [[0, 0], [500, 0], [500, 500], [0, 500]]},
        {"seat_id": "F1-02", "has_power": 1, "desk_roi": [[600, 0], [1100, 0], [1100, 500], [600, 500]]},
    ],
}


def _make_memory_sessionmaker():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    return sessionmaker(autocommit=False, autoflush=False, bind=engine)


# ===========================================================================
# Part 1: Top-Down Integration Tests using Stubs (自顶向下集成测试)
# ===========================================================================
def test_it_td01_top_down_api_refresh_to_color_with_stubs(monkeypatch: pytest.MonkeyPatch):
    """
    IT-TD-01: Top-down integration from FastAPI routes (/floors/F1/refresh -> /seats -> /floors)
    down to yolo_service & color, stubbing VideoCapture, YOLODetector, FloorConfigLoader, and Rollover.
    """
    SessionLocal = _make_memory_sessionmaker()
    app = create_app()

    def override_get_db() -> Generator:
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db

    cfg_stub = StubFloorConfigLoader({"F1": TEST_F1_CFG})
    cap_stub = StubVideoCapture(opened=True, total_frames=30)
    vstate = yolo_service.VideoState(cap=cap_stub, total_frames=30, fps=5.0, next_frame_idx=0, stream_path="stub://F1.mp4")
    # F1-01 has a person at (250, 250); F1-02 is empty
    det_stub = StubYOLODetector([Detection(200, 200, 300, 300, 0.95, "person")])
    roll_stub = StubRolloverTracker()

    monkeypatch.setattr(seat_routes, "load_floor_config", cfg_stub.load)
    monkeypatch.setattr(yolo_service, "_open_or_get_video_state", lambda fid, sp: vstate)
    monkeypatch.setattr(yolo_service, "get_detector", lambda: det_stub)
    monkeypatch.setattr(yolo_service, "perform_rollovers_if_needed", roll_stub)

    with TestClient(app) as client:
        # Phase 1: F1-01 occupied, F1-02 empty+power -> 1/2 empty (50% -> Yellow)
        r1 = client.post("/floors/F1/refresh")
        assert r1.status_code == 200
        by_id = {x["seat_id"]: x for x in r1.json()}
        assert by_id["F1-01"]["is_empty"] is False
        assert by_id["F1-01"]["seat_color"] == "#929292"
        assert by_id["F1-02"]["is_empty"] is True
        assert by_id["F1-02"]["seat_color"] == "#00A1FF"

        floors = client.get("/floors").json()
        assert floors[0]["empty_count"] == 1
        assert floors[0]["total_count"] == 2
        assert floors[0]["floor_color"] == "#FEAE03"
        assert len(roll_stub.calls) == 1
        assert det_stub.calls >= 1

        # Phase 2: Stub detector switches to all empty -> F1-01 turns Green, floor turns Green (100%)
        det_stub.scripted_detections = []
        r2 = client.post("/floors/F1/refresh")
        assert r2.status_code == 200
        by_id2 = {x["seat_id"]: x for x in r2.json()}
        assert by_id2["F1-01"]["seat_color"] == "#60D937"
        assert client.get("/floors").json()[0]["floor_color"] == "#60D937"


def test_it_td02_scheduler_job_integration_with_stubs(monkeypatch: pytest.MonkeyPatch):
    """
    IT-TD-02: Top-down integration of FloorRefreshScheduler._refresh_job with DB + Stubs,
    including graceful exception isolation when config is missing.
    """
    SessionLocal = _make_memory_sessionmaker()
    from backend import scheduler as sched_mod

    cfg_stub = StubFloorConfigLoader({"F1": TEST_F1_CFG})
    cap_stub = StubVideoCapture(opened=True, total_frames=20)
    vstate = yolo_service.VideoState(cap=cap_stub, total_frames=20, fps=5.0, next_frame_idx=0, stream_path="stub://F1.mp4")
    det_stub = StubYOLODetector([Detection(800, 200, 900, 300, 0.9, "backpack")])  # hits F1-02

    monkeypatch.setattr(sched_mod, "SessionLocal", SessionLocal)
    monkeypatch.setattr(sched_mod, "load_floor_config", cfg_stub.load)
    monkeypatch.setattr(yolo_service, "_open_or_get_video_state", lambda fid, sp: vstate)
    monkeypatch.setattr(yolo_service, "get_detector", lambda: det_stub)

    sched = FloorRefreshScheduler(interval_seconds=5)
    sched._refresh_job("F1")

    db = SessionLocal()
    s1 = db.query(Seat).filter_by(seat_id="F1-01").one()
    s2 = db.query(Seat).filter_by(seat_id="F1-02").one()
    assert s1.is_empty is True
    assert s2.is_empty is False
    assert s2.occupancy_start_ts > 0
    db.close()

    # Missing config for F9 should be caught inside _refresh_job without crashing
    sched._refresh_job("F9")


def test_it_td03_unopened_stream_stub_preserves_db_state(monkeypatch: pytest.MonkeyPatch):
    """IT-TD-03: StubVideoCapture(opened=False) verifies API refresh stays safe when video fails."""
    SessionLocal = _make_memory_sessionmaker()
    db = SessionLocal()
    db.add(Seat(seat_id="F1-01", floor_id="F1", has_power=False, is_empty=False))
    db.commit()
    db.close()

    app = create_app()
    def override_get_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override_get_db

    cfg_stub = StubFloorConfigLoader({"F1": TEST_F1_CFG})
    cap_closed = StubVideoCapture(opened=False)
    vstate = yolo_service.VideoState(cap=cap_closed, total_frames=0, fps=30.0, next_frame_idx=0, stream_path="stub://bad.mp4")

    monkeypatch.setattr(seat_routes, "load_floor_config", cfg_stub.load)
    monkeypatch.setattr(yolo_service, "_open_or_get_video_state", lambda fid, sp: vstate)

    with TestClient(app) as client:
        r = client.post("/floors/F1/refresh")
        assert r.status_code == 200
        by_id = {x["seat_id"]: x for x in r.json()}
        # Existing F1-01 kept its prior occupied state instead of crashing
        assert by_id["F1-01"]["is_empty"] is False


def test_it_td04_rollover_stub_exception_does_not_block_detection(monkeypatch: pytest.MonkeyPatch):
    """IT-TD-04: StubRolloverTracker raises error -> refresh_floor catches it and completes seat detection."""
    SessionLocal = _make_memory_sessionmaker()
    db = SessionLocal()

    cap_stub = StubVideoCapture(opened=True, total_frames=10)
    vstate = yolo_service.VideoState(cap=cap_stub, total_frames=10, fps=5.0, next_frame_idx=0, stream_path="stub://F1.mp4")
    det_stub = StubYOLODetector([Detection(200, 200, 300, 300, 0.9, "person")])
    faulty_roll = StubRolloverTracker(raise_error=True)

    monkeypatch.setattr(yolo_service, "_open_or_get_video_state", lambda fid, sp: vstate)
    monkeypatch.setattr(yolo_service, "get_detector", lambda: det_stub)
    monkeypatch.setattr(yolo_service, "perform_rollovers_if_needed", faulty_roll)

    seats = {s.seat_id: s for s in yolo_service.refresh_floor(db, TEST_F1_CFG)}
    assert len(faulty_roll.calls) == 1
    assert seats["F1-01"].is_empty is False
    db.close()


# ===========================================================================
# Part 2: Bottom-Up Integration Tests using Drivers (自底向上集成测试)
# ===========================================================================
class SeatDetectionToRolloverDriver:
    """
    Driver driving lower-level modules directly:
      roi_loader -> yolo_service.refresh_floor -> color -> rollover.perform_rollovers_if_needed
    """

    def __init__(self, db: Session, cfg: Dict[str, Any]) -> None:
        self.db = db
        self.cfg = cfg

    def run_cycle(self) -> Dict[str, str]:
        seats = yolo_service.refresh_floor(self.db, self.cfg)
        colors = {}
        for s in seats:
            base = compute_seat_color(s.is_empty, s.has_power, s.is_reported)
            colors[s.seat_id] = compute_admin_color(base, s.is_malicious, s.is_empty, s.has_power)
        return colors

    def run_midnight_rollover(self, now_ts: int) -> None:
        rollover.perform_rollovers_if_needed(self.db, now_ts)


def test_it_bu01_bottom_up_detection_color_and_rollover_driver(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    IT-BU-01: Bottom-up integration driven by SeatDetectionToRolloverDriver.
    Verifies >2h malicious alarm -> color inversion -> midnight daily+monthly TXT export & reset.
    """
    monkeypatch.setattr(rollover, "OUTPUTS_DIR", tmp_path)
    SessionLocal = _make_memory_sessionmaker()
    db = SessionLocal()

    now_ts = int(time.time())
    cur_dt = datetime.fromtimestamp(now_ts, tz=timezone.utc).astimezone()
    cur_month_str = cur_dt.strftime("%Y-%m")
    cur_date_str = cur_dt.strftime("%Y-%m-%d")

    db.add(
        Seat(
            seat_id="F1-01",
            floor_id="F1",
            has_power=False,
            is_empty=False,
            occupancy_start_ts=now_ts - 7250,  # > 2h object-only on the same day
            daily_empty_seconds=1800,
            total_empty_seconds=36000,
            last_update_ts=now_ts - 60,
            last_state_is_empty=True,
        )
    )
    db.commit()

    cap_stub = StubVideoCapture(opened=True, total_frames=10)
    vstate = yolo_service.VideoState(cap=cap_stub, total_frames=10, fps=5.0, next_frame_idx=0, stream_path="stub://F1.mp4")
    det_stub = StubYOLODetector([Detection(200, 200, 300, 300, 0.9, "backpack")])
    monkeypatch.setattr(yolo_service, "_open_or_get_video_state", lambda fid, sp: vstate)
    monkeypatch.setattr(yolo_service, "get_detector", lambda: det_stub)

    driver = SeatDetectionToRolloverDriver(db, TEST_F1_CFG)
    admin_colors = driver.run_cycle()
    # F1-01 becomes malicious (occupied + no power -> admin inverted color is Green #60D937)
    assert admin_colors["F1-01"] == "#60D937"
    assert compute_floor_color(1, 2) == "#FEAE03"

    # Advance 35 days into the next month and drive rollover
    next_month_ts = now_ts + 35 * 86400
    driver.run_midnight_rollover(next_month_ts)
    assert (tmp_path / "monthly" / f"{cur_month_str}.txt").exists()
    assert (tmp_path / cur_date_str / "daily_empty.txt").exists()
    s1 = db.query(Seat).filter_by(seat_id="F1-01").one()
    assert s1.is_malicious is False
    assert s1.total_empty_seconds == 0
    assert s1.daily_empty_seconds == 0
    db.close()


class ReportAdminLockIntegrationDriver:
    """
    Driver coordinating reports -> admin confirm/lock -> yolo_service.refresh_floor -> clear.
    Verifies 5-minute seat lock prevents YOLO from overwriting admin-confirmed state.
    """

    def __init__(self, db: Session, cfg: Dict[str, Any]) -> None:
        self.db = db
        self.cfg = cfg

    def submit_and_lock(self, seat_id: str, reporter_id: int, minutes: int = 5) -> int:
        rep = report_routes.create_report(seat_id=seat_id, reporter_id=reporter_id, text="Hogging", images=None, db=self.db)
        admin_routes.confirm_toggle(report_id=rep.id, db=self.db)
        admin_routes.lock_seat(seat_id=seat_id, minutes=minutes, db=self.db)
        return rep.id


def test_it_bu02_bottom_up_report_lock_and_yolo_driver(monkeypatch: pytest.MonkeyPatch):
    """IT-BU-02: Driver verifies locked seat keeps state even when YOLO sees empty frame, and resumes after unlock."""
    SessionLocal = _make_memory_sessionmaker()
    db = SessionLocal()
    db.add(User(username="stu_drv", pass_hash=get_password_hash("123456"), role="student"))
    db.add(Seat(seat_id="F1-01", floor_id="F1", has_power=False, is_empty=False))
    db.commit()
    stu = db.query(User).filter_by(username="stu_drv").one()

    cap_stub = StubVideoCapture(opened=True, total_frames=10)
    vstate = yolo_service.VideoState(cap=cap_stub, total_frames=10, fps=5.0, next_frame_idx=0, stream_path="stub://F1.mp4")
    # YOLO detects NO people and NO objects (empty)
    det_stub = StubYOLODetector([])
    monkeypatch.setattr(yolo_service, "_open_or_get_video_state", lambda fid, sp: vstate)
    monkeypatch.setattr(yolo_service, "get_detector", lambda: det_stub)

    driver = ReportAdminLockIntegrationDriver(db, TEST_F1_CFG)
    driver.submit_and_lock("F1-01", stu.id, minutes=5)

    # While locked, refresh_floor MUST NOT flip is_empty back to True
    yolo_service.refresh_floor(db, TEST_F1_CFG)
    s1 = db.query(Seat).filter_by(seat_id="F1-01").one()
    assert s1.is_empty is False
    assert s1.is_reported is True
    assert s1.is_malicious is True

    # Simulate lock expired + admin cleared anomaly -> refresh_floor resumes updating to True
    s1.lock_until_ts = int(time.time()) - 1
    db.commit()
    admin_routes.clear_anomaly(seat_id="F1-01", db=db)
    yolo_service.refresh_floor(db, TEST_F1_CFG)
    db.refresh(s1)
    assert s1.is_empty is True
    assert s1.is_reported is False
    db.close()


class AuthSchedulerLifecycleDriver:
    """
    Driver exercising Auth routes (register/login/logout) integrated with StubScheduler
    to verify active-user counting starts scheduler on 1st login and stops it when 0 users remain.
    """

    def __init__(self, client: TestClient) -> None:
        self.client = client

    def login(self, username: str, password: str = "123456") -> str:
        r = self.client.post("/auth/login", data={"username": username, "password": password})
        assert r.status_code == 200
        return r.json()["access_token"]

    def register(self, username: str, password: str = "123456") -> str:
        r = self.client.post("/auth/register", json={"username": username, "password": password})
        assert r.status_code == 200
        return r.json()["access_token"]

    def logout(self, token: str) -> None:
        r = self.client.post("/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200


def test_it_bu03_auth_scheduler_lifecycle_driver():
    """IT-BU-03: Auth + Scheduler integration via AuthSchedulerLifecycleDriver."""
    SessionLocal = _make_memory_sessionmaker()
    auth_routes._active_users.clear()

    db = SessionLocal()
    db.add(User(username="u1", pass_hash=get_password_hash("123456"), role="student"))
    db.commit()
    db.close()

    app = create_app()
    def override_get_db():
        s = SessionLocal()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = override_get_db

    stub_sched = StubScheduler()
    with TestClient(app) as client:
        app.state.scheduler = stub_sched
        drv = AuthSchedulerLifecycleDriver(client)

        # 1st user logs in -> scheduler starts (count=1)
        t1 = drv.login("u1")
        assert stub_sched.started is True
        assert stub_sched.start_count == 1

        # 2nd user registers -> already started, does not restart
        t2 = drv.register("u2")
        assert stub_sched.started is True
        assert stub_sched.start_count == 1

        # 1st user logs out -> 1 user remains, scheduler stays running
        drv.logout(t1)
        assert stub_sched.started is True
        assert stub_sched.shutdown_count == 0

        # Last user logs out -> scheduler shuts down
        drv.logout(t2)
        assert stub_sched.started is False
        assert stub_sched.shutdown_count == 1
