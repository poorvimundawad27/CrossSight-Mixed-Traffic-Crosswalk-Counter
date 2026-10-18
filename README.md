# Safety rules module (Workplace Safety Sentinel, Member 2)

Checks whether a detected person is inside a restricted zone for long enough to matter, and writes a JSON incident.

## Setup
```
python -m pip install -r requirements.txt
```

## Run
- Tests: `python -m pytest -v`
- Demo with fake data: `python run_sample.py` (prints one `ALERT:` and creates `incidents.jsonl`)
- Delete `incidents.jsonl` before a real demo so the dashboard starts clean.

## Config (`config.json`)
| Key | Meaning |
|---|---|
| `zone_id` | Name of the zone, copied into each event |
| `polygon` | Zone corners in video pixel coordinates |
| `target_class` | Class name to watch (must match the pipeline's label) |
| `min_confidence` | Detections below this are ignored |
| `persistence_seconds` | Person must stay in the zone this long before an alert |
| `cooldown_seconds` | Minimum gap between alerts |
| `output_file` | JSON-lines file the events are appended to |

## Input (one frame)
```
{"timestamp": "ISO-8601", "objects": [{"class": "person", "confidence": 0.94, "bbox": [x1, y1, x2, y2]}]}
```

## Output (one line per event in `incidents.jsonl`)
```
{"timestamp": "...", "event_type": "zone_intrusion", "zone": "restricted_1", "confidence": 0.94, "bbox": [x1, y1, x2, y2], "status": "new"}
```

## Using it from the pipeline
```python
from zone_rules import ZoneMonitor, load_config
mon = ZoneMonitor(load_config())
events = mon.process_frame(frame_metadata)   # returns a list of new events
```
If PipeGen's real output uses different field names, bbox format or timestamps, convert them at the top of `process_frame`.

## Known limitation
Detections carry no person IDs, so the zone is treated as occupied or empty rather than tracking individuals.

## Format adapter (handles PipeGen output differences)
`zone_rules.py` accepts these variations without code changes:
- objects under `objects`, `detections`, `predictions` or `boxes`
- class under `class`, `label`, `class_name`, `name` or `class_id`, any capitalization; numeric ids are mapped by the optional config key `class_map` (default `{"0": "person"}`)
- confidence under `confidence`, `score` or `conf` (missing = treated as confident)
- boxes as `[x1,y1,x2,y2]`, `[x,y,w,h]` (set `"bbox_format": "xywh"` in config) or a dict with `x1/y1/x2/y2`, `xmin/ymin/xmax/ymax`, `left/top/width/height` or `x/y/w/h`
- timestamps as ISO text, epoch seconds/ms/ns (optional config `"timestamp_unit": "auto|s|ms|ns"`; use `"ns"` for small relative nanosecond values), or a frame number (`frame`, `frame_number`, ...) converted with config `"fps"` (default 30); with no timestamp the current clock is used
- one bad detection is skipped instead of crashing the frame
