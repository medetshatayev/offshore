# Offshore Transaction Risk Detection System

An automated compliance tool that classifies banking transactions by offshore jurisdiction involvement. Built for Kazakhstani banks, it processes Excel files of incoming/outgoing transactions, runs each through an LLM-based analysis pipeline, and produces annotated Excel reports.

## Features

- **Multi-dimensional offshore detection** — evaluates entity addresses, bank HQ locations, entity HQ locations, country/citizenship codes, and address obfuscation patterns
- **LLM classification** — uses OpenAI GPT-5.1 (via internal REST gateway) with structured JSON output and web search tool to verify headquarter locations
- **High-value filtering** — processes only transactions ≥ 5,000,000 KZT
- **Payment status filtering** — automatically excludes rejected/deleted outgoing transactions
- **Batch processing** — groups transactions into batches of 10 with semaphore-controlled concurrency
- **Excel-native** — reads Cyrillic-header Excel files (`.xlsx`/`.xls`) and outputs annotated reports with a `Результат` column
- **Web interface** — single-page upload form with async job polling and download links
- **Privacy protection** — excludes physical person names from LLM analysis

## Quick Start

### Docker (recommended)

```bash
# 1. Create .env file
cat > .env << EOF
OPENAI_API_KEY=your_key_here
OPENAI_GATEWAY_URL=https://your-gateway-url
OPENAI_MODEL=gpt-5.1
EOF

# 2. Run
docker-compose up --build

# 3. Open http://localhost:8000
```

### Local

```bash
python -m venv venv
source venv/bin/activate   # Linux/Mac
# venv\Scripts\activate    # Windows
pip install -r requirements.txt
python main.py
```

## Configuration

All settings are managed via environment variables (or `.env` file).

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(required)* | API key for OpenAI gateway |
| `OPENAI_GATEWAY_URL` | *(required)* | Internal REST API gateway endpoint |
| `OPENAI_MODEL` | `gpt-5.1` | LLM model name |
| `OPENAI_TIMEOUT` | `60` | Request timeout in seconds |
| `AMOUNT_THRESHOLD_KZT` | `5000000` | Minimum transaction amount (KZT) |
| `MAX_CONCURRENT_LLM_CALLS` | `5` | Semaphore limit for parallel LLM requests (1–50) |
| `PORT` | `8000` | Server port |
| `HOST` | `0.0.0.0` | Server bind address |
| `LOG_LEVEL` | `INFO` | Logging level |
| `STORAGE_PATH` | `files` | Directory for processed output files |
| `DATABASE_PATH` | `offshore.db` | SQLite database with offshore jurisdiction list |

## API Endpoints

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/` | Web UI — file upload form |
| `GET` | `/health` | Health check (`{"status": "healthy"}`) |
| `POST` | `/process` | Upload incoming + outgoing Excel files, returns `job_id` |
| `GET` | `/status/{job_id}` | Poll processing status and results |
| `GET` | `/download/{filename}` | Download processed Excel report |

## Data Processing Pipeline

```
Upload (.xlsx/.xls)
  │
  ├─ Parse Excel ─── headers at row 6, skiprows=[0,1,2,3,4,6]
  │                  column name normalization (whitespace cleanup)
  │                  auto-detect engine: xlrd (.xls) / openpyxl (.xlsx)
  │
  ├─ Filter ──────── amount threshold: Сумма в тенге ≥ 5M KZT
  │                  payment status (outgoing only): exclude "Отказано в исполнении", "Удален"
  │
  ├─ Normalize ───── convert each row to flat dict with standardized keys
  │                  incoming: 37 source columns → ~30 normalized fields
  │                  outgoing: 27 source columns → ~15 normalized fields
  │
  ├─ Classify ────── batch into groups of 10
  │                  build system prompt (embeds offshore list from SQLite)
  │                  build user message (annotate banks → VERIFY HQ, companies → SEARCH HQ)
  │                  call LLM gateway with structured JSON output + web_search tool
  │                  validate response with Pydantic (up to 3 retries)
  │
  └─ Export ──────── append Результат column to original DataFrame
                     format: Итог | Уверенность | Объяснение | Источники
```

## Input File Format

Both incoming and outgoing Excel files must follow this structure:

| Row | Content |
|-----|---------|
| 1–5 | Metadata (skipped) |
| 6 | Column headers in Cyrillic |
| 7 | Column position numbers (skipped) |
| 8+ | Transaction data |

**Incoming transactions** — 37 columns including payer name/address, payer bank SWIFT/address/country, correspondent bank, intermediary banks (1–3), beneficiary info, payment details.

**Outgoing transactions** — 27 columns including recipient name/address, recipient bank SWIFT/address/country, payer (our client) info, payment details.

## Offshore Detection Criteria

The LLM evaluates each transaction across five dimensions:

| # | Dimension | Description |
|---|-----------|-------------|
| A | **Entity addresses** | Payer/recipient physical address, actual payer/recipient address, beneficiary address |
| B | **Bank branch addresses** | Payer/recipient bank address, correspondent bank address |
| C | **Bank HQ** *(web search)* | Registered headquarters of every bank (mandatory) |
| D | **Entity HQ** *(web search)* | Registered headquarters of every named company — best effort; failed lookup alone does not trigger SUSPECT |
| E | **Country codes** | Residence country and citizenship codes translated and matched against the offshore list |

Additional detection capabilities:
- **Address obfuscation** — detects fake Cyrillic country prefixes (e.g., `KAZAHSTAN`, `SOEDINENNYE SHTATY AMERIKI`) and Russian abbreviations in foreign addresses
- **Sub-national jurisdictions** — resolves US states (Wyoming, Delaware), territories of large countries that are individually offshore
- **Street name disambiguation** — avoids false positives like "Hong Kong East Road, Qingdao" (China, not Hong Kong)

### Classification Labels

| Label | Russian | Condition |
|-------|---------|-----------|
| `OFFSHORE_YES` | ОФШОР: ДА | Any address, bank HQ, entity HQ, or country code matches the offshore list |
| `OFFSHORE_NO` | ОФШОР: НЕТ | All resolvable locations are non-offshore (even if an entity HQ lookup failed) |
| `OFFSHORE_SUSPECT` | ОФШОР: ПОДОЗРЕНИЕ | Core location data (addresses, bank info, country codes) is missing or unresolvable |

## Project Structure

```
offshore-gateway/
├── main.py                    # Entry point — starts uvicorn server
├── app/
│   └── api.py                 # FastAPI routes, background job orchestration
├── core/
│   ├── config.py              # Pydantic Settings, environment variables
│   ├── db.py                  # SQLite wrapper for offshore jurisdiction list
│   ├── exceptions.py          # Domain exception hierarchy
│   ├── exporters.py           # Excel output with Результат column
│   ├── logger.py              # Structured logging with PII redaction
│   ├── normalize.py           # Amount cleaning, filtering, row normalization
│   ├── parsing.py             # Excel parsing with Cyrillic headers
│   └── schema.py              # Pydantic models for LLM I/O
├── llm/
│   ├── classify.py            # Batch classification with validation retries
│   ├── client.py              # REST client for OpenAI gateway (not SDK)
│   └── prompts.py             # System/user prompt construction
├── services/
│   └── transaction_service.py # Pipeline orchestration, concurrency control
├── templates/
│   └── index.html             # Single-page web UI
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## Docker Deployment

```bash
docker-compose up --build
```

**Volume mounts:**
- `./data` → `/app/data:ro` — read-only data directory (offshore jurisdiction database)
- Host file path → `/app/files` — persistent storage for processed output files

The Dockerfile includes corporate proxy configuration for pip. Adjust or remove the proxy settings in `Dockerfile` if deploying outside the corporate network.

## Development

```bash
# Run locally
python main.py

# Health check
curl http://localhost:8000/health
```

**Key development details:**
- Async/sync hybrid: FastAPI routes are `async`, LLM calls are synchronous (run via `loop.run_in_executor`)
- In-memory job storage — job state is not persisted across restarts
- LLM client uses NDJSON parsing, handles both standard OpenAI and custom gateway response formats
- Offshore jurisdiction list is embedded in the system prompt on every batch call from SQLite

## License

Internal use only. Not for public distribution.