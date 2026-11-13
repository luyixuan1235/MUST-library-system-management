# -*- coding: utf-8 -*-
"""
White-box Test Suite (WB-01 .. WB-12) for Library Seat Management System.

Directly targets internal branches, conditions, and exception paths in:
1. backend.services.roi_loader (validate_floor_config, load_floor_config, _polygon_area, _is_number)
2. backend.services.color (compute_seat_color, compute_admin_color, compute_floor_color)
3. backend.services.yolo_service (point_in_polygon, refresh_floor state machine, 2h malicious timer, 5m lock)
4. backend.services.rollover (export_daily_and_reset, export_monthly_and_reset_total, perform_rollovers_if_needed)
"""
from __future__ import annotations

import copy
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from backend.db import Base
from backend.models import Seat
from backend.services import roi_loader, rollover, yolo_service
from backend.services.color import (
    ADMIN_YELLOW,
    FLOOR_RED,
    SEAT_BLUE,
    SEAT_GRAY,
    SEAT_GREEN,
    compute_admin_color,
    compute_floor_color,
    compute_seat_color,
)
from backend.services.roi_loader import (
    _is_number,
    _polygon_area,
    load_floor_config,
    validate_floor_config,
)
from backend.services.yolo_service import Detection, point_in_polygon, refresh_floor


VALID_CFG = {
    "floor_id": "F1",
    "stream_path": "input/test/F1.mp4",
    "frame_size": [1920, 1080],
    "seats": [
        {
            "seat_id": "F1-01",
            "has_power": 1,
            "desk_roi": [[100.0, 100.0], [300.0, 100.0], [300.0, 300.0], [100.0, 300.0]],
        }
    ],
}


# ---------------------------------------------------------------------------
# WB-01: Root Object Type Check (line 27-28 of roi_loader.py)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_root", [[], "string", 123, None])
def test_wb01_root_must_be_dict(bad_root):
    validate_floor_config(copy.deepcopy(VALID_CFG))  # True branch
    with pytest.raises(ValueError, match="config must be an object"):
        validate_floor_config(bad_root)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# WB-02: floor_id and stream_path Non-Empty String Branches (lines 29-32)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_val", ["", None, 123, []])
def test_wb02_floor_id_and_stream_path_branches(bad_val):
    cfg1 = copy.deepcopy(VALID_CFG)
    cfg1["floor_id"] = bad_val
    with pytest.raises(ValueError, match="floor_id must be a non-empty string"):
        validate_floor_config(cfg1)

    cfg2 = copy.deepcopy(VALID_CFG)
    cfg2["stream_path"] = bad_val
    with pytest.raises(ValueError, match="stream_path must be a non-empty string"):
        validate_floor_config(cfg2)


# ---------------------------------------------------------------------------
# WB-03: frame_size Optional & Positive-Integer Validation (lines 34-40)
# ---------------------------------------------------------------------------
def test_wb03_frame_size_branches():
    # Omitted frame_size -> width = height = None branch
    cfg_no_fs = copy.deepcopy(VALID_CFG)
    del cfg_no_fs["frame_size"]
    validate_floor_config(cfg_no_fs)

    # Invalid frame_size cases
    for bad_fs in ["640x480", [640], [640, 480, 3], [0, 480], [640, -1], [640.5, 480]]:
        cfg = copy.deepcopy(VALID_CFG)
        cfg["frame_size"] = bad_fs
        with pytest.raises(ValueError, match="frame_size must be"):
            validate_floor_config(cfg)


# ---------------------------------------------------------------------------
# WB-04: seats Array Type & Non-Empty Check (lines 42-44)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("bad_seats", [None, [], {}, "seats"])
def test_wb04_seats_array_branches(bad_seats):
    cfg = copy.deepcopy(VALID_CFG)
    cfg["seats"] = bad_seats
    with pytest.raises(ValueError, match="seats must be a non-empty array"):
        validate_floor_config(cfg)


# ---------------------------------------------------------------------------
# WB-05: Per-Seat Structure & Type Validation (lines 46-54)
# ---------------------------------------------------------------------------
def test_wb05_seat_structure_branches():
    # Seat not a dict
    cfg = copy.deepcopy(VALID_CFG)
    cfg["seats"] = ["not-a-dict"]
    with pytest.raises(ValueError, match=r"seats\[0\] must be an object"):
        validate_floor_config(cfg)

    # Missing/empty seat_id
    cfg = copy.deepcopy(VALID_CFG)
    cfg["seats"][0]["seat_id"] = ""
    with pytest.raises(ValueError, match=r"seats\[0\]\.seat_id must be a non-empty string"):
        validate_floor_config(cfg)

    # Invalid has_power type (string/float rejected; bool and int accepted)
    cfg = copy.deepcopy(VALID_CFG)
    cfg["seats"][0]["has_power"] = "yes"
    with pytest.raises(ValueError, match=r"seats\[0\]\.has_power must be boolean or 0/1"):
        validate_floor_config(cfg)

    # _is_number explicitly rejects bool even though isinstance(True, int) is True
    assert _is_number(10) is True
    assert _is_number(10.5) is True
    assert _is_number(True) is False


# ---------------------------------------------------------------------------
# WB-06: ROI Polygon Vertex Count & Shoelace Area > 0 (lines 16-23, 53-63)
# ---------------------------------------------------------------------------
def test_wb06_roi_polygon_vertices_and_area():
    # Fewer than 3 points
    cfg_2pts = copy.deepcopy(VALID_CFG)
    cfg_2pts["seats"][0]["desk_roi"] = [[0, 0], [10, 10]]
    with pytest.raises(ValueError, match="must be an array of >=3 points"):
        validate_floor_config(cfg_2pts)

    # Invalid point structure (bool coordinate or wrong length)
    cfg_bool_pt = copy.deepcopy(VALID_CFG)
    cfg_bool_pt["seats"][0]["desk_roi"] = [[True, 10], [20, 10], [20, 20]]
    with pytest.raises(ValueError, match=r"must be \[x, y\] numbers"):
        validate_floor_config(cfg_bool_pt)

    # Collinear points -> _polygon_area == 0.0 -> rejected
    cfg_collinear = copy.deepcopy(VALID_CFG)
    cfg_collinear["seats"][0]["desk_roi"] = [[10, 10], [20, 20], [30, 30]]
    assert _polygon_area(cfg_collinear["seats"][0]["desk_roi"]) == 0.0
    with pytest.raises(ValueError, match="polygon area must be > 0"):
        validate_floor_config(cfg_collinear)


# ---------------------------------------------------------------------------
# WB-07: Coordinate Bounds Check (0 <= x <= width, 0 <= y <= height)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "bad_pt,expected_msg",
    [
        ([-1, 100], "x out of bounds"),
        ([1921, 100], "x out of bounds"),
        ([100, -0.1], "y out of bounds"),
        ([100, 1081], "y out of bounds"),
    ],
)
def test_wb07_coordinate_bounds_branches(bad_pt, expected_msg):
    cfg = copy.deepcopy(VALID_CFG)
    cfg["seats"][0]["desk_roi"][0] = bad_pt
    with pytest.raises(ValueError, match=expected_msg):
        validate_floor_config(cfg)


# ---------------------------------------------------------------------------
# WB-08 & WB-09: load_floor_config File I/O, JSON Parsing & Auto-fill floor_id
# ---------------------------------------------------------------------------
def test_wb08_wb09_load_floor_config_io_and_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(roi_loader, "FLOORS_DIR", tmp_path)

    # 1. FileNotFoundError branch
    with pytest.raises(FileNotFoundError, match="Floor config not found"):
        load_floor_config("MISSING")

    # 2. Truncated/invalid JSON -> JSONDecodeError
    (tmp_path / "BADJSON.json").write_text("{invalid json", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        load_floor_config("BADJSON")

    # 3. Valid JSON missing "floor_id" key -> auto-filled from filename parameter (line 75-76)
    cfg_without_id = copy.deepcopy(VALID_CFG)
    del cfg_without_id["floor_id"]
    (tmp_path / "F9.json").write_text(json.dumps(cfg_without_id), encoding="utf-8")
    loaded = load_floor_config("F9")
    assert loaded["floor_id"] == "F9"


# ---------------------------------------------------------------------------
# WB-10: All Branches of compute_seat_color, compute_admin_color, compute_floor_color
# ---------------------------------------------------------------------------
def test_wb10_all_color_service_branches():
    # compute_seat_color
    assert compute_seat_color(is_empty=True, has_power=False, is_reported=True) == ADMIN_YELLOW
    assert compute_seat_color(is_empty=False, has_power=True, is_reported=False) == SEAT_GRAY
    assert compute_seat_color(is_empty=True, has_power=True, is_reported=False) == SEAT_BLUE
    assert compute_seat_color(is_empty=True, has_power=False, is_reported=False) == SEAT_GREEN

    # compute_admin_color (inversion when is_malicious=True)
    assert compute_admin_color(SEAT_GREEN, is_malicious=False, is_empty=True, has_power=False) == SEAT_GREEN
    assert compute_admin_color(SEAT_GREEN, is_malicious=True, is_empty=True, has_power=False) == SEAT_GRAY
    assert compute_admin_color(SEAT_GRAY, is_malicious=True, is_empty=False, has_power=True) == SEAT_BLUE
    assert compute_admin_color(SEAT_GRAY, is_malicious=True, is_empty=False, has_power=False) == SEAT_GREEN

    # compute_floor_color
    assert compute_floor_color(0, 0) == FLOOR_RED
    assert compute_floor_color(0, 10) == FLOOR_RED
    assert compute_floor_color(6, 10) == SEAT_GREEN
    assert compute_floor_color(5, 10) == ADMIN_YELLOW


# ---------------------------------------------------------------------------
# WB-11: Ray-Casting point_in_polygon & YOLO Occupancy / 2h Malicious / Lock
# ---------------------------------------------------------------------------
def test_wb11_point_in_polygon_and_yolo_state_machine(monkeypatch: pytest.MonkeyPatch):
    poly = [[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]]
    assert point_in_polygon((50.0, 50.0), poly) is True
    assert point_in_polygon((150.0, 50.0), poly) is False

    # Setup in-memory DB for refresh_floor state machine test
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    now_ts = int(time.time())
    # Pre-seed seat with object_only occupancy starting 7201s ago (> 2 hours)
    seat = Seat(
        seat_id="F1-01",
        floor_id="F1",
        has_power=False,
        is_empty=False,
        is_malicious=False,
        occupancy_start_ts=now_ts - 7205,
        last_update_ts=now_ts - 10,
        last_state_is_empty=True,
        lock_until_ts=0,
    )
    db.add(seat)
    db.commit()

    # Mock video state & detector to return an 'object' ("backpack") inside F1-01 ROI (no person)
    fake_cap = MagicMock()
    fake_cap.isOpened.return_value = True
    fake_cap.read.return_value = (True, MagicMock())
    fake_vstate = yolo_service.VideoState(
        cap=fake_cap, total_frames=10, fps=2.0, next_frame_idx=0, stream_path="dummy.mp4"
    )
    monkeypatch.setattr(yolo_service, "_open_or_get_video_state", lambda fid, sp: fake_vstate)

    fake_detector = MagicMock()
    fake_detector.person_name = "person"
    fake_detector.object_names = {"backpack"}
    # Center (200, 200) is inside VALID_CFG F1-01 ROI [100..300, 100..300]
    fake_detector.detect_frame.return_value = [Detection(180, 180, 220, 220, 0.9, "backpack")]
    monkeypatch.setattr(yolo_service, "get_detector", lambda: fake_detector)

    updated = refresh_floor(db, VALID_CFG)
    s = updated[0]
    assert s.is_empty is False
    assert s.is_malicious is True  # >= 7200s object-only triggers malicious auto-alarm!
    assert s.daily_empty_seconds >= 10
    assert s.change_count == 1
    db.close()


# ---------------------------------------------------------------------------
# WB-12: Daily & Monthly Rollover Export and Offline Catch-up
# ---------------------------------------------------------------------------
def test_wb12_daily_and_monthly_rollover(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(rollover, "OUTPUTS_DIR", tmp_path)

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    # Seed seat with last_update_ts in the previous month
    prev_month_dt = datetime(2025, 10, 31, 12, 0, 0, tzinfo=timezone.utc)
    now_dt = datetime(2025, 11, 1, 0, 5, 0, tzinfo=timezone.utc)
    db.add(
        Seat(
            seat_id="F1-01",
            floor_id="F1",
            has_power=True,
            is_empty=False,
            is_reported=True,
            is_malicious=True,
            daily_empty_seconds=3600,
            total_empty_seconds=72000,
            last_update_ts=int(prev_month_dt.timestamp()),
        )
    )
    db.commit()

    rollover.perform_rollovers_if_needed(db, int(now_dt.timestamp()))

    # Verify both daily and monthly files were exported and counters/flags were reset
    daily_file = tmp_path / "2025-10-31" / "daily_empty.txt"
    monthly_file = tmp_path / "monthly" / "2025-10.txt"
    assert daily_file.exists()
    assert monthly_file.exists()
    assert "F1-01 01h00min00s" in daily_file.read_text(encoding="utf-8")
    assert "F1-01 20h00min00s" in monthly_file.read_text(encoding="utf-8")

    s = db.query(Seat).filter_by(seat_id="F1-01").one()
    assert s.daily_empty_seconds == 0
    assert s.total_empty_seconds == 0
    assert s.is_reported is False
    assert s.is_malicious is False
    assert s.is_empty is True
    db.close()
