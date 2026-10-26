# Adaptive Learning Platform starter

Stack: React + Vite + TypeScript, Python FastAPI, PostgreSQL + pgvector, optional Gemini.

## Run database
From project root:
```powershell
docker compose up -d db
```

## Run backend (PowerShell)
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```
API docs: http://localhost:8000/docs

## Run frontend (second terminal)
```powershell
cd frontend
npm install
npm run dev
```
Open http://localhost:5173.

Add a Gemini API key to `backend/.env` for live AI generation. Without it, a clearly marked demo question generator is used.

Important: this is a starter prototype, not production-secure. PDF extraction/chunking is included; embeddings and vector retrieval need an embedding provider configured to match `EMBEDDING_DIMENSION`. Review and test all generated answers before using for real exams.
