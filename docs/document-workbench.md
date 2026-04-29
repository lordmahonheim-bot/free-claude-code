# C-f-C Document Workbench

The Document Workbench is a local-first utility for preparing files before analysis, synthesis, or future deliverable generation.

It reads source files from:

- workbench/inbox

It writes extracted text to:

- workbench/processing

It writes Markdown reports to:

- workbench/reports

The tool does not send files to external APIs.

## Supported inputs in V1.1

Text-like files:

- .txt, .md, .py, .js, .ts, .json, .csv, .html, .htm, .xml, .yaml, .yml

Document files:

- .pdf, .docx, .xlsx, .pptx

Images:

- .png, .jpg, .jpeg, .webp, .bmp, .gif, .tiff

Images are limited to technical metadata in V1.1.

Audio and video files are detected, but not transcribed in V1.1.

## Directory layout

- workbench/inbox: source files to process
- workbench/processing: extracted text files
- workbench/reports: Markdown reports
- workbench/output: reserved for future generated deliverables
- workbench/archive: reserved for future archiving

The workbench directory is ignored by Git, except for workbench/.gitignore.

## Commands

List files waiting in the inbox:

    uv run cfc-doc list

Process all files in the inbox:

    uv run cfc-doc process

Limit extracted text per file:

    uv run cfc-doc process --max-chars 20000

## Output per processed file

For each processed file, C-f-C writes:

- one extracted .txt file in workbench/processing
- one Markdown report in workbench/reports

Each report includes source path, detected type, file size, metadata, warnings, preview, and path to the complete extracted text.

## Safety notes

- .env files are skipped by design.
- Files remain local.
- OCR is not included in V1.1.
- Audio/video transcription is not included in V1.1.
- OCR, visual analysis, transcription, and document sub-agents belong to later roadmap stages.
