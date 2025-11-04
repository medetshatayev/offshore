# Architecture Documentation

## System Overview

The Offshore Risk Detection Service is a FastAPI-based application that analyzes banking transactions to identify potential offshore jurisdiction involvement. The system follows clean architecture principles with clear separation of concerns.

## Architecture Layers

### 1. Presentation Layer (`app/`)

**Responsibility**: HTTP handling and API endpoints

- `api.py` - FastAPI route handlers
  - Handles HTTP requests/responses
  - Validates file uploads
  - Manages background tasks
  - Returns appropriate HTTP status codes
  - ~320 lines (clean, focused)

**Key Principles**:
- Thin controllers
- Delegates business logic to service layer
- Only HTTP-specific concerns

### 2. Application/Service Layer (`services/`)

**Responsibility**: Business logic and use cases

- `transaction_service.py` - Core transaction processing service
  - `extract_transaction_signals()` - Extract matching signals from transaction
  - `process_transaction_batch()` - Batch processing with concurrency control
  - `build_classification_statistics()` - Aggregate statistics
  - `process_file()` - End-to-end file processing pipeline
  - `process_files()` - Process multiple files

**Key Principles**:
- Encapsulates business rules
- Coordinates between infrastructure components
- Independent of HTTP/UI layer
- Easy to test

### 3. Domain Layer (`core/schema.py`, `core/exceptions.py`)

**Responsibility**: Business entities and domain rules

- `schema.py` - Pydantic models for domain entities
  - `OffshoreRiskResponse` - Risk assessment result
  - `Classification` - Risk classification
  - `TransactionSignals` - Matching signals
  - `TransactionInput` - Input transaction

- `exceptions.py` - Domain-specific exceptions
  - `OffshoreRiskException` - Base exception
  - `FileProcessingError`, `ParsingError`, `ValidationError`
  - `LLMError`, `ExportError`, `ConfigurationError`
  - `DataNotFoundError`

**Key Principles**:
- Pure business logic
- No dependencies on infrastructure
- Rich domain models

### 4. Infrastructure Layer (`core/`, `llm/`)

**Responsibility**: External services and technical concerns

#### Core Infrastructure (`core/`)
- `config.py` - Configuration management
- `parsing.py` - Excel file parsing
- `normalize.py` - Data normalization
- `matching.py` - Fuzzy matching algorithms
- `swift.py` - SWIFT code handling
- `exporters.py` - Excel export
- `logger.py` - Logging setup

#### LLM Integration (`llm/`)
- `client.py` - OpenAI API client
- `classify.py` - Transaction classification
- `prompts.py` - LLM prompt management

**Key Principles**:
- Adapters to external services
- Technical implementations
- Can be swapped without affecting business logic

## Data Flow

```
┌─────────────────────────────────────────────────────────────┐
│                      HTTP Request                           │
│                   (Upload Excel Files)                      │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│              Presentation Layer (app/api.py)                │
│  - Validate file extensions                                 │
│  - Save uploaded files                                      │
│  - Create job ID                                            │
│  - Start background task                                    │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│     Service Layer (services/transaction_service.py)        │
│                                                             │
│  1. Parse Excel File ────► Infrastructure (parsing.py)     │
│  2. Filter by Threshold ─► Infrastructure (normalize.py)   │
│  3. Add Metadata ────────► Infrastructure (normalize.py)   │
│  4. Extract Signals ─────► Infrastructure (matching.py)    │
│  5. Classify with LLM ───► Infrastructure (llm/)           │
│  6. Export Results ──────► Infrastructure (exporters.py)   │
│                                                             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│           Infrastructure Layer (core/, llm/)                │
│                                                             │
│  Excel ─► Parse ─► Normalize ─► Match ─► LLM ─► Export    │
│                                                             │
└─────────────────┬───────────────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────────────┐
│                      HTTP Response                          │
│              (Job Status / Download Link)                   │
└─────────────────────────────────────────────────────────────┘
```

## Component Interactions

```
┌──────────────┐
│   API Layer  │
│  (api.py)    │
└──────┬───────┘
       │ uses
       ▼
┌──────────────────┐
│ Service Layer    │
│ (TransactionSvc) │
└──────┬───────────┘
       │ uses
       ▼
┌──────────────────────────────────────────┐
│      Infrastructure Layer                │
│                                          │
│  ┌────────┐  ┌─────────┐  ┌──────────┐ │
│  │Parsing │  │Matching │  │Normalize │ │
│  └────────┘  └─────────┘  └──────────┘ │
│                                          │
│  ┌────────┐  ┌─────────┐  ┌──────────┐ │
│  │LLM Cls │  │Exporters│  │Config    │ │
│  └────────┘  └─────────┘  └──────────┘ │
└──────────────────────────────────────────┘
       │
       ▼ depends on
┌──────────────────┐
│  Domain Layer    │
│ (Schema, Except) │
└──────────────────┘
```

## Configuration Management

**Centralized Settings** (`core/config.py`)

```python
class Settings(BaseSettings):
    # Application
    app_name: str
    host: str
    port: int
    log_level: str
    
    # OpenAI
    openai_api_key: str
    openai_model: str
    openai_timeout: int
    
    # Processing
    amount_threshold_kzt: float
    max_concurrent_llm_calls: int
    fuzzy_match_threshold: float
    
    # Storage
    temp_storage_path: str
    offshore_countries_file: Path
```

**Benefits**:
- Type-safe configuration
- Validation at startup
- Single source of truth
- Easy testing with mocked settings

## Error Handling Strategy

### Exception Hierarchy

```
OffshoreRiskException (base)
├── FileProcessingError
├── ParsingError
├── ValidationError
├── LLMError
├── ExportError
├── ConfigurationError
└── DataNotFoundError
```

### Error Flow

1. **Domain Layer**: Raises domain exceptions with rich context
2. **Service Layer**: Catches and handles domain exceptions, may wrap in service-specific errors
3. **API Layer**: Catches all exceptions, logs, and returns appropriate HTTP responses

### Error Context

All custom exceptions include:
- `message`: Human-readable error message
- `details`: Dictionary with error context (file paths, line numbers, etc.)

Example:
```python
raise ParsingError(
    "Failed to parse Excel file",
    details={
        "file_path": file_path,
        "direction": direction,
        "error": str(e)
    }
)
```

## Dependency Injection

### Current Approach

1. **Configuration**: Singleton pattern via `get_settings()`
2. **Services**: Instantiated in API layer, can be injected for testing
3. **LLM Client**: Singleton pattern via `get_client()`

### Benefits

- Easy to mock for testing
- Loose coupling between components
- Can swap implementations without changing consumers

## Testing Strategy

### Unit Tests

**Domain Layer**:
```python
# Test pure business logic
def test_transaction_classification():
    # No external dependencies
    pass
```

**Service Layer**:
```python
# Test with mocked infrastructure
def test_process_file_with_mock():
    service = TransactionService()
    # Mock: LLM client, file system, etc.
    result = await service.process_file(...)
```

**Infrastructure Layer**:
```python
# Test with test fixtures
def test_parse_excel():
    df = parse_excel_file("test_file.xlsx", "incoming")
    assert len(df) > 0
```

### Integration Tests

```python
# Test full pipeline
async def test_full_transaction_processing():
    # Use test configuration
    # Process real file
    # Verify output
```

## Scalability Considerations

### Current Design

1. **Concurrency**: Semaphore-based concurrency control for LLM calls
2. **Background Tasks**: FastAPI background tasks for async processing
3. **In-Memory Jobs**: Simple dict for job tracking

### Future Enhancements

1. **Job Queue**: Replace in-memory dict with Redis/RabbitMQ
2. **Worker Pool**: Separate worker processes for file processing
3. **Caching**: Cache LLM results for similar transactions
4. **Database**: PostgreSQL for job persistence
5. **Horizontal Scaling**: Multiple API instances behind load balancer

## Security Considerations

1. **File Upload Validation**: Extension and path traversal checks
2. **Configuration**: API keys from environment variables
3. **Temporary Storage**: Cleanup after processing
4. **Path Resolution**: Prevent directory traversal attacks
5. **Error Messages**: Don't expose internal paths in API responses

## Monitoring & Observability

### Logging

- Structured logging with context
- Different log levels (DEBUG, INFO, WARNING, ERROR)
- Request tracing with job IDs

### Metrics (Future)

- Request count by endpoint
- Processing time per file
- LLM API latency
- Error rates by type
- Queue depth

### Health Checks

- `/health` endpoint for liveness probe
- Validates service availability
- Can be extended to check dependencies

## Performance Optimization

1. **Batch Processing**: Process multiple transactions concurrently
2. **Semaphore Control**: Limit concurrent LLM calls to avoid rate limits
3. **Progress Logging**: Track processing progress
4. **Efficient Data Structures**: Use pandas for bulk operations
5. **Connection Pooling**: Reuse HTTP connections for LLM API

## Development Workflow

1. **Local Development**:
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Set environment variables
   cp .env.example .env
   
   # Run server
   python main.py
   ```

2. **Testing**:
   ```bash
   # Run all tests
   pytest
   
   # With coverage
   pytest --cov=core --cov=services --cov=llm
   ```

3. **Docker**:
   ```bash
   docker-compose up
   ```

## Deployment

The application is containerized and can be deployed to:
- Docker/Docker Compose
- Kubernetes
- Cloud platforms (AWS ECS, Google Cloud Run, Azure Container Instances)

## Conclusion

The architecture follows clean architecture principles:
- **Independence**: Business logic independent of frameworks and infrastructure
- **Testability**: Easy to test each layer in isolation
- **Maintainability**: Clear separation of concerns
- **Flexibility**: Can swap implementations without affecting other layers
- **Scalability**: Designed to scale horizontally
