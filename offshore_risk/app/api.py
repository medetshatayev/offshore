"""
FastAPI routes for file upload and processing.
Handles the main workflow: upload -> parse -> filter -> match -> LLM -> export.
"""
import os
import asyncio
from pathlib import Path
from typing import List
import pandas as pd
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from core.logger import setup_logger
from core.parsing import parse_excel_file, validate_dataframe
from core.normalize import filter_by_threshold, add_metadata, normalize_transaction
from core.swift import extract_country_from_swift
from core.matching import (
    fuzzy_match_country_code,
    fuzzy_match_country_name,
    fuzzy_match_city,
    aggregate_matching_signals
)
from core.exporters import export_to_excel, create_output_filename
from llm.classify import classify_transaction

logger = setup_logger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="Offshore Transaction Risk Detection",
    description="Detect offshore jurisdiction involvement in banking transactions",
    version="1.0.0"
)

# Setup templates
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# Temp storage path
TEMP_STORAGE = os.getenv("TEMP_STORAGE_PATH", "/tmp/offshore_risk")
Path(TEMP_STORAGE).mkdir(parents=True, exist_ok=True)

# Concurrency limit
MAX_CONCURRENT_LLM = int(os.getenv("MAX_CONCURRENT_LLM_CALLS", "5"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render upload form."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "offshore_risk"}


async def process_transaction_batch(
    transactions: List[dict],
    semaphore: asyncio.Semaphore
) -> List[dict]:
    """
    Process a batch of transactions with concurrency control.
    
    Args:
        transactions: List of normalized transaction dictionaries
        semaphore: Asyncio semaphore for concurrency control
    
    Returns:
        List of classification responses
    """
    total = len(transactions)
    completed = [0]  # Use list to allow modification in nested function
    
    async def process_single(txn, idx):
        async with semaphore:
            # Run LLM classification in thread pool (since it's synchronous)
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, classify_transaction, txn)
            completed[0] += 1
            # Log progress every 10 transactions
            if completed[0] % 10 == 0 or completed[0] == total:
                logger.info(f"Progress: {completed[0]}/{total} transactions processed")
            return result
    
    tasks = [process_single(txn, i) for i, txn in enumerate(transactions)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert exceptions to error responses
    from llm.classify import create_error_response
    processed_results = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"Transaction {i} failed: {result}")
            processed_results.append(
                create_error_response(transactions[i], str(result))
            )
        else:
            processed_results.append(result)
    
    return processed_results


async def process_file(file_path: str, direction: str) -> dict:
    """
    Process a single Excel file through the full pipeline.
    
    Args:
        file_path: Path to Excel file
        direction: "incoming" or "outgoing"
    
    Returns:
        Dictionary with output_path and statistics
    """
    logger.info(f"Processing {direction} file: {file_path}")
    
    # 1. Parse Excel
    df = parse_excel_file(file_path, direction)
    stats = validate_dataframe(df, direction)
    logger.info(f"Parsed {len(df)} transactions")
    
    # 2. Filter by threshold
    df_filtered = filter_by_threshold(df)
    logger.info(f"After filtering: {len(df_filtered)} transactions")
    
    if len(df_filtered) == 0:
        logger.warning("No transactions meet the threshold criteria")
        return {
            "output_path": None,
            "stats": {**stats, "filtered_count": 0, "processed_count": 0},
            "error": "No transactions meet the 5,000,000 KZT threshold"
        }
    
    # 3. Add metadata
    df_filtered = add_metadata(df_filtered, direction)
    
    # 4. Process each transaction: normalize -> extract signals -> classify
    transactions_with_signals = []
    
    for idx, row in df_filtered.iterrows():
        # Normalize transaction
        txn = normalize_transaction(row, direction)
        
        # Extract SWIFT country
        swift_country = extract_country_from_swift(txn.get("swift_code"))
        
        # Fuzzy matching
        country_code_match = fuzzy_match_country_code(txn.get("country_code"))
        country_name_to_match = txn.get("payer_country") if direction == "incoming" else txn.get("recipient_country")
        country_name_match = fuzzy_match_country_name(country_name_to_match)
        city_match = fuzzy_match_city(txn.get("city"))
        
        # Aggregate signals
        signals = aggregate_matching_signals(
            swift_country,
            country_code_match,
            country_name_match,
            city_match
        )
        
        txn["signals"] = signals
        transactions_with_signals.append(txn)
    
    logger.info(f"Prepared {len(transactions_with_signals)} transactions with signals")
    
    # 5. Classify with LLM (with concurrency control)
    logger.info("Starting LLM classification (this may take a while)...")
    
    # Create semaphore for concurrency control
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM)
    
    # Run async processing with progress logging
    total = len(transactions_with_signals)
    logger.info(f"Starting LLM classification for {total} transactions...")
    
    responses = await process_transaction_batch(transactions_with_signals, semaphore)
    
    logger.info(f"Completed LLM classification for {len(responses)}/{total} transactions")
    
    # 6. Export to Excel
    sheet_name = "Входящие операции" if direction == "incoming" else "Исходящие операции"
    output_path = create_output_filename(direction, TEMP_STORAGE)
    
    export_to_excel(df_filtered, responses, output_path, sheet_name)
    
    # Build statistics
    classification_counts = {}
    for resp in responses:
        label = resp.classification.label
        classification_counts[label] = classification_counts.get(label, 0) + 1
    
    return {
        "output_path": output_path,
        "stats": {
            **stats,
            "filtered_count": len(df_filtered),
            "processed_count": len(responses),
            "classifications": classification_counts
        }
    }


@app.post("/process")
async def process_files(
    incoming_file: UploadFile = File(...),
    outgoing_file: UploadFile = File(...)
):
    """
    Process both incoming and outgoing transaction files.
    
    Returns:
        JSON with download links and statistics
    """
    logger.info(
        f"Received files: incoming={incoming_file.filename}, "
        f"outgoing={outgoing_file.filename}"
    )
    
    # Validate file extensions
    for file in [incoming_file, outgoing_file]:
        if not file.filename.endswith(('.xlsx', '.xls')):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type: {file.filename}. Only .xlsx and .xls are supported."
            )
    
    # Save uploaded files temporarily
    incoming_path = Path(TEMP_STORAGE) / f"incoming_{incoming_file.filename}"
    outgoing_path = Path(TEMP_STORAGE) / f"outgoing_{outgoing_file.filename}"
    
    # Track which files were successfully saved for cleanup
    saved_files = []
    
    try:
        # Save incoming file
        with open(incoming_path, "wb") as f:
            content = await incoming_file.read()
            f.write(content)
        saved_files.append(incoming_path)
        
        # Save outgoing file
        with open(outgoing_path, "wb") as f:
            content = await outgoing_file.read()
            f.write(content)
        saved_files.append(outgoing_path)
        
        logger.info("Files saved, starting processing...")
        
        # Process both files
        incoming_result = await process_file(str(incoming_path), "incoming")
        outgoing_result = await process_file(str(outgoing_path), "outgoing")
        
        # Build response
        response = {
            "status": "success",
            "incoming": {
                "filename": Path(incoming_result["output_path"]).name if incoming_result["output_path"] else None,
                "stats": incoming_result["stats"]
            },
            "outgoing": {
                "filename": Path(outgoing_result["output_path"]).name if outgoing_result["output_path"] else None,
                "stats": outgoing_result["stats"]
            }
        }
        
        logger.info("Processing completed successfully")
        return response
    
    except Exception as e:
        logger.error(f"Processing failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
    
    finally:
        # Clean up uploaded files (only ones that were successfully saved)
        for path in saved_files:
            try:
                if path.exists():
                    path.unlink()
                    logger.debug(f"Cleaned up: {path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup {path}: {cleanup_error}")


@app.get("/download/{filename}")
async def download_file(filename: str):
    """
    Download processed file.
    
    Args:
        filename: Name of the file to download
    
    Returns:
        File response
    """
    # Security: Validate filename to prevent path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    # Only allow Excel files
    if not filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Invalid file type")
    
    file_path = Path(TEMP_STORAGE) / filename
    
    # Ensure the resolved path is within TEMP_STORAGE
    try:
        file_path = file_path.resolve()
        temp_storage_resolved = Path(TEMP_STORAGE).resolve()
        if not str(file_path).startswith(str(temp_storage_resolved)):
            raise HTTPException(status_code=400, detail="Invalid file path")
    except Exception as e:
        logger.error(f"Path resolution error: {e}")
        raise HTTPException(status_code=400, detail="Invalid file path")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")
    
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
