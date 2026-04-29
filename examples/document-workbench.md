# Document Workbench Examples

## Example 1 — List files waiting in the inbox

From the project root:

    uv run cfc-doc list

## Example 2 — Process all inbox files

Put files in:

    /home/lord-mahonheim/projects/free-claude-code/workbench/inbox

Then run:

    cd /home/lord-mahonheim/projects/free-claude-code && uv run cfc-doc process

## Example 3 — Limit extracted text size

Useful for large PDFs, DOCX, XLSX, or PPTX files:

    cd /home/lord-mahonheim/projects/free-claude-code && uv run cfc-doc process --max-chars 20000

## Example 4 — Read generated outputs

List Markdown reports:

    ls -la /home/lord-mahonheim/projects/free-claude-code/workbench/reports

List extracted text files:

    ls -la /home/lord-mahonheim/projects/free-claude-code/workbench/processing

## Example 5 — Manual cleanup for test files only

Only remove files intentionally created for tests:

    rm -f /home/lord-mahonheim/projects/free-claude-code/workbench/inbox/test_*
    rm -f /home/lord-mahonheim/projects/free-claude-code/workbench/processing/test_*
    rm -f /home/lord-mahonheim/projects/free-claude-code/workbench/reports/test_*
## Example 6 — Generate a Markdown deliverable

After processing files, generate a local Markdown deliverable from extracted text files:

    cd /home/lord-mahonheim/projects/free-claude-code && uv run cfc-doc deliver

The generated file is written to:

    /home/lord-mahonheim/projects/free-claude-code/workbench/output

## Example 7 — Limit deliverable preview size

For large extracted texts, limit the preview size per file:

    cd /home/lord-mahonheim/projects/free-claude-code && uv run cfc-doc deliver --max-chars 2000
