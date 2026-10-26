import os
from contextlib import asynccontextmanager

from datetime import datetime, timezone

from .rag import ingest_pdf, retrieve_context, backfill_missing_topics
from uuid import UUID, uuid4
from azure.core.exceptions import AzureError
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient, ContentSettings

from fastapi import FastAPI, HTTPException, UploadFile, File, Request

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel, Field

from psycopg.types.json import Jsonb

from .config import settings

from .db import init_db, get_connection

from .ai import generate_questions, tutor_answer


from .auth import hash_password, verify_password, create_access_token, current_user_from_request

import re

from fastapi.security import HTTPBearer

@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        init_db()
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS user_test_attempts (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    subject TEXT NOT NULL,
                    topic TEXT,
                    duration_seconds INTEGER NOT NULL DEFAULT 0,
                    total_questions INTEGER NOT NULL,
                    correct_answers INTEGER NOT NULL,
                    accuracy_percent NUMERIC(5,2) NOT NULL,
                    topics_practiced JSONB NOT NULL DEFAULT '[]'::jsonb,
                    completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_user_test_attempts_user_completed
                ON user_test_attempts (user_id, completed_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_conversations (
                    id UUID PRIMARY KEY,
                    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    title TEXT NOT NULL DEFAULT 'New chat',
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_conversations_user_updated
                ON chat_conversations (user_id, updated_at DESC)
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id BIGSERIAL PRIMARY KEY,
                    conversation_id UUID NOT NULL REFERENCES chat_conversations(id) ON DELETE CASCADE,
                    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                    content TEXT NOT NULL,
                    sources JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_messages_conversation_created
                ON chat_messages (conversation_id, created_at, id)
                """
            )
            connection.commit()
    except Exception as exc:
        print(f"Database initialization failed: {exc}")
    yield

AZURE_STORAGE_ACCOUNT_NAME = os.getenv("AZURE_STORAGE_ACCOUNT_NAME")
AZURE_STORAGE_CONTAINER_NAME = os.getenv("AZURE_STORAGE_CONTAINER_NAME", "study-documents")


def get_blob_container():
    """Return the private Azure Blob Storage container using managed identity."""
    if not AZURE_STORAGE_ACCOUNT_NAME:
        raise RuntimeError("AZURE_STORAGE_ACCOUNT_NAME is missing.")

    account_url = f"https://{AZURE_STORAGE_ACCOUNT_NAME}.blob.core.windows.net"
    credential = DefaultAzureCredential()
    service = BlobServiceClient(account_url=account_url, credential=credential)
    return service.get_container_client(AZURE_STORAGE_CONTAINER_NAME)


app = FastAPI(title="Adaptive Learning Platform API", lifespan=lifespan)

bearer_scheme = HTTPBearer(auto_error=False)

def custom_openapi():

          from fastapi.openapi.utils import get_openapi

          if app.openapi_schema:

                    return app.openapi_schema

          schema = get_openapi(

                    title=app.title,

                    version="1.0.0",

                    routes=app.routes,

          )

          schema.setdefault("components", {}).setdefault("securitySchemes", {})[

                    "BearerAuth"

          ] = {

                    "type": "http",

                    "scheme": "bearer",

                    "bearerFormat": "JWT",

          }

          app.openapi_schema = schema

          return app.openapi_schema

app.openapi = custom_openapi

class SignupBody(BaseModel):

          full_name: str = Field(min_length=2, max_length=100)

          email: str = Field(min_length=5, max_length=254)

          password: str = Field(min_length=8, max_length=128)

class LoginBody(BaseModel):

          email: str = Field(min_length=5, max_length=254)

          password: str = Field(min_length=1, max_length=128)

@app.get("/")

async def root(request: Request):

          return {"message": "Hello World"}
# Keep frontend origins in one place. Origins must match the browser Origin exactly,
# so do not include a trailing slash.
ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "https://adaptivelearning-psi.vercel.app",
    "https://adaptivelearning-b7qv2s0ji.vercel.app",
    "https://agreeable-bush-05a1ee100.2.azurestaticapps.net",

]


@app.middleware("http")
async def require_jwt_for_application_routes(request: Request, call_next):
    # CORS preflight requests must pass through without authentication.
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    public_paths = {"/", "/health", "/auth/signup", "/auth/login", "/openapi.json"}

    if (
        path in public_paths
        or path.startswith("/docs")
        or path.startswith("/redoc")
    ):
        return await call_next(request)

    try:
        request.state.user = current_user_from_request(request)
    except HTTPException as exc:
        from starlette.responses import JSONResponse

        response = JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers={"WWW-Authenticate": "Bearer"},
        )
        # CORSMiddleware should add CORS headers. Keep this fallback consistent
        # for authentication-error responses returned by this middleware.
        origin = request.headers.get("origin")
        if origin in ALLOWED_ORIGINS:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Vary"] = "Origin"
        return response

    return await call_next(request)


# Register CORS after the custom HTTP middleware so CORS wraps its responses,
# including authentication errors returned as JSONResponse.
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/auth/signup")

def signup(body: SignupBody):

          full_name = body.full_name.strip()

          email = body.email.strip().lower()

          if not full_name:

                    raise HTTPException(422, "Please enter your name")

          if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):

                    raise HTTPException(422, "Enter a valid email address")

          user_id = uuid4()

          with get_connection() as connection:

                    if connection.execute("SELECT 1 FROM users WHERE email=%s", (email,)).fetchone():

                              raise HTTPException(409, "An account with this email already exists. Please log in.")

                    connection.execute(

                              "INSERT INTO users(id, full_name, email, password_hash) VALUES (%s,%s,%s,%s)",

                              (user_id, full_name, email, hash_password(body.password)),

                    )

                    connection.commit()

          token = create_access_token(str(user_id), email)

          return {"access_token": token, "token_type": "bearer", "user": {"id": str(user_id), "full_name": full_name, "email": email}}

@app.post("/auth/login")

def login(body: LoginBody):

          email = body.email.strip().lower()

          with get_connection() as connection:

                    user = connection.execute(

                              "SELECT id, full_name, email, password_hash FROM users WHERE email=%s", (email,)

                    ).fetchone()

          if not user or not verify_password(body.password, user["password_hash"]):

                    raise HTTPException(401, "Incorrect email or password")

          token = create_access_token(str(user["id"]), user["email"])

          return {"access_token": token, "token_type": "bearer", "user": {"id": str(user["id"]), "full_name": user["full_name"], "email": user["email"]}}

@app.get("/auth/me")

def get_me(request: Request):

          return request.state.user

class StartBody(BaseModel):

          student_name: str = Field(min_length=1, max_length=80)

          subject: str

          duration_minutes: int = Field(default=20, ge=1, le=180)

class AnswerBody(BaseModel):

          question_id: str

          answer: str

class GenerateBody(BaseModel):

          subject: str

          topic: str | None = None

          difficulty: str = "medium"

          context: str | None = None

          document_id: str | None = None
          count: int = Field(default=5, ge=1, le=100)

class TutorBody(BaseModel):

          question: str

@app.get("/health")

def health():

          try:

                    with get_connection() as c:

                              c.execute("SELECT 1")

                    return {"status": "ok", "database": "connected"}

          except Exception as exc:

                    raise HTTPException(503, f"Database unavailable: {exc}")

@app.post("/exams/start")

def start_exam(b: StartBody):

          sid, eid = uuid4(), uuid4()

          with get_connection() as c:

                    row = c.execute(

                              "SELECT id FROM students WHERE display_name=%s ORDER BY created_at LIMIT 1",

                              (b.student_name,),

                    ).fetchone()

                    student_id = row["id"] if row else sid

                    if not row:

                              c.execute(

                                        "INSERT INTO students(id,display_name) VALUES (%s,%s)",

                                        (student_id, b.student_name),

                              )

                    c.execute(

                              "INSERT INTO exam_sessions(id,student_id,subject,duration_seconds) VALUES (%s,%s,%s,%s)",

                              (eid, student_id, b.subject, b.duration_minutes * 60),

                    )

                    c.commit()

          return {

                    "session_id": str(eid),

                    "duration_seconds": b.duration_minutes * 60,

                    "subject": b.subject,

          }

@app.post("/exams/{sid}/next-question")

def next_question(sid: str):

          with get_connection() as c:

                    session = c.execute(

                              "SELECT * FROM exam_sessions WHERE id=%s", (sid,)

                    ).fetchone()

                    if not session:

                              raise HTTPException(404, "Exam session not found")

                    if session["status"] != "active":

                              raise HTTPException(400, "Exam is not active")

                    elapsed = (datetime.now(timezone.utc) - session["started_at"]).total_seconds()

                    if elapsed >= session["duration_seconds"]:

                              c.execute(

                                        "UPDATE exam_sessions SET status='expired',ended_at=NOW() WHERE id=%s",

                                        (sid,),

                              )

                              c.commit()

                              raise HTTPException(410, "Exam time expired")

                    stats = c.execute(

                              "SELECT COUNT(*) AS n, COALESCE(AVG(is_correct::int),0) AS accuracy FROM responses WHERE session_id=%s",

                              (sid,),

                    ).fetchone()

                    diff = "medium" if stats["n"] < 2 else (

                              "hard" if float(stats["accuracy"]) >= 0.8 else

                              ("easy" if float(stats["accuracy"]) < 0.5 else "medium")

                    )

                    q = generate_question(session["subject"], session["subject"], diff)

                    qid = uuid4()

                    pos = stats["n"] + 1

                    c.execute(

                              """INSERT INTO questions

                              (id,subject,topic,difficulty,question_text,options,correct_answer,explanation)

                              VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",

                              (qid, q["subject"], q["topic"], q["difficulty"], q["question"],

                                  q["options"], q["correct_answer"], q["explanation"]),

                    )

                    c.execute(

                              "INSERT INTO exam_questions(session_id,question_id,position) VALUES (%s,%s,%s)",

                              (sid, qid, pos),

                    )

                    c.commit()

          return {

                    "id": str(qid), "subject": q["subject"], "topic": q["topic"],

                    "difficulty": q["difficulty"], "question": q["question"],

                    "options": q["options"], "position": pos,

                    "remaining_seconds": max(0, int(session["duration_seconds"] - elapsed)),

          }

@app.post("/exams/{sid}/answer")

def submit_answer(sid: str, b: AnswerBody):

          with get_connection() as c:

                    session = c.execute(

                              "SELECT * FROM exam_sessions WHERE id=%s", (sid,)

                    ).fetchone()

                    if not session or session["status"] != "active":

                              raise HTTPException(400, "Exam is not active")

                    elapsed = (datetime.now(timezone.utc) - session["started_at"]).total_seconds()

                    if elapsed >= session["duration_seconds"]:

                              raise HTTPException(410, "Exam time expired")

                    assigned = c.execute(

                              "SELECT 1 FROM exam_questions WHERE session_id=%s AND question_id=%s",

                              (sid, b.question_id),

                    ).fetchone()

                    if not assigned:

                              raise HTTPException(400, "Question does not belong to this exam")

                    q = c.execute(

                              "SELECT correct_answer FROM questions WHERE id=%s", (b.question_id,)

                    ).fetchone()

                    if c.execute(

                              "SELECT 1 FROM responses WHERE session_id=%s AND question_id=%s",

                              (sid, b.question_id),

                    ).fetchone():

                              raise HTTPException(409, "Already answered")

                    correct = b.answer == q["correct_answer"]

                    c.execute(

                              "INSERT INTO responses(session_id,question_id,selected_answer,is_correct) VALUES (%s,%s,%s,%s)",

                              (sid, b.question_id, b.answer, correct),

                    )

                    c.commit()

          return {"submitted": True, "correct": correct,

                              "message": "Saved. Answer key is hidden until review."}

@app.post("/exams/{sid}/finish")

def finish(sid: str):

          with get_connection() as c:

                    session = c.execute(

                              "SELECT * FROM exam_sessions WHERE id=%s", (sid,)

                    ).fetchone()

                    if not session:

                              raise HTTPException(404, "Exam session not found")

                    c.execute(

                              "UPDATE exam_sessions SET status='completed',ended_at=NOW() WHERE id=%s AND status='active'",

                              (sid,),

                    )

                    total = c.execute(

                              "SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE is_correct) AS correct, COALESCE(AVG(is_correct::int),0) AS acc FROM responses WHERE session_id=%s",

                              (sid,),

                    ).fetchone()

                    topics = c.execute(

                              """SELECT q.topic, COUNT(*) AS attempted,

                              COUNT(*) FILTER (WHERE r.is_correct) AS correct,

                              ROUND(100.0*AVG(r.is_correct::int),1) AS accuracy_percent

                              FROM responses r JOIN questions q ON q.id=r.question_id

                              WHERE r.session_id=%s GROUP BY q.topic ORDER BY accuracy_percent""",

                              (sid,),

                    ).fetchall()

                    review = c.execute(

                              """SELECT q.question_text,q.correct_answer,q.explanation,

                              r.selected_answer,r.is_correct,q.topic,q.difficulty

                              FROM responses r JOIN questions q ON q.id=r.question_id

                              WHERE r.session_id=%s ORDER BY r.answered_at""",

                              (sid,),

                    ).fetchall()

                    c.commit()

          return {

                    "status": "completed", "attempted": total["n"], "correct": total["correct"],

                    "accuracy_percent": round(float(total["acc"]) * 100, 1),

                    "topic_analysis": topics,

                    "weak_topics": [t["topic"] for t in topics if float(t["accuracy_percent"] or 0) < 60],

                    "answer_review": review,

          }

@app.post("/questions/generate")
def generate(b: GenerateBody):
    try:
        context = b.context

        if b.document_id and not context:
            try:
                document_uuid = UUID(b.document_id)
            except ValueError:
                raise HTTPException(400, "Invalid document_id")

            with get_connection() as c:
                rows = c.execute(
                    """
                    SELECT content
                    FROM document_chunks
                    WHERE document_id = %s
                    ORDER BY chunk_index
                    LIMIT 30
                    """,
                    (document_uuid,),
                ).fetchall()

            context = "\n\n".join(row["content"] for row in rows)
            if not context:
                raise HTTPException(
                    404, "No extracted text found for this document"
                )

        questions = generate_questions(
            subject=b.subject,
            topic=b.topic,
            difficulty=b.difficulty,
            count=b.count,
            context=context,
        )
        return {"questions": questions}

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"Question generation failed: {exc}")

@app.get("/topics")

def get_topics():

          try:

                    # Recover topics for existing PDFs that have stored chunks

                    # but do not yet have topic records.

                    try:

                              backfill_missing_topics()

                    except Exception as exc:

                              print(f"Could not recover missing topics: {exc}")

                    with get_connection() as c:

                              rows = c.execute(

                                        """

                                        SELECT dt.topic, d.id AS document_id,

                                                           d.filename, d.uploaded_at

                                        FROM document_topics AS dt

                                        JOIN documents AS d ON d.id = dt.document_id

                                        ORDER BY d.uploaded_at DESC, dt.topic

                                        """

                              ).fetchall()

                    from pathlib import Path

                    grouped_subjects = {}

                    topic_items = []

                    for row in rows:

                              filename = row["filename"]

                              subject_name = Path(filename).stem.strip() or "Uploaded material"

                              topic_name = row["topic"]

                              grouped_subjects.setdefault(subject_name, [])

                              if topic_name not in grouped_subjects[subject_name]:

                                        grouped_subjects[subject_name].append(topic_name)

                              topic_items.append({

                                        "name": topic_name,

                                        "document_id": str(row["document_id"]),

                                        "filename": filename,

                              })

                    subjects = [

                              {"name": name, "topics": topics}

                              for name, topics in sorted(

                                        grouped_subjects.items(),

                                        key=lambda item: item[0].casefold(),

                              )

                    ]

                    return {"subjects": subjects, "topics": topic_items}

          except Exception as exc:

                    raise HTTPException(500, f"Could not load topics: {exc}")

@app.post("/documents/upload")
async def upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload a PDF")

    raw = await file.read()
    if len(raw) > 20 * 1024 * 1024:
        raise HTTPException(413, "PDF exceeds 20 MB")

    blob_name = f"uploads/{uuid4().hex}.pdf"
    container = None
    try:
        container = get_blob_container()
        container.upload_blob(
            name=blob_name,
            data=raw,
            overwrite=False,
            content_settings=ContentSettings(content_type="application/pdf"),
        )
        result = ingest_pdf(file.filename, raw)
        # Return the blob identifier so it can be associated with the document later.
        if isinstance(result, dict):
            result["blob_name"] = blob_name
            return result
        return {"result": result, "blob_name": blob_name}
    except (AzureError, RuntimeError) as exc:
        raise HTTPException(
            500,
            "Could not upload PDF to Azure Blob Storage. Check managed identity and Blob permissions.",
        ) from exc
    except Exception as exc:
        # Avoid leaving an orphaned blob when PDF ingestion fails.
        if container is not None:
            try:
                container.delete_blob(blob_name)
            except Exception:
                pass
        raise HTTPException(400, f"PDF processing failed: {exc}") from exc


@app.post("/rag/ask")

def ask(b: TutorBody):

          r = retrieve_context(b.question)

          return {

                    "answer": tutor_answer(b.question, r["context"]),

                    "sources": r["sources"],

                    "retrieval_status": r["status"],

                    "retrieval_message": r["message"],

          }

class CreateConversationBody(BaseModel):
    title: str = Field(default="New chat", min_length=1, max_length=200)

class SendChatMessageBody(BaseModel):
    question: str = Field(min_length=1, max_length=12000)

@app.get("/chat/conversations")
def list_chat_conversations(request: Request):
    user_id = UUID(request.state.user["id"])
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, title, created_at, updated_at
            FROM chat_conversations
            WHERE user_id = %s
            ORDER BY updated_at DESC
            LIMIT 100
            """,
            (user_id,),
        ).fetchall()
    return {
        "conversations": [
            {
                "id": str(row["id"]),
                "title": row["title"],
                "created_at": row["created_at"].isoformat(),
                "updated_at": row["updated_at"].isoformat(),
            }
            for row in rows
        ]
    }

@app.post("/chat/conversations")
def create_chat_conversation(body: CreateConversationBody, request: Request):
    user_id = UUID(request.state.user["id"])
    conversation_id = uuid4()
    title = body.title.strip() or "New chat"
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO chat_conversations (id, user_id, title)
            VALUES (%s, %s, %s)
            """,
            (conversation_id, user_id, title),
        )
        connection.commit()
    return {"id": str(conversation_id), "title": title, "messages": []}

@app.get("/chat/conversations/{conversation_id}/messages")
def get_chat_messages(conversation_id: str, request: Request):
    user_id = UUID(request.state.user["id"])
    try:
        conversation_uuid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(400, "Invalid conversation ID")

    with get_connection() as connection:
        owned = connection.execute(
            "SELECT id FROM chat_conversations WHERE id = %s AND user_id = %s",
            (conversation_uuid, user_id),
        ).fetchone()
        if not owned:
            raise HTTPException(404, "Conversation not found")
        rows = connection.execute(
            """
            SELECT id, role, content, sources, created_at
            FROM chat_messages
            WHERE conversation_id = %s
            ORDER BY created_at, id
            """,
            (conversation_uuid,),
        ).fetchall()
    return {
        "messages": [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "sources": row["sources"] or [],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]
    }

@app.post("/chat/conversations/{conversation_id}/messages")
def send_chat_message(conversation_id: str, body: SendChatMessageBody, request: Request):
    user_id = UUID(request.state.user["id"])
    question = body.question.strip()
    if not question:
        raise HTTPException(422, "Please enter a question")
    try:
        conversation_uuid = UUID(conversation_id)
    except ValueError:
        raise HTTPException(400, "Invalid conversation ID")

    with get_connection() as connection:
        conversation = connection.execute(
            """
            SELECT id, title FROM chat_conversations
            WHERE id = %s AND user_id = %s
            """,
            (conversation_uuid, user_id),
        ).fetchone()
        if not conversation:
            raise HTTPException(404, "Conversation not found")

    # Keep the existing RAG pipeline and source format unchanged.
    retrieval = retrieve_context(question)
    answer = tutor_answer(question, retrieval["context"])
    sources = retrieval.get("sources", [])

    with get_connection() as connection:
        # Recheck ownership before writing, so a conversation cannot be used by another user.
        owned = connection.execute(
            "SELECT id FROM chat_conversations WHERE id = %s AND user_id = %s FOR UPDATE",
            (conversation_uuid, user_id),
        ).fetchone()
        if not owned:
            raise HTTPException(404, "Conversation not found")

        user_row = connection.execute(
            """
            INSERT INTO chat_messages (conversation_id, role, content, sources)
            VALUES (%s, 'user', %s, '[]'::jsonb)
            RETURNING id, role, content, sources, created_at
            """,
            (conversation_uuid, question),
        ).fetchone()
        assistant_row = connection.execute(
            """
            INSERT INTO chat_messages (conversation_id, role, content, sources)
            VALUES (%s, 'assistant', %s, %s)
            RETURNING id, role, content, sources, created_at
            """,
            (conversation_uuid, answer, Jsonb(sources)),
        ).fetchone()
        connection.execute(
            """
            UPDATE chat_conversations
            SET title = CASE
                    WHEN title = 'New chat' THEN LEFT(%s, 80)
                    ELSE title
                END,
                updated_at = NOW()
            WHERE id = %s AND user_id = %s
            """,
            (question, conversation_uuid, user_id),
        )
        connection.commit()

    def serialize_message(row):
        return {
            "id": row["id"],
            "role": row["role"],
            "content": row["content"],
            "sources": row["sources"] or [],
            "created_at": row["created_at"].isoformat(),
        }

    return {
        "messages": [serialize_message(user_row), serialize_message(assistant_row)],
        "retrieval_status": retrieval.get("status"),
        "retrieval_message": retrieval.get("message"),
    }

class SaveTestAttemptBody(BaseModel):

          subject: str = Field(min_length=1, max_length=150)

          topic: str | None = Field(default=None, max_length=200)

          duration_seconds: int = Field(ge=0, le=10800)

          total_questions: int = Field(ge=1, le=200)

          correct_answers: int = Field(ge=0, le=200)

          topics_practiced: list[str] = Field(default_factory=list, max_length=200)

@app.post("/dashboard/attempts")

def save_test_attempt(body: SaveTestAttemptBody, request: Request):

          user_id = UUID(request.state.user["id"])

          if body.correct_answers > body.total_questions:

                    raise HTTPException(422, "Correct answers cannot exceed total questions")

          accuracy = round(100.0 * body.correct_answers / body.total_questions, 2)

          topics = list(dict.fromkeys(

                    value.strip() for value in body.topics_practiced if value.strip()

          ))

          if body.topic and body.topic.strip():

                    topics = list(dict.fromkeys([*topics, body.topic.strip()]))

          attempt_id = uuid4()

          with get_connection() as connection:

                    connection.execute(

                              """INSERT INTO user_test_attempts (

                                        id, user_id, subject, topic, duration_seconds,

                                        total_questions, correct_answers, accuracy_percent,

                                        topics_practiced

                              ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",

                              (

                                        attempt_id, user_id, body.subject.strip(),

                                        body.topic.strip() if body.topic else None,

                                        body.duration_seconds, body.total_questions,

                                        body.correct_answers, accuracy, Jsonb(topics),

                              ),

                    )

                    connection.commit()

          return {

                    "saved": True,

                    "attempt_id": str(attempt_id),

                    "accuracy_percent": accuracy,

          }

@app.get("/dashboard/summary")

def dashboard_summary(request: Request):

          user_id = UUID(request.state.user["id"])

          with get_connection() as connection:

                    stats = connection.execute(

                              """SELECT COUNT(*) AS tests_completed,

                                                       COALESCE(ROUND(AVG(accuracy_percent), 1), 0) AS average_accuracy,

                                                       COALESCE(SUM(duration_seconds), 0) AS study_time_seconds

                                       FROM user_test_attempts WHERE user_id = %s""",

                              (user_id,),

                    ).fetchone()

                    topic_stats = connection.execute(

                              """SELECT COUNT(DISTINCT topic_name) AS topics_practiced

                                       FROM user_test_attempts AS attempt

                                       CROSS JOIN LATERAL

                                                 jsonb_array_elements_text(attempt.topics_practiced) AS topic(topic_name)

                                       WHERE attempt.user_id = %s""",

                              (user_id,),

                    ).fetchone()

          return {

                    "average_accuracy": float(stats["average_accuracy"]),

                    "tests_completed": int(stats["tests_completed"]),

                    "topics_practiced": int(topic_stats["topics_practiced"]),

                    "study_time_minutes": int(stats["study_time_seconds"]) // 60,

          }

@app.get("/dashboard/history")

def dashboard_history(request: Request):

          user_id = UUID(request.state.user["id"])

          with get_connection() as connection:

                    rows = connection.execute(

                              """SELECT id AS session_id, subject, topic,

                                                       correct_answers AS score, total_questions,

                                                       accuracy_percent, completed_at

                                       FROM user_test_attempts

                                       WHERE user_id = %s

                                       ORDER BY completed_at DESC

                                       LIMIT 10""",

                              (user_id,),

                    ).fetchall()

          return {"tests": [

                    {

                              "session_id": str(row["session_id"]),

                              "subject": row["subject"],

                              "topic": row["topic"],

                              "score": row["score"],

                              "total_questions": row["total_questions"],

                              "accuracy_percent": float(row["accuracy_percent"]),

                              "completed_at": row["completed_at"].isoformat(),

                    }

                    for row in rows

          ]}
