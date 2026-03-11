# Offshore Risk Detection System - AI Agent Guide

## Architecture Overview

This repository contains a FastAPI application for offshore-risk screening of banking transactions for Kazakhstani bank workflows. The current implementation classifies transactions through the OpenAI Responses API, exports annotated Excel files, and logs classification results to PostgreSQL.

Core runtime flow:
1. Upload paired incoming and outgoing Excel files.
2. Parse, validate, and filter each direction independently.
3. Normalize rows into transaction dictionaries.
4. Classify in LLM batches with shared concurrency limits.
5. Export results to Excel and log batches to PostgreSQL.

Primary boundaries:
- `app/api.py`: FastAPI routes, background job handling, in-memory job state, startup and shutdown hooks.
- `services/transaction_service.py`: end-to-end pipeline orchestration for one file.
- `core/`: configuration, parsing, normalization, export, databases, logging, schemas.
- `llm/`: prompt construction, Responses API client, batch classification.

## Current Application Behavior

The application currently does all of the following:

- Requires both an incoming file and an outgoing file in each `/process` request.
- Stores uploaded and generated files under `STORAGE_PATH`.
- Processes incoming and outgoing directions concurrently in a background task.
- Uses one shared `asyncio.Semaphore` so both directions compete for the same LLM concurrency budget.
- Runs blocking LLM calls inside a `ThreadPoolExecutor`.
- Allows a job to complete even if one direction fails and the other succeeds.
- Stores job state only in memory.

Job status values used by the API:
- `queued`
- `processing`
- `completed`
- `failed`

## Configuration

All settings come from `core/config.py` via `get_settings()`.

Required environment variables:
- `HOST`
- `PORT`
- `LOG_LEVEL`
- `ROOT_PATH`
- `OPENAI_API_KEY`
- `OPENAI_MODEL`
- `OPENAI_TIMEOUT`
- `AMOUNT_THRESHOLD_KZT`
- `MAX_CONCURRENT_LLM_CALLS`
- `STORAGE_PATH`
- `POSTGRES_HOST`
- `POSTGRES_PORT`
- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`

Optional settings with current defaults:
- `BATCH_SIZE=10`
- `DATABASE_PATH=offshore.db`
- `OPENAI_RESPONSES_URL=https://api.openai.com/v1/responses`
- `POSTGRES_MIN_POOL=2`
- `POSTGRES_MAX_POOL=10`

Validation rules implemented today:
- `PORT` must be in `1..65535`.
- `LOG_LEVEL` must be one of `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`.
- `MAX_CONCURRENT_LLM_CALLS` must be in `1..50`.
- `BATCH_SIZE` must be in `1..20`.

## File Formats

Both incoming and outgoing Excel files are parsed with:
- headers at row 6
- `skiprows=[0,1,2,3,4,6]`
- row 7 treated as the column-number row and skipped

Parser behavior:
- `.xls` uses `xlrd`
- `.xlsx` uses `openpyxl`
- column names are normalized by trimming and collapsing repeated spaces
- fully empty rows are dropped
- missing expected columns produce warnings, not immediate failure

Expected column sets are defined in `core/parsing.py`.

Key normalization behavior in `core/normalize.py`:
- `clean_amount_kzt()` strips spaces, commas, non-breaking spaces, and non-numeric suffixes.
- Negative amounts are converted to absolute values.
- Invalid or empty amount values become `None`.
- Outgoing payment status filtering excludes `Отказано в исполнении` and `Удален`.

## LLM Integration

The current LLM integration uses a custom REST client in `llm/client.py`, not the official OpenAI SDK.

Implemented behavior:
- Sends requests to the OpenAI Responses API with bearer auth.
- Uses persistent `requests.Session` connection pooling.
- Enables the `web_search` tool.
- Requests strict `json_schema` output.
- Parses standard Responses API output items.
- Retries request failures with tenacity.
- Retries schema validation failures up to 3 times in `classify_batch()`.

Current classification schema:
- `transaction_id`
- `classification.label`
- `classification.confidence`
- `reasoning_short_ru`
- `sources`

Local post-processing adds or normalizes:
- `direction`
- `amount_kzt`
- fallback `OFFSHORE_SUSPECT` error responses when the LLM call fails or omits an item

## Prompt Behavior

The current prompt in `llm/prompts.py` instructs the model to evaluate:
- entity addresses
- bank branch addresses
- bank headquarters via web search
- entity headquarters via best-effort web search
- country and citizenship codes
- address obfuscation
- partial-offshore jurisdictions
- suspicious offshore-name mentions in text
- a mandatory auto-offshore entity list

Important prompt implementation details:
- The offshore jurisdiction list is loaded from SQLite through `core/db.py`.
- `build_system_prompt()` is cached with `lru_cache(maxsize=1)`.
- Changes to the SQLite country list do not automatically refresh the cached prompt inside a running process.
- The user message marks certain entities with `→ VERIFY HQ LOCATION` or `→ SEARCH COMPANY HQ BY NAME` instructions.
- Physical-person workflows are partially protected by prompt rules, but `normalize_transaction()` still includes person-related address fields and metadata; avoid documenting stronger privacy guarantees than the code actually enforces.

## Databases

Two separate datastores exist in the current implementation.

### SQLite reference data

`core/db.py` manages the offshore-country reference list in table `countries`:

```sql
CREATE TABLE countries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

Use cases:
- `get_all_countries()` returns the list for prompt embedding.
- `add_country()` inserts with `INSERT OR IGNORE`.
- `init_db()` creates the table if needed.

### PostgreSQL transaction logging

`core/pg.py` and `core/pg_logger.py` manage PostgreSQL logging.

Current startup behavior:
- app startup tries to initialize the PostgreSQL pool
- app startup tries to ensure the `transaction_logs` table and indexes exist
- if initialization fails, the app logs the error and continues without batch logging

The `transaction_logs` table stores:
- `job_id`
- `direction`
- `transaction_id`
- `amount_kzt`
- `currency`
- `classification`
- `confidence`
- `reasoning_ru`
- `sources`
- `llm_error`
- `raw_transaction`
- `result_text`
- `original_filename`
- `created_at`

## Export Behavior

Exports are created in `core/exporters.py`.

Current behavior:
- preserves the filtered source rows
- appends a `Результат` column
- writes `.xlsx` output with `xlsxwriter`
- formats BIN and IIN columns as text
- wraps text in the `Результат` column

Current `Результат` format:
- `Итог: {label_ru} | Уверенность: {conf}% | Объяснение: {reasoning}`
- adds `| Источники: ...` when sources are present
- adds `| ОШИБКА: ...` when `llm_error` is present

Current output filenames are generated as:
- `incoming_transactions_processed_{timestamp}.xlsx`
- `outgoing_transactions_processed_{timestamp}.xlsx`

Do not describe output filenames as preserving the original source filename; that is not what `create_output_filename()` does.

## API Surface

Current routes in `app/api.py`:
- `GET /` renders the upload page
- `GET /health` returns status, service name, and version
- `GET /favicon.ico` returns `204`
- `POST /process` validates file extensions, stores uploads, creates a job, and schedules background processing
- `GET /status/{job_id}` returns current job state and result metadata
- `GET /download/{filename}` downloads processed files with path-traversal checks

Implementation details worth preserving in future edits:
- `/process` only accepts `.xlsx` and `.xls`
- `/download/{filename}` rejects path traversal and non-Excel filenames
- `jobs` is a module-level dictionary, so restarts clear all job metadata

## Development Guidance

When changing this codebase, keep the documentation aligned with these current realities:

- PostgreSQL logging is part of the implementation, even though the app can continue without it after startup failure.
- The LLM client uses the standard OpenAI Responses API shape.
- Prompt behavior is extensive and includes web search, auto-offshore matching, and text-level suspicious-name detection.
- `build_system_prompt()` is cached, so prompt-source data changes may require a restart.
- Output filenames are timestamp-based and direction-based, not derived from the original filename.
- The API expects a paired-file workflow, not a single-file workflow.

## Testing And Debugging

Useful checks for this repository:
1. Start the app with `python main.py`.
2. Hit `/health` to verify configuration and routing.
3. Upload sample paired files through `/`.
4. Poll `/status/{job_id}` until completion.
5. Verify generated Excel files under `STORAGE_PATH`.
6. If PostgreSQL is enabled, verify rows in `transaction_logs`.

Common debugging directions:
- parsing issues: inspect the actual Excel header row and normalized column names
- no results after filtering: inspect `Сумма в тенге` and outgoing `Статус платежа`
- Responses API failures: inspect timeout, HTTP response body, and schema validation retries
- missing offshore matches: inspect SQLite country data and remember the prompt cache behavior