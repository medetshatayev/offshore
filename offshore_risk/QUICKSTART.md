# Quick Start Guide

## 1. Install Dependencies

```bash
# Navigate to project directory
cd offshore_risk

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install packages
pip install -r requirements.txt
```

## 2. Configure Environment

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your OpenAI API key
nano .env  # or use your favorite editor
```

**Required**: Set your OpenAI API key in `.env`:
```
OPENAI_API_KEY=sk-your-actual-key-here
```

## 3. Verify Setup

```bash
# Run verification script
python verify_setup.py
```

This will check:
- ✅ Python version (3.12+)
- ✅ All dependencies installed
- ✅ Project structure
- ✅ Data files present
- ✅ Environment configured

## 4. Start the Server

```bash
python main.py
```

You should see:
```
INFO: Starting Offshore Risk Detection Service
INFO: Starting server on 0.0.0.0:8000
```

## 5. Open Web Interface

Open your browser and go to:
```
http://localhost:8000
```

## 6. Upload Files

1. Click **"Choose File"** for incoming transactions
2. Select your Excel file (входящие операции)
3. Click **"Choose File"** for outgoing transactions
4. Select your Excel file (исходящие операции)
5. Click **"Process Transactions"**

The system will:
- Parse both files
- Filter transactions ≥ 5,000,000 KZT
- Extract SWIFT country codes
- Perform fuzzy matching
- Call LLM for classification
- Generate processed files

## 7. Download Results

When processing completes:
- Download **incoming_transactions_processed_*.xlsx**
- Download **outgoing_transactions_processed_*.xlsx**

Each file will have all original columns plus a new **"Результат"** column.

## Expected File Format

### Incoming Transactions
- Headers start at **row 5** (skip first 4 rows)
- Must contain columns like:
  - Сумма в тенге (for filtering)
  - SWIFT Банка плательщика
  - Код страны
  - Страна получателя
  - Город
  - etc.

### Outgoing Transactions
- Headers start at **row 6** (skip first 5 rows)
- Must contain columns like:
  - Сумма в тенге (for filtering)
  - SWIFT Банка получателя
  - Код страны
  - Страна получателя
  - Город
  - etc.

## Troubleshooting

### "OPENAI_API_KEY not found"
→ Make sure you created `.env` and set your API key

### "Invalid Excel format"
→ Check that your files match the expected format (see above)

### "No transactions meet threshold"
→ Ensure some transactions have Сумма в тенге ≥ 5,000,000

### Processing takes too long
→ Reduce `MAX_CONCURRENT_LLM_CALLS` in `.env` or process smaller batches

### Import errors
→ Run `pip install -r requirements.txt` again

## Next Steps

- See [README.md](README.md) for full documentation
- Adjust settings in `.env` as needed
- Check logs for detailed processing information

## Support

If you encounter issues:
1. Check the troubleshooting section
2. Review logs in console output
3. Verify file formats match specifications
4. Contact the development team

---

**Happy processing! 🚀**
