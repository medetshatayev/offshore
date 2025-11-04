# Offshore Transaction Risk Detection System

A Python application for detecting potential offshore jurisdiction involvement in banking transactions for Kazakhstani banks.

## 🎯 Overview

This system processes Excel files containing banking transactions, filters high-value transactions (≥ 5,000,000 KZT), performs offshore risk analysis using LLM-powered classification, and generates reports with classification results.

### Key Features

- 📊 **Excel Processing**: Handles Cyrillic headers for incoming and outgoing transaction files
- 🔍 **SWIFT Analysis**: Extracts country codes from BIC/SWIFT codes
- 🤖 **LLM Classification**: Uses OpenAI with integrated web search for verification
- 📝 **Detailed Reports**: Preserves original columns and adds comprehensive "Результат" column
- 🚀 **Web Interface**: Modern FastAPI-based interface with background job processing
- ⚡ **Concurrent Processing**: Configurable parallel LLM calls (default: 5)
- 🔒 **Privacy**: Client names excluded for physical persons (Категория клиента = "Физ")

## 🚀 Quick Start

### Prerequisites

- Python 3.12+ or Docker
- OpenAI API key

### Using Docker (Recommended)

1. **Create `.env` file**:
   ```bash
   OPENAI_API_KEY=your_key_here
   OPENAI_MODEL=gpt-4o
   ```

2. **Run with Docker Compose**:
   ```bash
   docker-compose up --build
   ```

3. **Access**: Open `http://localhost:8000` in your browser

### Local Python Installation

1. **Install dependencies**:
   ```bash
   python -m venv venv
   source venv/bin/activate 
   pip install -r requirements.txt
   ```

2. **Configure environment**:
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenAI API key
   ```

3. **Run**:
   ```bash
   python main.py
   ```

## ⚙️ Configuration

Required environment variables:

| Variable                   | Default              | Description                          |
|----------------------------|----------------------|--------------------------------------|
| `OPENAI_API_KEY`           | *(required)*         | Your OpenAI API key                  |
| `OPENAI_MODEL`             | `gpt-4.1`            | Model to use                         |
| `MAX_CONCURRENT_LLM_CALLS` | `5`                  | Parallel LLM request limit           |
| `AMOUNT_THRESHOLD_KZT`     | `5000000`            | Minimum transaction amount filter    |
| `PORT`                     | `8000`               | Server port                          |

## 🔄 Recent Updates

### Code Refactoring (2025-11-04)

The codebase has been refactored for improved maintainability:

- **Service Layer**: Business logic extracted to `services/transaction_service.py`
- **Configuration**: Centralized, type-safe settings in `core/config.py`
- **Error Handling**: Custom exceptions with rich context in `core/exceptions.py`
- **Code Quality**: Added type hints, improved documentation, reduced API layer by 30%
- **Testing**: Test infrastructure with pytest, example unit tests in `tests/`

Run tests: `pytest`

### Simplified LLM Input

The system now sends **only essential data** to the LLM for classification:

**For All Transactions:**
1. Плательщик / Получатель (only if `Категория клиента != "Физ"`)
2. SWIFT банка
3. Город
4. Банк
5. **Адрес банка** (critical for location verification)
6. Код страны
7. Страна отправителя / получателя

**For Outgoing Only:**
8. **Детали платежа**

### Enhanced Special Cases Handling

The system explicitly handles sub-jurisdictions that are offshore zones within larger countries:

- **China (CN)** is NOT offshore, but **Macao (MO)** IS offshore
- **Spain (ES)** is NOT offshore, but **Canary Islands (ES-CN)** IS offshore
- **USA (US)** is NOT offshore, but **Wyoming (US-WY)** IS offshore
- **Malaysia (MY)** is NOT offshore, but **Labuan (MY-15)** IS offshore
- **Portugal (PT)** is NOT offshore, but **Madeira (PT-30)** IS offshore
- **Morocco (MA)** is NOT offshore, but **Tangier (MA-TNG)** IS offshore

**Key Improvement**: Bank address is now the primary indicator. If an address shows a mainland city (e.g., Beijing, Shanghai, Madrid), it's classified as NOT offshore even if there are name ambiguities.

## 📊 Input File Format

### Incoming Transactions

Headers start at **row 5** (skiprows=4). Required columns (Cyrillic):
- Плательщик
- SWIFT Банка плательщика
- Город
- Банк плательщика
- Адрес банка плательщика
- Код страны
- Страна отправителя
- Категория клиента
- Сумма в тенге *(used for filtering)*

### Outgoing Transactions

Headers start at **row 6** (skiprows=5). Required columns (Cyrillic):
- Получатель
- SWIFT Банка получателя
- Город
- Банк получателя
- Адрес банка получателя
- Код страны
- Страна получателя
- Детали платежа
- Категория клиента
- Сумма в тенге *(used for filtering)*

**File formats**: `.xlsx` or `.xls` with UTF-8 encoding

## 📝 Output Format

The system adds a **"Результат"** column with structured classification:

```
Итог: {ОФШОР: ДА | ОФШОР: ПОДОЗРЕНИЕ | ОФШОР: НЕТ} | 
Уверенность: {0-100}% | 
Объяснение: {Reasoning in Russian} | 
Совпадения: {Matching signals}
[| Источники: {URLs if web search used}]
```

**Example**:
```
Итог: ОФШОР: НЕТ | Уверенность: 90% | Объяснение: SWIFT код CN и адрес банка указывают на материковый Китай (BEIJING), не офшорная юрисдикция. | Совпадения: SWIFT: CN; Город: BEIJING
```

### Classification Labels

- **OFFSHORE_YES** (ОФШОР: ДА): Clear offshore involvement
  - Bank located in offshore jurisdiction from list
  - Confirmed by SWIFT code and/or address

- **OFFSHORE_SUSPECT** (ОФШОР: ПОДОЗРЕНИЕ): Ambiguous indicators
  - Some signals suggest offshore but evidence incomplete
  - Requires manual review

- **OFFSHORE_NO** (ОФШОР: НЕТ): No offshore indicators
  - Bank clearly not in offshore jurisdiction
  - Confirmed by address and SWIFT code

## 🔍 Classification Logic

### Priority Order

1. **Bank Address** (highest priority): Physical location shown in address field
2. **SWIFT Country Code**: Extracted from positions 4-5 of SWIFT/BIC code
3. **City and Country Fields**: Supporting information
4. **Web Search** (when needed): LLM can verify bank locations for ambiguous cases

### Offshore Jurisdictions List

The system references **69 offshore jurisdictions** from `data/offshore_countries.md`, including:
- Classic offshore zones: Cayman Islands, BVI, Panama, Seychelles
- Special economic zones: Wyoming (US-WY), Labuan (MY-15), Madeira (PT-30)
- Special administrative regions: Macao (MO)

### Web Search Integration

The LLM automatically uses web search to verify:
- Unknown or unfamiliar banks
- Conflicting signals (e.g., SWIFT vs. address)
- Ambiguous company names or addresses
- When more context would improve classification accuracy

## 🔧 API Endpoints

### Web Interface
- `GET /` - Upload interface with real-time job tracking

### Processing
- `POST /process` - Upload files, returns job_id
- `GET /status/{job_id}` - Check processing status
- `GET /download/{filename}` - Download processed files

### Health Check
- `GET /health` - Service health status

## 🐛 Troubleshooting

**"OPENAI_API_KEY not set"**
- Create `.env` file with your API key

**"Invalid Excel format"**
- Ensure correct skip rows (4 for incoming, 5 for outgoing)
- Verify Cyrillic headers are present

**"No transactions meet threshold"**
- Check that some transactions have Сумма в тенге ≥ 5,000,000 KZT

**"LLM timeout errors"**
- Increase `OPENAI_TIMEOUT` in `.env`
- Reduce `MAX_CONCURRENT_LLM_CALLS` to 3 or 2

**Processing takes too long**
- Normal: ~2-5 seconds per transaction
- For 100 transactions: ~10-25 minutes
- Reduce concurrent calls if experiencing rate limits

**Jobs lost after browser refresh**
- Jobs stored in memory (use Redis for production)
- Check server logs for processing status

## 📚 Key Dependencies

- `fastapi` - Web framework
- `pandas` & `openpyxl` - Excel processing
- `openai` - LLM classification
- `python-Levenshtein` - Fuzzy matching
- `pydantic` & `pydantic-settings` - Data validation and configuration
- `pytest` - Testing framework

See `requirements.txt` for complete list with versions.

## 📁 Project Structure

```
offshore/
├── app/
│   └── api.py              # FastAPI routes (HTTP layer only)
├── services/
│   └── transaction_service.py  # Business logic
├── core/
│   ├── config.py           # Centralized configuration
│   ├── exceptions.py       # Custom exception hierarchy
│   ├── parsing.py          # Excel parsing
│   ├── normalize.py        # Data cleaning and filtering
│   ├── swift.py            # SWIFT code handling
│   ├── matching.py         # Fuzzy matching
│   ├── schema.py           # Pydantic models
│   ├── exporters.py        # Excel export
│   └── logger.py           # Logging
├── llm/
│   ├── prompts.py          # Prompt building
│   ├── client.py           # OpenAI client
│   └── classify.py         # Transaction classification
├── tests/
│   ├── test_config.py      # Configuration tests
│   └── test_exceptions.py  # Exception tests
├── data/
│   └── offshore_countries.md  # Offshore jurisdictions list
├── templates/
│   └── index.html          # Web interface
├── main.py                 # Application entry point
├── requirements.txt        # Dependencies
└── docker-compose.yml      # Docker configuration
```

## 🔐 Security & Privacy

- **PII Protection**: Physical person names excluded from LLM input
- **Account Redaction**: Account numbers in logs show only last 4 digits
- **Local Processing**: All data processing happens on your server
- **Temporary Storage**: Files auto-deleted after processing
- **Path Protection**: Download endpoint validates file paths

## 📖 Usage Example

1. Open `http://localhost:8000`
2. Upload incoming transactions Excel file
3. Upload outgoing transactions Excel file
4. Click "Process Files"
5. Wait for processing (status updates automatically)
6. Download processed files with classifications

The output files will include all original columns plus the "Результат" column with offshore risk classifications.

## 📞 Support

For issues or questions:
1. Check logs: Set `LOG_LEVEL=DEBUG` in `.env`
2. Verify setup: Run `python verify_setup.py`
3. Review troubleshooting section above

## 📄 License

Internal use only. Not for public distribution.
