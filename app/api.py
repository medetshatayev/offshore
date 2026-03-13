"""
FastAPI routes for file upload and processing.
Clean API layer following separation of concerns principle.
"""
import asyncio
import uuid
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from core.config import get_settings
from core.exceptions import FileProcessingError
from core.logger import setup_logger
from core.pg import close_pg_pool, init_pg_pool, init_transaction_logs_table
from llm.client import close_client
from services.transaction_service import TransactionService

logger = setup_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: initialize and clean up resources."""
    # Startup
    try:
        await init_pg_pool()
        await init_transaction_logs_table()
        logger.info("PostgreSQL transaction logging initialized")
    except Exception as e:
        logger.error(f"Failed to initialize PostgreSQL: {e}", exc_info=True)
        logger.warning("Application will continue without transaction logging")
    yield
    # Shutdown
    await close_pg_pool()
    close_client()


# Initialize FastAPI app
app = FastAPI(
    title="Offshore Transaction Risk Detection",
    description="Detect offshore jurisdiction involvement in banking transactions",
    version="1.0.0",
    root_path=settings.root_path,
    lifespan=lifespan,
)

# Setup templates
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))

# In-memory job storage (use Redis/DB in production)
jobs: Dict[str, Dict[str, Any]] = {}

# Service instance
transaction_service = TransactionService()


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    """Render upload form."""
    return templates.TemplateResponse("index.html", {
        "request": request,
        "base_path": settings.root_path.rstrip("/"),
    })


@app.get("/health")
async def health_check() -> Dict[str, str]:
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "offshore_risk",
        "version": "1.0.0"
    }


@app.get("/favicon.ico")
async def favicon() -> Response:
    """Return empty response for favicon to avoid 404 errors."""
    return Response(status_code=204)


def _extract_original_filename(stored_path: Path) -> str:
    """
    Extract original filename from the stored path.

    Removes job ID prefix from filenames like "{job_id}_incoming_{filename}".

    Args:
        stored_path: Path to the stored file with job ID prefix

    Returns:
        Original filename without job ID prefix
    """
    name = stored_path.name
    return name.split("_", 2)[-1] if "_" in name else name


def _build_direction_result(result: Any, failed: bool) -> Dict[str, Any]:
    """
    Build the result dictionary for a single processing direction.

    Args:
        result: Processing result (dict if successful, Exception if failed)
        failed: Whether the processing failed

    Returns:
        Dictionary with filename, stats, and error information
    """
    if failed:
        return {"filename": None, "stats": {}, "error": str(result)}

    if not isinstance(result, dict):
        return {"filename": None, "stats": {}, "error": None}

    filename = Path(result["output_path"]).name if result.get("output_path") else None
    return {"filename": filename, "stats": result.get("stats", {}), "error": None}


async def process_files_background(
    job_id: str,
    incoming_path: Path,
    outgoing_path: Path
) -> None:
    """
    Background task to process files.

    Args:
        job_id: Unique job identifier
        incoming_path: Path to incoming transactions file
        outgoing_path: Path to outgoing transactions file
    """
    executor = ThreadPoolExecutor(max_workers=settings.max_concurrent_llm_calls)
    try:
        jobs[job_id]["status"] = "processing"
        jobs[job_id]["message"] = "Processing incoming and outgoing transactions..."

        # Shared semaphore so both directions compete for the same LLM concurrency budget
        shared_semaphore = asyncio.Semaphore(settings.max_concurrent_llm_calls)

        incoming_orig = _extract_original_filename(incoming_path)
        outgoing_orig = _extract_original_filename(outgoing_path)

        results = await asyncio.gather(
            transaction_service.process_file(
                str(incoming_path), "incoming",
                job_id=job_id,
                original_filename=incoming_orig,
                semaphore=shared_semaphore,
                executor=executor,
            ),
            transaction_service.process_file(
                str(outgoing_path), "outgoing",
                job_id=job_id,
                original_filename=outgoing_orig,
                semaphore=shared_semaphore,
                executor=executor,
            ),
            return_exceptions=True,
        )

        incoming_result, outgoing_result = results
        incoming_failed = isinstance(incoming_result, Exception)
        outgoing_failed = isinstance(outgoing_result, Exception)

        if incoming_failed and outgoing_failed:
            raise FileProcessingError(
                "Both directions failed",
                details={
                    "incoming_error": str(incoming_result),
                    "outgoing_error": str(outgoing_result),
                }
            )

        if incoming_failed:
            logger.error(f"Job {job_id} incoming direction failed: {incoming_result}")
        else:
            jobs[job_id]["incoming_result"] = incoming_result

        if outgoing_failed:
            logger.error(f"Job {job_id} outgoing direction failed: {outgoing_result}")
        else:
            jobs[job_id]["outgoing_result"] = outgoing_result

        jobs[job_id]["status"] = "completed"
        jobs[job_id]["message"] = "Processing completed successfully"
        jobs[job_id]["result"] = {
            "incoming": _build_direction_result(incoming_result, incoming_failed),
            "outgoing": _build_direction_result(outgoing_result, outgoing_failed),
        }

        logger.info(f"Job {job_id} completed successfully")

    except FileProcessingError as e:
        logger.error(f"Job {job_id} failed with processing error: {e}", exc_info=True)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Processing failed: {e.message}"
        jobs[job_id]["error"] = e.message
        jobs[job_id]["error_details"] = e.details

    except Exception as e:
        logger.error(f"Job {job_id} failed with unexpected error: {e}", exc_info=True)
        jobs[job_id]["status"] = "failed"
        jobs[job_id]["message"] = f"Processing failed: {str(e)}"
        jobs[job_id]["error"] = str(e)

    finally:
        executor.shutdown(wait=False)
        # Clean up uploaded files
        for path in [incoming_path, outgoing_path]:
            try:
                if path.exists():
                    path.unlink()
                    logger.debug(f"Cleaned up: {path}")
            except Exception as cleanup_error:
                logger.warning(f"Failed to cleanup {path}: {cleanup_error}")


def validate_file_extension(filename: Optional[str]) -> None:
    """
    Validate file has correct extension.
    
    Args:
        filename: Name of file to validate (may be None for unnamed uploads)
    
    Raises:
        HTTPException: If file extension is invalid
    """
    if not filename or not filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {filename}. Only .xlsx and .xls are supported."
        )


@app.post("/process", status_code=202)
async def process_files(
    background_tasks: BackgroundTasks,
    incoming_file: UploadFile = File(...),
    outgoing_file: UploadFile = File(...)
):
    """
    Accept files and start background processing.
    Returns immediately with job ID for status polling.
    
    Args:
        background_tasks: FastAPI background tasks
        incoming_file: Incoming transactions Excel file
        outgoing_file: Outgoing transactions Excel file
    
    Returns:
        202 Accepted with job_id for status polling
    """
    logger.info(
        f"Received files: incoming={incoming_file.filename}, "
        f"outgoing={outgoing_file.filename}"
    )
    
    # Validate file extensions
    validate_file_extension(incoming_file.filename)
    validate_file_extension(outgoing_file.filename)
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Save uploaded files temporarily
    incoming_path = Path(settings.temp_storage_path) / f"{job_id}_incoming_{incoming_file.filename}"
    outgoing_path = Path(settings.temp_storage_path) / f"{job_id}_outgoing_{outgoing_file.filename}"
    
    async def save_file(path: Path, file: UploadFile) -> None:
        """Save uploaded file to disk."""
        content = await file.read()
        path.write_bytes(content)

    try:
        # Save uploaded files
        await save_file(incoming_path, incoming_file)
        await save_file(outgoing_path, outgoing_file)
        
        # Initialize job status
        jobs[job_id] = {
            "job_id": job_id,
            "status": "queued",
            "message": "Files uploaded, starting processing...",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "progress": 0,
        }
        
        # Start background processing
        background_tasks.add_task(
            process_files_background,
            job_id,
            incoming_path,
            outgoing_path
        )
        
        logger.info(f"Job {job_id} queued for processing")
        
        # Return immediately with job ID
        return {
            "job_id": job_id,
            "status": "accepted",
            "message": "Processing started. Use job_id to check status."
        }
    
    except Exception as e:
        logger.error(f"Failed to queue job: {e}", exc_info=True)
        # Clean up files if upload failed
        for path in [incoming_path, outgoing_path]:
            if path.exists():
                path.unlink()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start processing: {str(e)}"
        )


@app.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Get status of a processing job.
    
    Args:
        job_id: Job identifier
    
    Returns:
        Job status information
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job = jobs[job_id]
    
    # Build response based on status
    response = {
        "job_id": job_id,
        "status": job["status"],
        "message": job["message"],
        "created_at": job.get("created_at")
    }
    
    # Add result if completed
    if job["status"] == "completed" and "result" in job:
        response["result"] = job["result"]
    
    # Add error if failed
    if job["status"] == "failed":
        response["error"] = job.get("error")
        if "error_details" in job:
            response["error_details"] = job["error_details"]
    
    return response


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
    
    file_path = Path(settings.temp_storage_path) / filename
    
    # Ensure the resolved path is within TEMP_STORAGE
    try:
        file_path = file_path.resolve()
        temp_storage_resolved = Path(settings.temp_storage_path).resolve()
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
    uvicorn.run(app, host=settings.host, port=settings.port)
