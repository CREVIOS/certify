# IPO Verification Backend

AI-powered IPO document verification system with citation tracking.

## Features

- FastAPI-based REST API
- AI-powered document analysis using LangChain with GPT-4 and Gemini 2.5 Pro
- Vector storage with Weaviate
- Asynchronous task processing with Celery
- Document processing (PDF, DOCX, Excel)
- Citation tracking and verification
- Supabase integration for storage

## Setup

1. Install dependencies:
   ```bash
   poetry install
   ```

2. Configure environment variables (see `.env.example`)

3. Run the application:
   ```bash
   # From the project root directory
   python3 -m app.main
   
   # Or using uvicorn directly:
   poetry run uvicorn app.main:socket_app --reload --host 0.0.0.0 --port 8000
   ```

## Development

- Python 3.11+
- Poetry for dependency management
- Pre-commit hooks for code quality

## License

MIT
