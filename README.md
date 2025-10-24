# Offshore Transaction Risk Detection System

This repository contains a production-ready Python application for detecting potential offshore jurisdiction involvement in banking transactions for Kazakhstani banks.

## 🎯 Project Overview

The system processes Excel files containing incoming and outgoing banking transactions, filters high-value transactions (≥ 5,000,000 KZT), performs offshore risk analysis using LLM-powered classification with structured output, and generates comprehensive reports.

## 🚀 Quick Start

```bash
cd offshore_risk
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your OpenAI API key
python main.py
```

Then open http://localhost:8000 in your browser.

## 📁 Project Structure

```
offshore_risk/
├── app/          # FastAPI web application
├── core/         # Core processing logic (parsing, matching, export)
├── llm/          # LLM integration (OpenAI with web_search)
├── data/         # Offshore jurisdictions list
├── templates/    # HTML web interface
└── main.py       # Application entry point
```

## 📚 Full Documentation

See [offshore_risk/README.md](offshore_risk/README.md) for complete documentation including:
- Detailed installation instructions
- Input file format specifications
- Configuration options
- API documentation
- Troubleshooting guide

## ✨ Key Features

- 📊 Excel processing with Cyrillic support
- 🔍 SWIFT/BIC country extraction
- 🎯 Fuzzy matching for offshore signals
- 🤖 LLM classification with structured output
- 🔎 Web search tool integration
- 📝 Comprehensive result reports
- 🚀 Modern web interface
- ⚡ Concurrent processing with rate limiting

## 🛡️ Security

- PII redaction in logs
- Configurable LLM endpoints
- Local processing (except LLM API)
- Audit trail logging

## 📄 License

Proprietary - Internal bank use only
