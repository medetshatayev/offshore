# Offshore Transaction Risk Detection System

A production-ready Python application for detecting potential offshore jurisdiction involvement in banking transactions for Kazakhstani banks.

## 🎯 Overview

This system processes Excel files containing incoming and outgoing banking transactions, filters high-value transactions (≥ 5,000,000 KZT), performs offshore risk analysis using LLM-powered classification, and generates comprehensive reports with an appended **"Результат"** column.

### Key Features

- 📊 **Excel Processing**: Handles Cyrillic headers, different skip rows for incoming/outgoing files, supports both .xlsx and .xls formats
- 🔍 **SWIFT Analysis**: Extracts country codes from BIC/SWIFT codes (positions 4-5)
- 🎯 **Fuzzy Matching**: Levenshtein-based matching for country codes, names, and cities against offshore list
- 🤖 **LLM Classification**: Uses OpenAI Responses API with structured output and integrated web_search tool
- 📝 **Detailed Reports**: Preserves all original columns, adds comprehensive "Результат" column with classification details
- 🚀 **Async Web Interface**: Modern FastAPI-based interface with background job processing and real-time status polling
- ⚡ **Concurrent Processing**: Configurable parallel LLM calls (default: 5) with asyncio semaphores
- 💾 **Persistent Jobs**: Web interface tracks active jobs across browser sessions using localStorage
- 🔒 **Security**: PII redaction in logs, path traversal protection, sandboxed file operations

## 📁 Project Structure

```
offshore_risk/
├── app/
│   ├── __init__.py
│   └── api.py                 # FastAPI routes, async job processing, endpoints
├── core/
│   ├── __init__.py
│   ├── parsing.py             # Excel parsing with Cyrillic support (.xlsx/.xls)
│   ├── normalize.py           # Amount cleaning, filtering, transaction normalization
│   ├── swift.py               # SWIFT/BIC extraction, country code mapping
│   ├── matching.py            # Levenshtein fuzzy matching (country, city)
│   ├── schema.py              # Pydantic models for validation and LLM responses
│   ├── exporters.py           # Excel export with formatted Результат column
│   └── logger.py              # Structured logging with PII redaction
├── llm/
│   ├── __init__.py
│   ├── prompts.py             # Dynamic prompt building, offshore table loading
│   ├── client.py              # OpenAI Responses API client with web_search
│   └── classify.py            # Per-transaction LLM classification with error handling
├── data/
│   └── offshore_countries.md  # 74 offshore jurisdictions (Russian/English/codes)
├── templates/
│   └── index.html             # Interactive web UI with job polling and localStorage
├── main.py                    # Application entry point
├── requirements.txt           # Python dependencies with versions
├── verify_setup.py            # Setup verification script
└── README.md                  # This file
```

## 🚀 Quick Start

### Prerequisites

- **Docker & Docker Compose** (recommended) or Python 3.12+
- OpenAI API key with access to GPT-4o or GPT-5 models

### Option 1: Docker (Recommended)

1. **Create environment file**:
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

2. **Build and run with Docker Compose**:
   ```bash
   docker-compose up --build
   ```

3. **Access the application**:
   Open `http://localhost:8000` in your browser

### Option 2: Local Python Installation

1. **Navigate to project directory**:
   ```bash
   cd offshore_risk
   ```

2. **Create virtual environment**:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

5. **Run the application**:
   ```bash
   python main.py
   ```

### Configuration

Edit `.env` file with your settings. All variables except `OPENAI_API_KEY` are optional:

| Variable                   | Default              | Description                                 |
|----------------------------|----------------------|---------------------------------------------|
| `OPENAI_API_KEY`           | *(required)*         | Your OpenAI API key                         |
| `OPENAI_MODEL`             | `gpt-4.1`            | Model to use (gpt-4.1, etc.)                |
| `OPENAI_TIMEOUT`           | `120`                | API timeout in seconds                      |
| `TEMP_STORAGE_PATH`        | `/tmp/offshore_risk` | Temporary file storage                      |
| `LOG_LEVEL`                | `INFO`               | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `MAX_CONCURRENT_LLM_CALLS` | `5`                  | Parallel LLM request limit                  |
| `AMOUNT_THRESHOLD_KZT`     | `5000000`            | Minimum transaction amount filter           |
| `FUZZY_MATCH_THRESHOLD`    | `0.8`                | Fuzzy matching threshold (0.0-1.0)          |
| `HOST`                     | `0.0.0.0`            | Server bind address                         |
| `PORT`                     | `8000`               | Server port                                 |

## 🐳 Docker Usage

### Building the Image

```bash
docker build -t offshore-risk .
```

### Running with Docker Compose

Start the application:
```bash
docker-compose up -d
```

View logs:
```bash
docker-compose logs -f
```

Stop the application:
```bash
docker-compose down
```

### Running with Docker

Run the container directly:
```bash
docker run -d \
  -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/app/data:ro \
  --name offshore-risk \
  offshore-risk
```

Access logs:
```bash
docker logs -f offshore-risk
```

Stop the container:
```bash
docker stop offshore-risk
docker rm offshore-risk
```

## 📊 Input File Formats

### Incoming Transactions File

- **Headers start at row 5** (use `skiprows=4` in pandas)
- **Required columns** (in Russian):
  - №п/п
  - Наименование бенефициара (наш клиент)
  - Категория клиента
  - Страна резидентства
  - Гражданство
  - Номер счета бенефициара
  - Дата валютирования
  - Дата приема
  - Сумма
  - **Сумма в тенге** (used for filtering)
  - Валюта платежа
  - Плательщик
  - SWIFT Банка плательщика
  - Город
  - Банк плательщика
  - Адрес банка плательщика
  - Состояние
  - Код страны
  - Страна отправителя

### Outgoing Transactions File

- **Headers start at row 6** (use `skiprows=5` in pandas)
- **Required columns** (in Russian):
  - №п/п
  - Наименование плательщика (наш клиент)
  - Категория клиента
  - Страна резидентства
  - Гражданство
  - Номер счета плательщика
  - Дата валютирования
  - Дата приема
  - Сумма
  - **Сумма в тенге** (used for filtering)
  - Валюта платежа
  - Получатель
  - SWIFT Банка получателя
  - Город
  - Банк получателя
  - Адрес банка получателя
  - Детали платежа
  - Состояние
  - Код страны
  - Страна получателя

**Note**: Files must be UTF-8 encoded Excel (.xlsx or .xls) to properly handle Cyrillic characters.

## 🔍 Processing Pipeline

The system processes transactions through the following stages:

1. **File Upload**: User uploads incoming and outgoing transaction files via web interface
2. **Background Job Creation**: System generates unique job ID and starts async processing
3. **Excel Parsing**: Read files with appropriate skip rows (4 for incoming, 5 for outgoing), handle Cyrillic headers
4. **Transaction Filtering**: Keep only transactions where `Сумма в тенге` ≥ 5,000,000 KZT
5. **Signal Extraction**:
   - Extract country code from SWIFT/BIC positions 4-5
   - Perform Levenshtein fuzzy matching on country codes, names, and cities
   - Aggregate all matching signals
6. **LLM Classification**: 
   - Call OpenAI Responses API with structured JSON schema
   - LLM can use web_search tool for verification when needed
   - Process transactions concurrently (default: 5 at a time)
   - Extract citations from web_search results
7. **Excel Export**: Generate output file with all original columns + formatted "Результат" column
8. **Status Polling**: Web interface polls job status every 2 seconds until completion
9. **Download**: User downloads processed files with classifications

## 📝 Output Format

### "Результат" Column Structure

The output column contains structured information in the following format:

```
Итог: {ОФШОР: ДА | ОФШОР: ПОДОЗРЕНИЕ | ОФШОР: НЕТ} | 
Уверенность: {0-100}% | 
Объяснение: {Brief reasoning in Russian} | 
Совпадения: {Matching signals with scores}
[| Источники: {URLs from web_search}]
```

**Note**: The "Источники" section is only included if the LLM used web_search for verification.

**Example without web search**:
```
Итог: ОФШОР: ДА | Уверенность: 95% | Объяснение: SWIFT код банка указывает на Каймановы острова, что является офшорной юрисдикцией. | Совпадения: SWIFT: KY; Страна: Cayman Islands (UK) (1.00)
```

**Example with web search**:
```
Итог: ОФШОР: ПОДОЗРЕНИЕ | Уверенность: 65% | Объяснение: Банк зарегистрирован в Панаме, возможны офшорные операции. | Совпадения: Страна: Panama (PA) (0.95); Город: Panama City (1.00) | Источники: https://swift.com/...; https://example.com/...
```

### Output Files

- `incoming_transactions_processed_YYYY-MM-DDTHH-MM-SS.xlsx`
  - Sheet name: "Входящие операции"
- `outgoing_transactions_processed_YYYY-MM-DDTHH-MM-SS.xlsx`
  - Sheet name: "Исходящие операции"

## 🧪 Classification Labels

- **OFFSHORE_YES** (ОФШОР: ДА): Clear evidence of offshore involvement
  - SWIFT country matches offshore list
  - Exact country code/name match
  - High confidence (typically 0.8-1.0)

- **OFFSHORE_SUSPECT** (ОФШОР: ПОДОЗРЕНИЕ): Partial indicators
  - Fuzzy matches with lower scores
  - Suspicious city but unclear country
  - Medium confidence (typically 0.4-0.7)

- **OFFSHORE_NO** (ОФШОР: НЕТ): No offshore indicators
  - No matches found
  - Country not on offshore list
  - Confidence varies based on data quality

## 🔧 API Endpoints

### GET `/`
Returns the interactive HTML upload interface with job tracking

**Response**: HTML page

### GET `/health`
Health check endpoint for monitoring

**Response**:
```json
{"status": "healthy", "service": "offshore_risk"}
```

### POST `/process`
Upload transaction files and start background processing

**Request**: `multipart/form-data`
- `incoming_file`: Excel file (.xlsx or .xls) with incoming transactions
- `outgoing_file`: Excel file (.xlsx or .xls) with outgoing transactions

**Response**: `202 Accepted`
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "accepted",
  "message": "Processing started. Use job_id to check status."
}
```

### GET `/status/{job_id}`
Check processing status for a job

**Response** (while processing):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "processing",
  "message": "Processing incoming transactions...",
  "created_at": "2024-10-30T12:34:56.789000"
}
```

**Response** (completed):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "message": "Processing completed successfully",
  "created_at": "2024-10-30T12:34:56.789000",
  "result": {
    "incoming": {
      "filename": "incoming_transactions_processed_2024-10-30T12-35-45.xlsx",
      "stats": {
        "total_rows": 1000,
        "filtered_count": 150,
        "processed_count": 150,
        "classifications": {
          "OFFSHORE_YES": 45,
          "OFFSHORE_SUSPECT": 30,
          "OFFSHORE_NO": 75
        }
      }
    },
    "outgoing": { /* same structure */ }
  }
}
```

**Response** (failed):
```json
{
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "message": "Processing failed: Invalid Excel format",
  "error": "Invalid Excel format: ...",
  "created_at": "2024-10-30T12:34:56.789000"
}
```

### GET `/download/{filename}`
Download a processed Excel file

**Parameters**:
- `filename`: Name of the file returned in job result

**Response**: Excel file download

**Security**: Path traversal protection, only allows downloading files from temp storage directory

## 🛡️ Security & Compliance

### Data Protection

- **PII Redaction**: Account numbers in logs show only last 4 digits
- **Local Processing**: All data processing happens locally on your server
- **Temporary Storage**: Uploaded files stored in `/tmp/offshore_risk` (configurable)
- **Automatic Cleanup**: Uploaded files deleted immediately after processing
- **No Data Persistence**: Transaction data not stored in database (by design)

### API Security

- **OpenAI API Only**: Only external API calls are to OpenAI (no other third parties)
- **Configurable Endpoint**: OpenAI endpoint fully configurable via environment variables
- **API Key Protection**: API key stored in `.env` file (not committed to git)
- **Timeout Controls**: Configurable timeouts prevent hanging requests

### Web Security

- **Path Traversal Protection**: Download endpoint validates filenames and paths
- **File Type Validation**: Only `.xlsx` and `.xls` files accepted for upload
- **Filename Sanitization**: Prevents directory traversal attacks (`..`, `/`, `\` blocked)
- **Sandboxed Downloads**: Files restricted to temp storage directory only

### Audit & Compliance

- **Comprehensive Logging**: All operations logged with timestamps
- **Error Tracking**: Failed transactions logged with error details
- **Classification Audit**: All LLM decisions logged with confidence scores
- **Source Citations**: Web search sources tracked for verification

### Production Recommendations

For production deployment, consider:
- Implement Redis/database for job persistence
- Add authentication and user management
- Enable HTTPS/TLS for web interface
- Set up rate limiting on API endpoints
- Implement role-based access control (RBAC)
- Regular security audits and penetration testing

## 🎓 LLM Integration Details

### OpenAI Responses API

The system uses **OpenAI's Responses API** (not Chat Completions API) which provides:
- Native integration with `web_search` tool (no manual function calling)
- Automatic citation extraction from search results
- Structured output enforcement through JSON schema
- Better handling of tool results

### System Prompt

The system prompt is dynamically constructed and includes:
- **Complete offshore jurisdictions table**: 77 jurisdictions loaded from `data/offshore_countries.md`
- **Analysis rules**: SWIFT priority, fuzzy matching guidelines, conservative classification approach
- **Classification labels**: OFFSHORE_YES, OFFSHORE_SUSPECT, OFFSHORE_NO with detailed criteria
- **Web search guidance**: When to use, what to search for, how to cite sources
- **JSON schema**: Embedded in the prompt to ensure structured responses

### Web Search Tool

The LLM is configured with the `web_search` tool and instructed to use it proactively when:
- **Ambiguous cases**: Signals are unclear or contradictory
- **Unknown banks**: Need to verify bank's actual country of domicile
- **Company verification**: Checking if counterparty has offshore connections
- **Address verification**: Validating if location suggests offshore activity
- **SWIFT conflicts**: SWIFT code indicates one country but other data suggests another
- **Suspicious patterns**: Entity names or addresses suggest possible offshore involvement

**Citation handling**:
- LLM is instructed to NEVER include placeholder text like "Нет источников"
- The system automatically extracts URL citations from web_search annotations
- Citations are merged into the `sources` array
- If no search is performed, `sources` is an empty array `[]`
- Up to 3 sources are displayed in the output, with a count of additional sources if more exist

### Structured Output

All LLM responses conform to a strict JSON schema validated by Pydantic:

```python
{
  "transaction_id": str,
  "direction": "incoming" | "outgoing",
  "amount_kzt": float,
  "signals": {
    "swift_country_code": str | null,
    "swift_country_name": str | null,
    "is_offshore_by_swift": bool | null,
    "country_code_match": {"value": str | null, "score": float | null},
    "country_name_match": {"value": str | null, "score": float | null},
    "city_match": {"value": str | null, "score": float | null}
  },
  "classification": {
    "label": "OFFSHORE_YES" | "OFFSHORE_SUSPECT" | "OFFSHORE_NO",
    "confidence": float  # 0.0 to 1.0
  },
  "reasoning_short_ru": str,  # 10-500 chars in Russian
  "sources": list[str],  # URLs only
  "llm_error": str | null
}
```

This ensures:
- **Type safety**: All fields have defined types
- **Required fields**: Missing fields cause validation errors
- **Confidence bounds**: Scores must be between 0.0 and 1.0
- **Valid enums**: Labels must be one of three predefined values
- **URL validation**: Sources must start with http:// or https://

### Error Handling

If LLM classification fails (timeout, invalid JSON, validation error):
- System creates an error response with `OFFSHORE_SUSPECT` label and 0% confidence
- Error details are logged but not exposed to end users in the output
- Transaction is still exported with error indicator in the "Результат" column

## 🗺️ Offshore Jurisdictions Data

### Data Source

The system uses a curated list of **77 offshore jurisdictions** stored in `data/offshore_countries.md`:

- **Format**: Markdown table with three columns:
  - `RUSNAME`: Russian name (e.g., "КАЙМАНОВЫ ОСТРОВА")
  - `CODE`: ISO 2-letter or extended code (e.g., "KY", "US-WY")
  - `ENGNAME`: English name (e.g., "CAYMAN ISLANDS (UK)")

- **Loading**: Table is dynamically loaded and embedded into the LLM system prompt
- **Coverage**: Includes classic offshore zones plus special economic zones
- **Examples**: 
  - Traditional: Cayman Islands, British Virgin Islands, Panama, Seychelles
  - Special zones: Wyoming (US-WY), Labuan (MY-15), Madeira (PT-30)
  - City-states: Monaco, Andorra, Gibraltar, San Marino

### Customization

To modify the offshore list:
1. Edit `data/offshore_countries.md`
2. Maintain the table format (markdown with `|` separators)
3. Ensure all codes match ISO 3166-1 alpha-2 standard (or extended codes)
4. Restart the application to reload the list

**Note**: Changes to this list will affect:
- SWIFT country matching
- Country code/name fuzzy matching
- LLM classification decisions

## 📊 Performance Considerations

- **Concurrent Processing**: 
  - Default: 5 concurrent LLM calls (controlled by asyncio semaphore)
  - Configurable via `MAX_CONCURRENT_LLM_CALLS` environment variable
  - Higher concurrency = faster processing but higher API rate usage
  
- **Processing Time**: 
  - Per transaction: ~2-5 seconds (depends on LLM response time and web_search usage)
  - Progress logged every 10 transactions
  - Web interface polls status every 2 seconds
  
- **Memory Usage**: 
  - Base application: ~100-150MB
  - Per 1000 transactions: ~1-2MB additional
  - Temporary Excel files stored on disk, not in memory
  
- **Batch Size Recommendations**: 
  - **Small** (< 100 transactions): ~2-10 minutes total
  - **Medium** (100-500 transactions): ~10-40 minutes total
  - **Large** (500-1000 transactions): ~40-90 minutes total
  - **Very Large** (> 1000): Consider splitting into multiple jobs
  
- **Network Requirements**:
  - Reliable internet connection for OpenAI API calls
  - Retry logic with exponential backoff (3 attempts per transaction)
  - Timeout: 60 seconds per LLM call (configurable)

- **Background Processing**:
  - Jobs run asynchronously - users can close browser and check back later
  - Job state persisted in memory (use Redis/database for production)
  - Uploaded files cleaned up automatically after processing

## 🧪 Testing

To test the system:

1. Prepare sample Excel files matching the format specifications
2. Ensure at least some transactions are ≥ 5,000,000 KZT
3. Upload via web interface
4. Check logs for processing details
5. Download and verify output files have "Результат" column

## 🐛 Troubleshooting

### Common Issues

**Issue**: "OPENAI_API_KEY environment variable not set"
- **Solution**: Create a `.env` file in the project root and add `OPENAI_API_KEY=your_key_here`
- **Check**: Run `python verify_setup.py` to verify configuration

**Issue**: "Invalid Excel format" or "File contains no data"
- **Solution**: Ensure files have correct skip rows (4 for incoming, 5 for outgoing)
- **Check**: Verify files contain Cyrillic headers and are UTF-8 encoded
- **Formats**: Both `.xlsx` and `.xls` formats are supported

**Issue**: "No transactions meet threshold"
- **Solution**: Check that some transactions have `Сумма в тенге` ≥ 5,000,000 KZT
- **Check**: Verify the column name is exactly "Сумма в тенге" (Cyrillic)

**Issue**: "LLM timeout errors" or "Rate limit exceeded"
- **Solution 1**: Increase `OPENAI_TIMEOUT` in `.env` (default: 60 seconds)
- **Solution 2**: Reduce `MAX_CONCURRENT_LLM_CALLS` (try 3 or 2 instead of 5)
- **Solution 3**: Check your OpenAI API tier and rate limits

**Issue**: "Missing columns" warnings in logs
- **Solution**: Verify Excel files have all required columns with exact Russian names
- **Check**: See "Input File Formats" section for complete column lists

**Issue**: "Job not found" when checking status
- **Solution**: Jobs are stored in memory and cleared after retrieval
- **Note**: In production, implement Redis/database for persistent storage

**Issue**: Web interface shows "Processing..." but never completes
- **Solution**: Check server logs for errors
- **Check**: Ensure server process hasn't crashed
- **Debugging**: Open browser console (F12) to check for JavaScript errors

**Issue**: OpenAI API returns "Model not found" error
- **Solution**: Change `OPENAI_MODEL` to a model you have access to (e.g., `gpt-4o`)
- **Check**: Verify your API key has access to Responses API

### Logs

Check logs for detailed error information:
```bash
# Logs are written to stdout by default
# Increase verbosity with:
export LOG_LEVEL=DEBUG
python main.py

# Or in .env file:
LOG_LEVEL=DEBUG
```

**Log Features**:
- PII redaction (account numbers show only last 4 digits)
- Transaction processing progress (every 10 transactions)
- Detailed error tracing with stack traces
- LLM request/response details in DEBUG mode

## 📚 Dependencies

Core dependencies (see `requirements.txt` for exact versions):

- **Web Framework**:
  - `fastapi==0.120.0` - Async web framework
  - `uvicorn[standard]==0.38.0` - ASGI server
  - `Jinja2==3.1.6` - Template rendering
  - `python-multipart==0.0.20` - File upload support
  
- **Data Processing**:
  - `pandas==2.3.3` - DataFrame operations
  - `openpyxl==3.1.5` - Excel .xlsx reading/writing
  - `xlsxwriter==3.2.9` - Enhanced Excel output formatting
  - `xlrd==2.0.1` - Legacy .xls file support
  
- **LLM & AI**:
  - `openai==2.6.0` - OpenAI Responses API client
  - `pydantic==2.12.3` - Data validation and schema enforcement
  
- **Text Processing**:
  - `python-Levenshtein==0.27.1` - Fast fuzzy string matching
  
- **Utilities**:
  - `tenacity==9.1.2` - Retry logic with exponential backoff
  - `python-dotenv==1.1.1` - Environment variable management
  - `aiofiles==25.1.0` - Async file operations

**Python Version**: 3.12+ (tested on 3.12)

## 🌐 Web Interface Features

The web interface (`templates/index.html`) provides:

- **Modern, Responsive Design**: Gradient theme with smooth animations
- **Drag-and-Drop Upload**: Visual file selection for incoming/outgoing files
- **Real-Time Status Updates**: Polls job status every 2 seconds
- **Progress Messages**: Shows current processing stage (parsing, filtering, LLM classification)
- **Persistent Job Tracking**: Uses localStorage to resume tracking if browser is closed
- **Automatic Resume**: Checks for active jobs on page load and resumes polling
- **Download Links**: Direct download of processed Excel files upon completion
- **Statistics Display**: Shows classification breakdown (OFFSHORE_YES/SUSPECT/NO counts)
- **Error Handling**: Clear error messages with details

## 🔄 Future Enhancements

Potential improvements for production deployment:

- [ ] **Redis/Database for Job State**: Replace in-memory job storage with persistent storage
- [ ] **WebSocket Updates**: Real-time progress updates without polling
- [ ] **Batch API Support**: Use OpenAI Batch API for cost reduction on large datasets
- [ ] **Audit Database**: Store all transactions and classifications for compliance
- [ ] **PDF Report Generation**: Export findings to PDF with charts
- [ ] **Multi-User Support**: Authentication and user-specific job tracking
- [ ] **Custom Offshore Lists**: Allow banks to configure their own jurisdiction lists
- [ ] **Advanced Analytics**: Dashboard with trends, statistics, and visualizations
- [ ] **API Integration**: REST API for integration with bank core systems
- [ ] **Email Notifications**: Alert users when processing completes
- [ ] **Rate Limiting**: Protect API with request throttling
- [ ] **Caching**: Cache LLM responses for identical transactions
