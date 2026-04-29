# C-f-C Document Workbench

The Document Workbench is a local-first utility for preparing files before analysis, synthesis, or deliverable generation.

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
- workbench/output: generated Markdown deliverables
- workbench/archive: reserved for future archiving

The workbench directory is ignored by Git, except for workbench/.gitignore.

## Commands

List files waiting in the inbox:

    uv run cfc-doc list

Process all files in the inbox:

    uv run cfc-doc process

Limit extracted text per file:

    uv run cfc-doc process --max-chars 20000

Generate a simple Markdown deliverable from extracted texts:

    uv run cfc-doc deliver

Limit preview size per processed text file in the deliverable:

    uv run cfc-doc deliver --max-chars 2000

## Output per processed file

For each processed file, C-f-C writes:

- one extracted .txt file in workbench/processing
- one Markdown report in workbench/reports

Each report includes source path, detected type, file size, metadata, warnings, preview, and path to the complete extracted text.

## V1.2 deliverables

The `deliver` command reads `.txt` files from `workbench/processing` and writes a Markdown deliverable into `workbench/output`.

The generated deliverable includes:

- generation date
- source file index
- extractive preview per file
- basic character statistics
- V1.2 limitations

This deliverable is local and extractive. It does not call an external model and does not perform advanced rewriting.

## Safety notes

- .env files are skipped by design.
- Files remain local.
- OCR is not included in V1.1.
- Audio/video transcription is not included in V1.1.
- OCR, visual analysis, transcription, AI synthesis, and document sub-agents belong to later roadmap stages.
