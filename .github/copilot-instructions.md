# Offshore Risk Detection System - AI Agent Guide

## Architecture Overview

This is a FastAPI application that processes banking transactions to detect offshore jurisdiction involvement for Kazakhstani banks. The system uses OpenAI GPT-4 for classification with structured output.

**Core Data Flow:**
1. Excel upload → Parsing (Cyrillic headers) → Filtering (≥5M KZT) → Normalization
2. Batch LLM classification (10 transactions/batch, semaphore-controlled concurrency)
3. Export to Excel with `Результат` column containing Russian-language analysis

**Service Boundaries:**
- `app/api.py`: FastAPI routes, background job orchestration, in-memory job storage
- `services/transaction_service.py`: Business logic, batch processing orchestration
- `core/`: Configuration, parsing, normalization, schema validation, export
- `llm/`: OpenAI client (REST API gateway), prompts, classification logic

## Critical File Formats

**Both incoming and outgoing transactions:** Excel with headers at row 6 (A6), skiprows=[0,1,2,3,4,6]
- **Incoming transactions:** 37 columns
- **Outgoing transactions:** 27 columns
- **Row 7 contains column numbers** (1-37 or 1-27) and is automatically skipped

All column headers are in **Russian/Cyrillic**. Key columns:

**Common to both:**
- `Сумма в тенге` (Amount in KZT) - requires normalization via `clean_amount_kzt()`
- `Валюта платежа` (Payment currency)
- `Дата валютирования` (Value date)

**Incoming-specific (37 columns total):**
- `Плательщик (Наименование)` - Payer name
- `Адрес плательщика` - **NEW: Payer physical address** (critical for offshore detection)
- `SWIFT код Банка плательщика` - Payer bank SWIFT
- `Адрес банка плательщика` - Payer bank address
- `Страна банка плательщика` - **NEW: Payer bank country** (critical for combining with address)
- `SWIFT код Корреспондента Банка Плательщика(отправителя)` - **NEW: Correspondent bank** (evaluated as 3rd address)
- `Банк-посредник отправителя 1/2/3` - **NEW: Intermediary banks** (context only)

**Outgoing-specific (27 columns total):**
- `Получатель` - Recipient name
- `Адрес получателя` - **NEW: Recipient physical address** (critical for offshore detection)
- `SWIFT Банка получателя` - Recipient bank SWIFT
- `Адрес банка получателя` - Recipient bank address
- `Страна банка` - **NEW: Recipient bank country** (critical for combining with address)

**Column name normalization:** System automatically trims whitespace and replaces multiple spaces with single space to handle formatting variations.

Output adds `Результат` column with format: `Итог: {label_ru} | Уверенность: {conf}% | Объяснение: {reasoning}`

## Configuration & Environment

All settings via Pydantic `Settings` class in `core/config.py`. Access with `get_settings()` singleton.

**Required env vars:**
- `OPENAI_API_KEY` - API key for OpenAI gateway
- `OPENAI_GATEWAY_URL` - Internal REST API gateway endpoint (not standard OpenAI URL)

**Key settings:**
- `AMOUNT_THRESHOLD_KZT=5000000` - Filter transactions below threshold
- `MAX_CONCURRENT_LLM_CALLS=5` - Semaphore limit for async batch processing
- Headers at row 6 (both directions) - `skiprows=[0,1,2,3,4,6]` in `parse_excel_file()`
  - Skips rows 1-5 (metadata) and row 7 (column numbers)

## LLM Integration Patterns

**Client:** Custom REST API wrapper (`llm/client.py`), NOT official OpenAI SDK. Uses:
- Direct `requests` calls to internal gateway with SSL verification disabled
- Tenacity retry decorator (3 attempts, exponential backoff)
- JSON extraction from markdown code blocks (`extract_json_from_text`)

**Structured Output:** Pydantic `BatchOffshoreRiskResponse` schema enforces:
- `results` array of `OffshoreRiskResponse` objects
- Classification: `OFFSHORE_YES | OFFSHORE_SUSPECT | OFFSHORE_NO`
- `reasoning_short_ru` (10-500 chars, Russian language)
- Validation retries: Up to 3 attempts on `ValidationError`

**Batch Processing:** `classify_batch()` processes 10 transactions per LLM call:
- Builds single prompt with numbered transaction list
- Returns array of responses mapped by `transaction_id`
- Semaphore controls concurrency via `asyncio.Semaphore(max_concurrent_llm_calls)`

## Data Normalization Rules

**Amount cleaning (`clean_amount_kzt`):**
- Removes spaces, commas, `\xa0` (non-breaking space)
- Strips currency suffixes like " KZT"
- Uses absolute value for negative amounts
- Returns `None` for invalid/missing values

**Privacy:** System intentionally excludes physical person names from LLM analysis (see `normalize_transaction()` in `core/normalize.py`) - only category/metadata sent.

**Outgoing payment status filtering (`filter_by_payment_status`):**
- Applied only to **outgoing** transactions, after amount threshold filtering
- Excludes rows where `Статус платежа` is "Отказано в исполнении" or "Удален" (case-insensitive, whitespace-normalized)
- If column `Статус платежа` is missing, logs warning and returns df unchanged
- Pipeline order: amount filter → status filter (outgoing only) → normalization → LLM

**Offshore Database:** Offshore jurisdiction list loaded from SQLite (`core/db.py`) and embedded in system prompt. List is government-provided, authoritative source.

## Offshore Database Schema

**SQLite Structure (`core/db.py`):**
```sql
CREATE TABLE countries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

**Key operations:**
- `get_all_countries()` - Returns sorted list of jurisdiction names for prompt embedding
- `add_country(name)` - Adds new jurisdiction with `INSERT OR IGNORE` (idempotent)
- `init_db()` - Creates table if not exists (safe to call repeatedly)

**Database location:** Set via `DATABASE_PATH` env var (default: `offshore.db`)  
**Data mount:** In Docker, map `/app/data` volume as read-only for production DB access

**Important:** List is embedded in LLM system prompt on every batch call - changes require app restart to take effect.

## Excel Parsing Edge Cases

**Common parsing issues and solutions:**

1. **Header row misalignment:**
   - **Symptom:** `Missing expected columns` warning
   - **Cause:** File has different header structure than expected
   - **Fix:** Verify `skiprows` value in `parse_excel_file()` - both directions use `[0,1,2,3,4,6]`
   - **Note:** Headers must be at row 6 (A6), row 7 contains column numbers and is skipped
   - **Debug:** Check logged "Available columns" vs expected column sets (37 for incoming, 27 for outgoing)

2. **Amount normalization failures:**
   - **Example:** `"5 000 000,00 KZT"` → removes spaces/commas/`\xa0`, strips " KZT" suffix
   - **Edge case:** Negative amounts → `abs()` applied with warning
   - **Returns `None` for:** Empty strings, non-numeric content, missing values
   - **Validation:** Logged at WARNING level for troubleshooting

3. **Old Excel format (.xls):**
   - Uses `xlrd` engine instead of `openpyxl`
   - Automatically detected by file extension
   - Example: `engine = "xlrd" if path.suffix.lower() == ".xls" else "openpyxl"`

4. **Cyrillic encoding issues:**
   - Files must use UTF-8 or Windows-1251 (pandas auto-detects)
   - Column names are case-sensitive and must match exactly
   - **Normalization applied:** System trims whitespace and replaces multiple spaces with single space
   - Handles variations like `"Адрес  получателя"` (double space) → `"Адрес получателя"` (single space)

5. **Empty rows/columns:**
   - `df.dropna(how="all")` removes completely empty rows
   - Missing optional columns logged as warnings, not errors
   - Required column: `Сумма в тенге` (raises `ValidationError` if missing)

## LLM Prompt Tuning & Classification Edge Cases

**Chain-of-thought prompting (`llm/prompts.py`):**
The system prompt enforces a 4-step analysis process:
1. **DECONSTRUCT** - Parse address into components
2. **RESOLVE** - Web search for State/Province + Country
3. **COMPARE** - Match against offshore list
4. **CLASSIFY** - Apply label logic

**Critical edge cases taught to LLM:**

1. **Street name ambiguity:**
   - ❌ "HONG KONG EAST ROAD, QINGDAO" → Misclassified as Hong Kong
   - ✅ Correctly parsed: Street name vs actual location (Qingdao, China)

2. **US state-level offshore jurisdictions:**
   - ❌ "123 Main St, Sheridan" → Classified as USA (non-offshore)
   - ✅ Correctly resolved: Sheridan, Wyoming → Wyoming is offshore jurisdiction
   - **Pattern:** Cities like Sheridan/Cheyenne require state resolution

3. **Multi-address evaluation:**
   - **Incoming:** Evaluate UP TO THREE addresses: (1) Payer address, (2) Payer bank address, (3) Correspondent bank address
   - **Outgoing:** Evaluate TWO addresses: (1) Recipient address, (2) Recipient bank address
   - If **ANY** address is offshore → `OFFSHORE_YES`
   - Bank addresses combine multiple fields: `Address + City + Bank Country + Country Code`
   - Example: Local company using offshore bank = `OFFSHORE_YES`

4. **Missing/incomplete addresses:**
   - Empty address field → `OFFSHORE_SUSPECT` (not `OFFSHORE_NO`)
   - Failed web search → `OFFSHORE_SUSPECT`
   - Never default to `OFFSHORE_NO` without confident location resolution

5. **Entity HQ search (company headquarters verification):**
   - For every named company (counterparty and our client when `client_category != "Физ"`), the LLM is instructed to search for the company’s registered head office address
   - Annotation `→ SEARCH COMPANY HQ BY NAME` is appended to company names in the user message, following the same pattern as `→ VERIFY HQ LOCATION` for banks
   - Both the transaction field address and the found HQ address are evaluated independently against the offshore list
   - If either is offshore → `OFFSHORE_YES`
   - Individual persons (`Физ` category) are excluded: their names are not sent to the LLM, so no HQ search occurs
   - **Failed HQ lookup ≠ SUSPECT**: If the company is too small/obscure to find online, but all other data (field addresses, bank addresses, country codes) clearly resolves to non-offshore → `OFFSHORE_NO`. `OFFSHORE_SUSPECT` is only for cases where core location data is missing/unresolvable.
   - Example: Company with field address in Kazakhstan but HQ in BVI → `OFFSHORE_YES`
   - Example: Small Kazakh company HQ not found, all addresses in Kazakhstan → `OFFSHORE_NO`

**Temperature & retries:**
- `temperature=0.1` (near-deterministic responses)
- 3 validation retries on `ValidationError` (malformed JSON)
- Batch size fixed at 10 for consistent quality

**Testing prompt changes:**
- Edit `build_system_prompt()` or `build_user_message()` in `llm/prompts.py`
- Restart app (prompts loaded at runtime, not cached)
- Monitor `reasoning_short_ru` field in output for quality assessment
- Check logs for validation retry counts (indicates prompt clarity issues)

## Development Workflows

**Run locally:**
```bash
python main.py  # Starts uvicorn on port 8000
```

**Docker deployment:**
```bash
docker-compose up --build
```
Note: Dockerfile includes corporate proxy configuration for pip (`headproxy03.fortebank.com:8080`)

**Volume mounts:** 
- `./files` → `/app/files` - persistent storage for processed files
- `./data` → `/app/data:ro` - read-only data directory (e.g., offshore DB)

## Error Handling Patterns

**Exceptions hierarchy (`core/exceptions.py`):**
- `OffshoreAppError` (base) → domain-specific errors with `details` dict
- `LLMError`, `ParsingError`, `ValidationError` - typed exceptions for each layer

**LLM failures:** On batch/transaction error, create fallback response via `create_error_response()` with `llm_error` field populated, ensuring output completeness.

**Validation retries:** `classify_batch()` retries up to 3x on Pydantic `ValidationError` (malformed LLM JSON).

## Key Conventions

- **Async/sync hybrid:** FastAPI routes are `async`, LLM calls are synchronous (run in executor via `loop.run_in_executor`)
- **Logging:** Use `setup_logger(__name__)` from `core/logger.py` - configured log levels via `LOG_LEVEL` env var
- **File naming:** `create_output_filename()` generates timestamped names: `{direction}_{original_name}_{timestamp}.xlsx`
- **Schema translation:** `LABEL_TRANSLATIONS` dict in `core/schema.py` maps English labels to Russian for user-facing output

## Testing & Debugging

No test suite currently exists in codebase. For manual testing:
1. Upload sample Excel files via web UI at `http://localhost:8000`
2. Check `/health` endpoint for service status
3. Monitor logs for batch processing progress (shows "Processed batch X/Y")
4. Inspect `files/` directory for output Excel files

**Common issues:**
- Excel parsing failures: Verify `skiprows` value matches actual header row
- LLM timeouts: Increase `OPENAI_TIMEOUT` (default 60s)
- Concurrency bottlenecks: Adjust `MAX_CONCURRENT_LLM_CALLS` based on API limits


[def]: ./llm/prompts.py)