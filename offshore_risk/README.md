# Offshore Transaction Risk Detection System

A production-ready Python application for detecting potential offshore jurisdiction involvement in banking transactions for Kazakhstani banks.

## 🎯 Overview

This system processes Excel files containing incoming and outgoing banking transactions, filters high-value transactions (≥ 5,000,000 KZT), performs offshore risk analysis using LLM-powered classification, and generates comprehensive reports with an appended **"Результат"** column.

### Key Features

- 📊 **Excel Processing**: Handles Cyrillic headers, different skip rows for incoming/outgoing files
- 🔍 **SWIFT Analysis**: Extracts country codes from BIC/SWIFT codes
- 🎯 **Fuzzy Matching**: Simple, deterministic matching for country codes, names, and cities
- 🤖 **LLM Classification**: Uses OpenAI with structured output and web_search tool
- 📝 **Detailed Reports**: Preserves all original columns, adds comprehensive results column
- 🚀 **Web Interface**: Clean, modern FastAPI-based upload/download interface
- ⚡ **Concurrent Processing**: Configurable parallel LLM calls with rate limiting
- 🔒 **Security**: PII redaction, no external data leaks except to configured LLM

## 📁 Project Structure

```
offshore_risk/
├── app/
│   ├── __init__.py
│   └── api.py                 # FastAPI routes, main processing logic
├── core/
│   ├── __init__.py
│   ├── parsing.py             # Excel parsing with Cyrillic support
│   ├── normalize.py           # Amount cleaning, filtering, metadata
│   ├── swift.py               # SWIFT/BIC extraction, country mapping
│   ├── matching.py            # Fuzzy matching (country, city)
│   ├── schema.py              # Pydantic models for validation
│   ├── exporters.py           # Excel export with Результат column
│   └── logger.py              # Structured logging
├── llm/
│   ├── __init__.py
│   ├── prompts.py             # System/user prompts, offshore table loading
│   ├── client.py              # OpenAI client with web_search tool
│   └── classify.py            # Per-transaction classification
├── data/
│   └── offshore_countries.md  # Offshore jurisdictions list (embedded in prompts)
├── templates/
│   └── index.html             # Web UI upload form
├── main.py                    # Application entry point
├── requirements.txt           # Python dependencies
├── .env.example               # Environment variables template
└── README.md                  # This file
```

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- OpenAI API key with access to GPT-4 or later
- pip or conda for package management

### Installation

1. **Clone or download the project**:
   ```bash
   cd offshore_risk
   ```

2. **Create virtual environment** (recommended):
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

### Configuration

Edit `.env` file with your settings:

```bash
# Required
OPENAI_API_KEY=your_openai_api_key_here

# Optional (defaults shown)
OPENAI_MODEL=gpt-4o
OPENAI_TIMEOUT=120
TEMP_STORAGE_PATH=/tmp/offshore_risk
LOG_LEVEL=INFO
MAX_CONCURRENT_LLM_CALLS=5
AMOUNT_THRESHOLD_KZT=5000000
FUZZY_MATCH_THRESHOLD=0.80
```

### Running the Application

**Start the web server**:
```bash
python main.py
```

The application will start on `http://0.0.0.0:8000`

**Access the web interface**:
Open your browser and navigate to `http://localhost:8000`

## 📊 Input File Formats

### Incoming Transactions File

- **Headers start at row 5** (use `skiprows=4` in pandas)
- **Required columns** (in Russian):
  - №п/п
  - Наименование бенефициара
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
  - Страна получателя

### Outgoing Transactions File

- **Headers start at row 6** (use `skiprows=5` in pandas)
- **Required columns** (in Russian):
  - №п/п
  - Наименование плательщика
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

1. **Parse Excel**: Read files with correct skip rows, handle Cyrillic headers
2. **Filter**: Keep only transactions with `Сумма в тенге` ≥ 5,000,000 KZT
3. **Extract SWIFT**: Get country code from positions 4-5 of SWIFT/BIC code
4. **Fuzzy Match**: Simple matching for country code/name and city
5. **LLM Classify**: Call OpenAI with structured output, optional web_search
6. **Export**: Write Excel with all original columns + "Результат" column

## 📝 Output Format

### "Результат" Column Structure

```
Итог: {ОФШОР: ДА | ОФШОР: ПОДОЗРЕНИЕ | ОФШОР: НЕТ} | 
Уверенность: {0-100}% | 
Объяснение: {Brief reasoning in Russian} | 
Совпадения: {Matching signals with scores} | 
Источники: {URLs from web_search or "Нет источников"}
```

**Example**:
```
Итог: ОФШОР: ДА | Уверенность: 95% | Объяснение: SWIFT код банка указывает на Каймановы острова, что является офшорной юрисдикцией. | Совпадения: SWIFT: KY; Страна: Cayman Islands (KY) (1.00) | Источники: Нет источников
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
Returns HTML upload form

### GET `/health`
Health check endpoint
```json
{"status": "healthy", "service": "offshore_risk"}
```

### POST `/process`
Process transaction files

**Request**: multipart/form-data
- `incoming_file`: Excel file (incoming transactions)
- `outgoing_file`: Excel file (outgoing transactions)

**Response**:
```json
{
  "status": "success",
  "incoming": {
    "filename": "incoming_transactions_processed_2024-10-24T10-30-00.xlsx",
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
```

### GET `/download/{filename}`
Download processed file

## 🛡️ Security & Compliance

- **PII Protection**: Account numbers redacted in logs (only last 4 digits shown)
- **Local Processing**: All processing happens locally except LLM API calls
- **Configurable Endpoints**: LLM endpoint fully configurable
- **No External Uploads**: Bank data never uploaded to third parties (except OpenAI API)
- **Audit Trail**: Comprehensive logging with timestamps
- **Temp File Cleanup**: Uploaded files automatically removed after processing

## 🎓 LLM Integration Details

### System Prompt

The system prompt includes:
- Complete offshore jurisdictions table (Russian name, code, English name)
- Analysis rules and priorities
- Classification guidelines
- Web search tool usage instructions

### Web Search Tool

The LLM can use the `web_search` tool when it needs to:
- Verify a bank's country of domicile
- Look up SWIFT/BIC code information
- Check regulatory or sanctions lists
- Confirm offshore jurisdiction status

**Important**: The LLM is instructed to:
- Use web_search sparingly
- Cite all sources used
- Prefer authoritative sources
- Never include screenshots

### Structured Output

All LLM responses conform to a strict JSON schema validated by Pydantic. This ensures:
- Type safety
- Required fields are always present
- Confidence scores are 0.0-1.0
- Labels are valid enums
- Sources are valid URLs

## 📊 Performance Considerations

- **Concurrent Processing**: By default, 5 concurrent LLM calls (configurable)
- **Processing Time**: ~2-5 seconds per transaction (depends on LLM response time)
- **Memory Usage**: ~100MB base + ~1MB per 1000 transactions
- **Batch Recommendations**: 
  - Small batches: < 100 transactions, ~2-10 minutes
  - Medium batches: 100-500 transactions, ~10-40 minutes
  - Large batches: 500+ transactions, consider breaking into chunks

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
- **Solution**: Copy `.env.example` to `.env` and add your API key

**Issue**: "Invalid Excel format"
- **Solution**: Ensure files have correct skip rows and Cyrillic headers

**Issue**: "No transactions meet threshold"
- **Solution**: Check that some transactions have `Сумма в тенге` ≥ 5,000,000

**Issue**: "LLM timeout errors"
- **Solution**: Increase `OPENAI_TIMEOUT` in `.env` or reduce `MAX_CONCURRENT_LLM_CALLS`

**Issue**: "Missing columns" warnings
- **Solution**: Verify Excel files have all required columns in Russian

### Logs

Check logs for detailed error information:
```bash
# Logs are written to stdout
# Increase verbosity with:
export LOG_LEVEL=DEBUG
python main.py
```

## 📚 Dependencies

Core dependencies:
- `fastapi` - Web framework
- `pandas` - Excel processing
- `openpyxl` - Excel file handling
- `pydantic` - Data validation
- `openai` - LLM API client
- `python-Levenshtein` - Fuzzy string matching
- `tenacity` - Retry logic

See `requirements.txt` for complete list with versions.

## 🔄 Future Enhancements

Potential improvements:
- [ ] Batch LLM calls with OpenAI Batch API for cost reduction
- [ ] Progress indicator with WebSocket updates
- [ ] Database storage for audit history
- [ ] Export to PDF reports
- [ ] Multi-language support
- [ ] Advanced analytics dashboard
- [ ] Custom offshore jurisdiction lists per bank
- [ ] Integration with bank core systems

## 📄 License

This project is proprietary software for internal bank use. Unauthorized distribution is prohibited.

## 🤝 Support

For issues or questions, contact the development team or refer to internal documentation.

---

**Version**: 1.0.0  
**Last Updated**: 2024-10-24  
**Status**: Production Ready
