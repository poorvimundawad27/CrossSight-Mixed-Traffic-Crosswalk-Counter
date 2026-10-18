#!/usr/bin/env python3
"""
Turn PipeGen's metadata.json into per-class crossing counts.

Usage:
  python3 count_crossings.py metadata.json [--line-y 0.70] [--minute-bins]

Reads: frames[].objects[] with id, class_id, bbox{left,top,width,height}.
Writes: crossing_summary.json and crossing_events.csv next to the input file.

It prints sanity warnings first. If detections look invalid
(confidence > 1, mostly empty frames, full-frame boxes), fix the pipeline
before trusting any count.
"""
import argparse, csv, json, os
from collections import defaultdict

COCO = {0: "pedestrian", 1: "bicycle", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


def centre(b):
    return b["left"] + b["width"] / 2.0, b["top"] + b["height"] / 2.0


def inside(pt, b, pad=0.15):
    x, y = pt
    px, py = b["width"] * pad, b["height"] * pad
    return (b["left"] - px <= x <= b["left"] + b["width"] + px and
            b["top"] - py <= y <= b["top"] + b["height"] + py)


def sanity(frames):
    n = len(frames)
    empty = sum(1 for f in frames if not f.get("objects"))
    confs, full = [], 0
    for f in frames:
        W, H = f.get("width", 1), f.get("height", 1)
        for o in f.get("objects", []):
            confs.append(o.get("confidence", 0))
            b = o["bbox"]
            if b["width"] > 0.9 * W and b["height"] > 0.9 * H:
                full += 1
    warns = []
    if n and empty / n > 0.5:
        warns.append(f"{empty}/{n} frames have no objects")
    if confs and max(confs) > 1.0:
        warns.append(f"confidence up to {max(confs):.1f} (should be 0 to 1): output parser looks wrong")
    if full:
        warns.append(f"{full} full-frame boxes: likely a parsing error")
    return warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("metadata")
    ap.add_argument("--line-y", type=float, default=0.70,
                    help="horizontal counting line, fraction of frame height")
    args = ap.parse_args()

    data = json.load(open(args.metadata))
    frames = data["frames"]
    for w in sanity(frames):
        print("WARNING:", w)

    tracks = {}            # id -> dict(prev_y, cls)
    counts = defaultdict(lambda: {"down": 0, "up": 0})
    per_minute = defaultdict(lambda: defaultdict(int))
    events = []

    for f in frames:
        H = f.get("height", 1)
        line = args.line_y * H
        t_s = f.get("pts_ns", 0) / 1e9
        objs = f.get("objects", [])

        bikes = [o["bbox"] for o in objs if o.get("class_id") in (1, 3)]
        for o in objs:
            cid = o.get("class_id")
            if cid not in COCO:
                continue
            name = COCO[cid]
            c = centre(o["bbox"])
            # cyclist heuristic: person whose centre sits on a bicycle/motorcycle box
            if cid == 0 and any(inside(c, b) for b in bikes):
                name = "cyclist"
            if cid == 1:        # bicycle boxes are only used for the heuristic
                continue
            tid = o.get("id")
            prev = tracks.get(tid)
            if prev is not None:
                a, b_ = prev["y"], c[1]
                if a < line <= b_ or b_ < line <= a:
                    d = "down" if b_ > a else "up"
                    if prev["cls"] != "cyclist" and name != "cyclist":
                        use = name
                    else:
                        use = "cyclist"
                    counts[use][d] += 1
                    per_minute[int(t_s // 60)][use] += 1
                    events.append([round(t_s, 2), tid, use, d, f["frame"]])
            tracks[tid] = {"y": c[1], "cls": name}

    out_dir = os.path.dirname(os.path.abspath(args.metadata))
    summary = {
        "line_y_fraction": args.line_y,
        "counts_per_class": {k: dict(v, total=v["down"] + v["up"]) for k, v in counts.items()},
        "counts_per_minute": {str(m): dict(v) for m, v in sorted(per_minute.items())},
        "note": "Approximate. Dense traffic causes ID switches and missed objects.",
    }
    json.dump(summary, open(os.path.join(out_dir, "crossing_summary.json"), "w"), indent=2)
    with open(os.path.join(out_dir, "crossing_events.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["time_s", "track_id", "class", "direction", "frame"])
        w.writerows(events)

    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
