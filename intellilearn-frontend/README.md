# AdaptiveLearning frontend

A responsive React + TypeScript + Vite frontend based on the supplied AdaptiveLearning screenshots. It includes the dashboard, test menu, mock-test setup, timed question workspace, subject/topic selection, AI test configuration, results review, and AI Tutor/PDF upload screens.

## Run locally

1. Open a terminal in this folder.
2. Install packages:
   ```bash
   npm install
   ```
3. Optional: copy `.env.example` to `.env` and set `VITE_API_URL` to your FastAPI backend URL (default `http://localhost:8000`).
4. Start the frontend:
   ```bash
   npm run dev
   ```
5. Open the URL Vite prints, usually `http://localhost:5173`.

## Backend integration

The frontend uses the existing FastAPI endpoints where available: `/questions/generate`, `/exams/start`, `/documents/upload`, and `/rag/ask`. Endpoint payloads can differ between backend versions; adjust the corresponding calls in `src/App.tsx` if your current `main.py` expects different fields or requires an exam session ID. Sample questions are included as a UI fallback so the pages can be previewed when the exam API is unavailable.

## Notes

- This package changes the frontend only; it does not replace or modify your backend or database.
- Never put your Gemini API key or database password in frontend environment variables. Keep secrets in the backend `.env` file only.
