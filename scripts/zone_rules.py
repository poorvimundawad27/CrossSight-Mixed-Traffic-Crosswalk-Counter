"""Restricted-zone safety rules.

Preferred input per frame:
    {"timestamp": ISO-8601, "objects": [{"class": "person", "confidence": 0.94, "bbox": [x1, y1, x2, y2]}]}

An adapter at the top of this file also accepts common variations:
  * objects under "detections" / "predictions" / "boxes"
  * class under "label" / "class_name" / "name" / "class_id", any capitalization,
    numeric ids mapped through config "class_map" (default {"0": "person"})
  * confidence under "score" / "conf"
  * bbox as [x1,y1,x2,y2], [x,y,w,h] (config "bbox_format": "xywh"), or a dict
    with x1/y1/x2/y2, xmin/ymin/xmax/ymax, left/top/width/height, or x/y/w/h
  * timestamp as ISO string, epoch seconds/ms/ns (config "timestamp_unit": auto|s|ms|ns),
    or a frame number ("frame", "frame_number", ...) converted with config "fps" (default 30)
  * no timestamp at all: the current clock time is used

Output: events appended (one JSON per line) to the file named in config["output_file"].
"""
import json
from datetime import datetime, timedelta, timezone

from shapely.geometry import Polygon, box

DEFAULTS = {
    "bbox_format": "xyxy",          # or "xywh" for list boxes
    "class_map": {"0": "person"},   # numeric class id -> name
    "fps": 30,                      # used when only a frame number is given
    "timestamp_unit": "auto",       # auto | s | ms | ns for numeric timestamps
}

_FRAME_EPOCH = datetime(2000, 1, 1, tzinfo=timezone.utc)


def load_config(path="config.json"):
    with open(path) as f:
        return json.load(f)


# ----------------------------------------------------------------- adapter ---

def _first(d, keys, default=None):
    """Return the value of the first key present (and not None) in dict d."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _num(v):
    """float -> int when it is a whole number, so 80.0 prints as 80."""
    v = float(v)
    return int(v) if v.is_integer() else v


def _parse_timestamp(value, unit="auto"):
    """ISO string, epoch number or numeric string -> datetime, or None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        s = value.strip()
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            try:
                value = float(s)
            except ValueError:
                return None
    if isinstance(value, (int, float)):
        v = float(value)
        if unit == "auto":
            div = 1e9 if v > 1e17 else 1e3 if v > 1e11 else 1.0
        else:
            div = {"s": 1.0, "ms": 1e3, "ns": 1e9}.get(unit, 1.0)
        try:
            return datetime.fromtimestamp(v / div, tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _bbox_xyxy(obj, bbox_format):
    """Return [x1, y1, x2, y2] (corners) or None if the box can't be read."""
    b = _first(obj, ["bbox", "box", "bounding_box", "rect"])
    if b is None:
        b = obj  # maybe the coordinates sit directly on the object
    try:
        if isinstance(b, dict):
            if all(k in b for k in ("x1", "y1", "x2", "y2")):
                x1, y1, x2, y2 = b["x1"], b["y1"], b["x2"], b["y2"]
            elif all(k in b for k in ("xmin", "ymin", "xmax", "ymax")):
                x1, y1, x2, y2 = b["xmin"], b["ymin"], b["xmax"], b["ymax"]
            elif all(k in b for k in ("left", "top", "width", "height")):
                x1, y1 = b["left"], b["top"]
                x2, y2 = x1 + b["width"], y1 + b["height"]
            elif all(k in b for k in ("x", "y", "w", "h")):
                x1, y1 = b["x"], b["y"]
                x2, y2 = x1 + b["w"], y1 + b["h"]
            elif all(k in b for k in ("x", "y", "width", "height")):
                x1, y1 = b["x"], b["y"]
                x2, y2 = x1 + b["width"], y1 + b["height"]
            else:
                return None
        else:
            a, b2, c, d = b
            if bbox_format == "xywh":
                x1, y1, x2, y2 = a, b2, a + c, b2 + d
            else:
                x1, y1, x2, y2 = a, b2, c, d
        x1, y1, x2, y2 = float(x1), float(y1), float(x2), float(y2)
    except (TypeError, ValueError, KeyError):
        return None
    lo_x, hi_x = sorted((x1, x2))
    lo_y, hi_y = sorted((y1, y2))
    return [_num(lo_x), _num(lo_y), _num(hi_x), _num(hi_y)]


# ----------------------------------------------------------------- monitor ---

class ZoneMonitor:
    def __init__(self, cfg):
        self.cfg = {**DEFAULTS, **cfg}
        self.zone = Polygon(self.cfg["polygon"])
        self.target = str(self.cfg["target_class"]).strip().lower()
        self.inside_since = None   # when the zone first became occupied
        self.last_alert = None     # when we last raised an alert

    # --- adapter pieces ---
    def _frame_time(self, meta):
        """Return (datetime, timestamp string for the event)."""
        raw = _first(meta, ["timestamp", "time", "ts", "pts"])
        t = _parse_timestamp(raw, self.cfg["timestamp_unit"])
        if t is not None:
            return t, (raw if isinstance(raw, str) and "T" in raw else t.isoformat())
        frame_no = _first(meta, ["frame", "frame_number", "frame_id", "frame_num"])
        if frame_no is not None:
            try:
                t = _FRAME_EPOCH + timedelta(seconds=float(frame_no) / float(self.cfg["fps"]))
                return t, t.isoformat()
            except (TypeError, ValueError, ZeroDivisionError):
                pass
        t = datetime.now(timezone.utc)
        return t, t.isoformat()

    def _class_name(self, obj):
        raw = _first(obj, ["class", "label", "class_name", "name", "class_id", "category"])
        if raw is None:
            return None
        s = str(raw).strip()
        return str(self.cfg["class_map"].get(s, s)).strip().lower()

    def _confidence(self, obj):
        raw = _first(obj, ["confidence", "score", "conf", "probability"])
        if raw is None:
            return 1.0   # detector gave no score: treat as fully confident
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _in_zone(self, bbox):
        x1, y1, x2, y2 = bbox
        return self.zone.intersects(box(x1, y1, x2, y2))

    def _hits(self, meta):
        """Person detections that are confident enough and overlap the zone."""
        objects = _first(meta, ["objects", "detections", "predictions", "boxes"], [])
        hits = []
        for o in objects:
            if not isinstance(o, dict):
                continue
            if self._class_name(o) != self.target:
                continue
            conf = self._confidence(o)
            if conf is None or conf < self.cfg["min_confidence"]:
                continue
            bbox = _bbox_xyxy(o, self.cfg["bbox_format"])
            if bbox is None or not self._in_zone(bbox):
                continue
            hits.append({"confidence": conf, "bbox": bbox})
        return hits

    # --- main entry point ---
    def process_frame(self, meta):
        """Takes one frame's metadata (dict or JSON string), returns a list of new events."""
        if isinstance(meta, (str, bytes)):
            meta = json.loads(meta)
        t, ts_text = self._frame_time(meta)
        hits = self._hits(meta)

        # Nobody in the zone: reset the timer
        if not hits:
            self.inside_since = None
            return []

        # Somebody in the zone: start the timer if it isn't running
        if self.inside_since is None:
            self.inside_since = t

        # Not there long enough yet (filters out one-frame flickers)
        if (t - self.inside_since).total_seconds() < self.cfg["persistence_seconds"]:
            return []

        # Too soon after the last alert (cooldown)
        if self.last_alert is not None and \
                (t - self.last_alert).total_seconds() < self.cfg["cooldown_seconds"]:
            return []

        self.last_alert = t
        best = max(hits, key=lambda h: h["confidence"])
        event = {
            "timestamp": ts_text,
            "event_type": "zone_intrusion",
            "zone": self.cfg["zone_id"],
            "confidence": best["confidence"],
            "bbox": best["bbox"],
            "status": "new",
        }
        with open(self.cfg["output_file"], "a") as f:
            f.write(json.dumps(event) + "\n")
        return [event]
