# Offshore Transaction Risk Detection System

A Python application for detecting potential offshore jurisdiction involvement in banking transactions for Kazakhstani banks.

## 🎯 Features

- **High-Value Filtering**: Automatically filters transactions ≥ 5,000,000 KZT.
- **LLM Analysis**: Uses OpenAI to classify offshore risk (Yes/Suspect/No).
- **Smart Detection**: Analyzes SWIFT/country codes, payer/receiver and bank addresses.
- **Web Interface**: Simple UI for uploading files and downloading reports.
- **Privacy Focused**: Excludes names of physical persons from analysis.

## 🚀 Quick Start

### Using Docker (Recommended)

1. **Configure environment**:
   Create a `.env` file with your OpenAI API key:
   ```bash
   OPENAI_API_KEY=your_key_here
   OPENAI_MODEL=gpt-4.1
   ```

2. **Run the application**:
   ```bash
   docker-compose up --build
   ```

3. **Access**: Open [http://localhost:8000](http://localhost:8000)

### Local Installation

1. **Install dependencies**:
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Run**:
   ```bash
   python main.py
   ```

## ⚙️ Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | *(required)* | Your OpenAI API key |
| `OPENAI_MODEL` | `gpt-4.1` | Model to use |
| `MAX_CONCURRENT_LLM_CALLS` | `5` | Parallel LLM request limit |
| `AMOUNT_THRESHOLD_KZT` | `5000000` | Minimum transaction amount filter |
| `PORT` | `8000` | Server port |

## 📖 Usage

1. **Upload Files**: 
   - **Incoming**: Excel file with headers at row 5.
   - **Outgoing**: Excel file with headers at row 6.
2. **Process**: Click "Process Files" to start analysis.
3. **Download**: Get the processed Excel files with a new `Результат` column containing risk analysis.

## 📁 Project Structure

```
offshore/
├── app/              # API routes
├── core/             # Configuration & core logic
├── llm/              # OpenAI integration
├── services/         # Business logic
├── templates/        # Web UI
└── main.py           # Entry point
```

## 📄 License

Internal use only. Not for public distribution.