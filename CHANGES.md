# Codebase Refactoring Changes

## Summary
Refactored and cleaned the entire codebase for improved maintainability, consistency, and best practices compliance.

## Changes Made

### Pydantic v2 Compatibility (`core/config.py`)
- Replaced deprecated `@validator` with `@field_validator`
- Replaced `class Config` with `model_config = ConfigDict(...)`
- Added proper `@classmethod` decorators and type hints to validators

### Database Module (`core/db.py`)
- Added context manager pattern with `@contextmanager` for connection handling
- Replaced `datetime.utcnow()` with `datetime.now(timezone.utc)` (deprecation fix)
- Added comprehensive docstrings
- Improved type hints

### API Module (`app/api.py`)
- Fixed deprecated `datetime.utcnow()` usage
- Improved import organization

### LLM Client (`llm/client.py`)
- Fixed duplicate `if not content:` check (bug fix)
- Improved exception handling in HTTP error handler
- Organized imports alphabetically

### Dependencies (`requirements.txt`)
- Removed unused packages: `openai`, `python-Levenshtein`, `aiofiles`
- Organized dependencies by category with comments

### Configuration (`env.example`)
- Removed unused `FUZZY_MATCH_THRESHOLD` variable
- Organized variables by category

### Parsing Module (`core/parsing.py`)
- Changed column mappings from `Dict` to `Set` (more appropriate data structure)
- Added proper type hints
- Removed unused import

### Module Docstrings
- Enhanced `__init__.py` files in all packages with comprehensive descriptions
- Improved function-level documentation

### Docker Configuration (`Dockerfile`)
- Removed hardcoded proxy configuration
- Improved layer caching with separate COPY for requirements
- Added storage directory creation

### Code Cleanup
- Removed commented-out code in `core/normalize.py`
- Organized imports alphabetically across all modules
- Standardized trailing commas in collections
- Fixed deprecation warnings

## Files Modified
- `core/config.py`
- `core/db.py`
- `core/normalize.py`
- `core/parsing.py`
- `core/exporters.py`
- `app/__init__.py`
- `app/api.py`
- `core/__init__.py`
- `llm/__init__.py`
- `llm/client.py`
- `llm/classify.py`
- `services/__init__.py`
- `services/transaction_service.py`
- `main.py`
- `requirements.txt`
- `.env.example`
- `Dockerfile`
