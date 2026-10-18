# CrossSight – Mixed-Traffic Crosswalk Counter

## Project Overview

CrossSight is a computer vision project for analyzing mixed traffic at pedestrian crossings. The project processes video footage and produces an output video and metadata to help review crosswalk activity.

## Problem Statement

Pedestrian crossings can be difficult to monitor when pedestrians and vehicles share busy traffic areas. CrossSight aims to support the analysis of crossing activity through video processing and computer vision.

## Pipeline Overview

1. Provide the traffic or crosswalk video as input.
2. Process the video through the project's computer vision pipeline.
3. Apply the configured zone rules where applicable.
4. Generate the processed video and metadata.
5. Review the output to evaluate the results.

## Project Structure

- `docs/` – Project documentation and screenshots.
- `output/output.mp4` – Processed output video.
- `output/metadata.json` – Sample output metadata.
- `scripts/count_crossings.py` – Crossing-counting script.
- `scripts/zone_rules.py` – Zone-rule logic.
- `scripts/test_zone_rules.py` – Tests for zone rules.

## Model and Precision

The model name and measured precision should be documented here after checking the model used in the pipeline and its evaluation results. No unverified accuracy or precision values are reported.

## Results

The repository includes an output video and metadata file for reviewing the project's results. Add measured crossing counts, evaluation metrics, and benchmark or latency results when these are available.

## Limitations

- Performance may vary with lighting, camera angle, video quality, occlusion, and traffic density.
- Counting accuracy should be evaluated against manually verified results.
- The reliability of results depends on the input video and the pipeline configuration.

## How to Run

1. Clone or download this repository.
2. Install the dependencies required by the project.
3. Follow the actual pipeline and script instructions for processing the input video.
4. Review `output/output.mp4` and `output/metadata.json`.

Use the Python scripts in the `scripts/` directory according to their input requirements and configuration.

## Documentation and Evidence

The `docs/` directory should contain the available project evidence, including the pipeline graph, benchmark and latency results, run screenshot, and compile card.

## Export Note

PipeGen export verification reportedly failed because of absolute paths in `pipeline.sh`, so the project was packaged manually.

