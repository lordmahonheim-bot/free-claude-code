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
