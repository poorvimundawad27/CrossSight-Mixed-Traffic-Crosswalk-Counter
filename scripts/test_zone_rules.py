import json
from datetime import datetime, timedelta, timezone

import pytest
from zone_rules import ZoneMonitor

BASE = datetime(2026, 10, 18, 10, 0, 0, tzinfo=timezone.utc)

INSIDE = [200, 200, 300, 350]
OUTSIDE = [600, 200, 700, 350]
EDGE = [50, 200, 110, 350]  # overlaps the zone by 10 pixels


@pytest.fixture
def cfg(tmp_path):
    return {
        "zone_id": "restricted_1",
        "polygon": [[100, 100], [400, 100], [400, 400], [100, 400]],
        "target_class": "person",
        "min_confidence": 0.5,
        "persistence_seconds": 1.0,
        "cooldown_seconds": 8,
        "output_file": str(tmp_path / "incidents.jsonl"),
    }


def person(bbox, conf=0.9, cls="person"):
    return {"class": cls, "confidence": conf, "bbox": bbox}


def frame(ms, objects):
    ts = (BASE + timedelta(milliseconds=ms)).isoformat()
    return {"timestamp": ts, "objects": objects}


def run(mon, objects, duration_ms, start_ms=0, step=200):
    events = []
    for t in range(start_ms, start_ms + duration_ms + 1, step):
        events += mon.process_frame(frame(t, objects))
    return events


def test_outside_zone_no_event(cfg):
    assert run(ZoneMonitor(cfg), [person(OUTSIDE)], 3000) == []


def test_inside_zone_one_event(cfg):
    events = run(ZoneMonitor(cfg), [person(INSIDE)], 2000)
    assert len(events) == 1
    assert events[0]["event_type"] == "zone_intrusion"


def test_brief_flicker_no_event(cfg):
    mon = ZoneMonitor(cfg)
    events = run(mon, [person(INSIDE)], 200)
    events += mon.process_frame(frame(400, []))
    assert events == []


def test_edge_overlap_triggers(cfg):
    assert len(run(ZoneMonitor(cfg), [person(EDGE)], 2000)) == 1


def test_cooldown_suppresses_repeats(cfg):
    assert len(run(ZoneMonitor(cfg), [person(INSIDE)], 5000)) == 1


def test_low_confidence_ignored(cfg):
    assert run(ZoneMonitor(cfg), [person(INSIDE, conf=0.3)], 3000) == []


def test_wrong_class_ignored(cfg):
    assert run(ZoneMonitor(cfg), [person(INSIDE, cls="car")], 3000) == []


def test_event_written_to_file(cfg):
    run(ZoneMonitor(cfg), [person(INSIDE)], 2000)
    with open(cfg["output_file"]) as f:
        lines = f.read().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["status"] == "new"


# ---------------------------------------------------------------------------
# Adapter tests: PipeGen output may differ from the preferred format
# ---------------------------------------------------------------------------

def test_class_name_capitalized(cfg):
    assert len(run(ZoneMonitor(cfg), [person(INSIDE, cls="Person")], 2000)) == 1


def test_numeric_class_id_zero_is_person(cfg):
    assert len(run(ZoneMonitor(cfg), [person(INSIDE, cls=0)], 2000)) == 1


def test_numeric_class_id_other_ignored(cfg):
    assert run(ZoneMonitor(cfg), [person(INSIDE, cls=2)], 3000) == []


def test_custom_class_map(cfg):
    cfg["class_map"] = {"5": "person"}
    assert len(run(ZoneMonitor(cfg), [person(INSIDE, cls=5)], 2000)) == 1


def test_alternate_key_names(cfg):
    mon = ZoneMonitor(cfg)
    events = []
    for t in range(0, 2001, 200):
        meta = {"timestamp": frame(t, [])["timestamp"],
                "detections": [{"label": "person", "score": 0.8, "box": INSIDE}]}
        events += mon.process_frame(meta)
    assert len(events) == 1


def test_xywh_bbox_format(cfg):
    cfg["bbox_format"] = "xywh"
    xywh_inside = [200, 200, 100, 150]      # = [200,200,300,350]
    xywh_outside = [600, 200, 100, 150]
    assert len(run(ZoneMonitor(cfg), [person(xywh_inside)], 2000)) == 1
    assert run(ZoneMonitor(cfg), [person(xywh_outside)], 2000) == []


def test_dict_bbox_left_top_width_height(cfg):
    b = {"left": 200, "top": 200, "width": 100, "height": 150}
    events = run(ZoneMonitor(cfg), [person(b)], 2000)
    assert len(events) == 1
    assert events[0]["bbox"] == [200, 200, 300, 350]


def test_dict_bbox_xmin_ymin_xmax_ymax(cfg):
    b = {"xmin": 200, "ymin": 200, "xmax": 300, "ymax": 350}
    assert len(run(ZoneMonitor(cfg), [person(b)], 2000)) == 1


def test_epoch_seconds_timestamps(cfg):
    mon = ZoneMonitor(cfg)
    events = []
    for t in range(0, 2001, 200):
        events += mon.process_frame({"timestamp": BASE.timestamp() + t / 1000,
                                     "objects": [person(INSIDE)]})
    assert len(events) == 1


def test_epoch_milliseconds_timestamps(cfg):
    mon = ZoneMonitor(cfg)
    events = []
    for t in range(0, 2001, 200):
        events += mon.process_frame({"timestamp": int(BASE.timestamp() * 1000) + t,
                                     "objects": [person(INSIDE)]})
    assert len(events) == 1


def test_relative_nanosecond_timestamps(cfg):
    cfg["timestamp_unit"] = "ns"
    mon = ZoneMonitor(cfg)
    events = []
    for i in range(0, 11):
        events += mon.process_frame({"timestamp": i * 200_000_000,
                                     "objects": [person(INSIDE)]})
    assert len(events) == 1


def test_frame_numbers_instead_of_timestamps(cfg):
    cfg["fps"] = 5
    mon = ZoneMonitor(cfg)
    events = []
    for n in range(0, 11):   # 2 seconds at 5 fps
        events += mon.process_frame({"frame": n, "objects": [person(INSIDE)]})
    assert len(events) == 1


def test_missing_timestamp_does_not_crash(cfg):
    mon = ZoneMonitor(cfg)
    assert mon.process_frame({"objects": [person(INSIDE)]}) == []


def test_json_string_input(cfg):
    mon = ZoneMonitor(cfg)
    events = []
    for t in range(0, 2001, 200):
        events += mon.process_frame(json.dumps(frame(t, [person(INSIDE)])))
    assert len(events) == 1


def test_malformed_object_is_skipped(cfg):
    mon = ZoneMonitor(cfg)
    bad = [{"class": "person", "confidence": "high", "bbox": INSIDE},
           {"class": "person", "confidence": 0.9, "bbox": [1, 2]},
           "not a dict"]
    events = []
    for t in range(0, 2001, 200):
        events += mon.process_frame(frame(t, bad + [person(INSIDE)]))
    assert len(events) == 1


def test_missing_confidence_treated_as_confident(cfg):
    obj = {"class": "person", "bbox": INSIDE}
    assert len(run(ZoneMonitor(cfg), [obj], 2000)) == 1
