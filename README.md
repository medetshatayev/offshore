# Offshore Transaction Risk Detection System

FastAPI service for screening bank transactions for offshore jurisdiction involvement. The application accepts paired incoming and outgoing Excel files, filters and normalizes the transactions, classifies them through the OpenAI Responses API, exports annotated Excel reports, and logs classification results to PostgreSQL.

## Current Functionality

- Processes two files per job: one incoming transactions file and one outgoing transactions file.
- Accepts `.xlsx` and `.xls` Excel files with Cyrillic headers at row 6.
- Filters transactions by `Сумма в тенге >= AMOUNT_THRESHOLD_KZT`.
- Applies an additional outgoing-only status filter that excludes `Отказано в исполнении` and `Удален`.
- Normalizes transaction rows into a flat structure for LLM classification.
- Sends transactions to the LLM in batches of `BATCH_SIZE` with shared semaphore-based concurrency control.
- Uses a structured JSON response schema and validates LLM output with up to 3 retries on schema errors.
- Appends a `Результат` column to the filtered source data and writes separate output files for incoming and outgoing directions.
- Logs processed transaction batches to PostgreSQL when the pool initializes successfully.
- Serves a simple web UI, job-status polling endpoint, and file download endpoint.

## Processing Flow

```text
Upload incoming + outgoing Excel files
  -> save both files under STORAGE_PATH
  -> start background job
  -> parse Excel with headers at row 6 and skip rows [0,1,2,3,4,6]
  -> validate columns and collect parse stats
  -> filter by KZT threshold
  -> filter outgoing payment statuses
  -> normalize rows for LLM input
  -> classify in batches through the OpenAI Responses API
  -> log batch results to PostgreSQL
  -> export filtered rows with a Результат column
  -> expose result filenames through the status endpoint
```

## LLM Classification

The classification layer uses the configured `OPENAI_MODEL` through a custom REST client in `llm/client.py`.

- The request is sent to `OPENAI_RESPONSES_URL` with `web_search` enabled.
- The response is parsed from the standard Responses API format and validated against a strict JSON schema.
- The offshore jurisdiction list is loaded from SQLite and embedded into the system prompt.
- Transactions are classified into `OFFSHORE_YES`, `OFFSHORE_NO`, or `OFFSHORE_SUSPECT`.
- Failed or malformed LLM responses are converted into fallback `OFFSHORE_SUSPECT` results with an error marker.

The prompt currently instructs the model to evaluate:

- Entity addresses from transaction fields.
- Bank branch addresses from transaction fields.
- Bank headquarters via web search.
- Company headquarters via best-effort web search.
- Country and citizenship codes.
- Address obfuscation, partial-offshore jurisdictions, and suspicious offshore-name mentions in text.

## Input File Format

Both uploaded Excel files are expected to use this layout:

| Row | Content |
|-----|---------|
| 1-5 | Metadata, skipped during parsing |
| 6 | Column headers |
| 7 | Column numbers, skipped during parsing |
| 8+ | Transaction rows |

Parsing details:

- `.xlsx` files use `openpyxl`.
- `.xls` files use `xlrd`.
- Column names are normalized by trimming whitespace and collapsing repeated spaces.
- Completely empty rows are removed after import.

Expected source formats:

- Incoming file: the parser validates against the configured incoming-column set in `core/parsing.py`.
- Outgoing file: the parser validates against the configured outgoing-column set in `core/parsing.py`.

## Output Format

Each processed output file preserves the filtered source columns and appends a `Результат` column.

Current result format:

```text
Итог: {label_ru} | Уверенность: {confidence_percent}% | Объяснение: {reasoning}[ | Источники: ...][ | ОШИБКА: ...]
```

Output filenames are generated as:

```text
incoming_transactions_processed_YYYY-MM-DDTHH-MM-SS.xlsx
outgoing_transactions_processed_YYYY-MM-DDTHH-MM-SS.xlsx
```

## API

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | HTML upload page |
| `GET` | `/health` | Service health response |
| `GET` | `/favicon.ico` | Empty `204` response |
| `POST` | `/process` | Upload both Excel files and create a background job |
| `GET` | `/status/{job_id}` | Return job status and result metadata |
| `GET` | `/download/{filename}` | Download a processed Excel file |

Job behavior:

- Jobs are stored in memory and are lost on restart.
- Each job runs incoming and outgoing processing concurrently.
- Both directions share the same LLM concurrency budget.
- A job can complete with one direction successful and the other failed.

## Configuration

Settings are loaded from environment variables or `.env` through `core/config.py`.

Required settings:

| Variable | Description |
|----------|-------------|
| `HOST` | Server bind host |
| `PORT` | Server port |
| `LOG_LEVEL` | Logging level |
| `ROOT_PATH` | FastAPI root path and UI base path |
| `OPENAI_API_KEY` | API key for the OpenAI API |
| `OPENAI_MODEL` | Model name sent to the Responses API |
| `OPENAI_TIMEOUT` | Responses API request timeout in seconds |
| `AMOUNT_THRESHOLD_KZT` | Minimum KZT amount to process |
| `MAX_CONCURRENT_LLM_CALLS` | Shared LLM concurrency limit |
| `STORAGE_PATH` | Directory for uploaded and generated files |
| `POSTGRES_HOST` | PostgreSQL host |
| `POSTGRES_PORT` | PostgreSQL port |
| `POSTGRES_DB` | PostgreSQL database name |
| `POSTGRES_USER` | PostgreSQL user |
| `POSTGRES_PASSWORD` | PostgreSQL password |

Optional settings with defaults:

| Variable | Default |
|----------|---------|
| `BATCH_SIZE` | `10` |
| `DATABASE_PATH` | `offshore.db` |
| `OPENAI_RESPONSES_URL` | `https://api.openai.com/v1/responses` |
| `POSTGRES_MIN_POOL` | `2` |
| `POSTGRES_MAX_POOL` | `10` |

Notes:

- `MAX_CONCURRENT_LLM_CALLS` is validated to stay within `1..50`.
- `BATCH_SIZE` is validated to stay within `1..20`.
- `STORAGE_PATH` is created automatically if it does not exist.

## Datastores

The service uses two databases for different purposes.

### SQLite

SQLite stores the offshore jurisdiction reference list.

- Table: `countries`
- Access layer: `core/db.py`
- Usage: the list is loaded into the LLM system prompt

### PostgreSQL

PostgreSQL stores batch classification logs.

- Pool management: `core/pg.py`
- Batch logging: `core/pg_logger.py`
- Table: `transaction_logs`

Logged data includes:

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

If PostgreSQL initialization fails at startup, the app logs the error and continues without transaction logging.

## Run Locally

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

### Linux or macOS

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

The server starts with Uvicorn using the configured host and port.

## Docker

```bash
docker-compose up --build
```

The Docker setup builds the application image and uses the project configuration from `docker-compose.yml` and `Dockerfile`.

## Project Structure

```text
offshore-gateway/
|-- main.py
|-- app/
|   |-- api.py
|-- core/
|   |-- config.py
|   |-- db.py
|   |-- exceptions.py
|   |-- exporters.py
|   |-- logger.py
|   |-- normalize.py
|   |-- parsing.py
|   |-- pg.py
|   |-- pg_logger.py
|   |-- schema.py
|-- llm/
|   |-- classify.py
|   |-- client.py
|   |-- prompts.py
|-- services/
|   |-- transaction_service.py
|-- templates/
|   |-- index.html
|-- Dockerfile
|-- docker-compose.yml
|-- requirements.txt
```

## Development Notes

- FastAPI endpoints are async, while LLM calls run synchronously inside an executor.
- Output exports use `xlsxwriter` formatting, including wrapped text in the `Результат` column.
- BIN and IIN columns are explicitly written as text in generated Excel files.
- The health endpoint returns service metadata including version `1.0.0`.

## License

Internal use only.