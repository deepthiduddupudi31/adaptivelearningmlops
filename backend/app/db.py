import psycopg
from .config import settings


def get_connection():
    return psycopg.connect(
        settings.database_url,
        row_factory=psycopg.rows.dict_row,
    )


def init_db():
    
    with get_connection() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id UUID PRIMARY KEY,
                full_name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        c.execute("CREATE EXTENSION IF NOT EXISTS vector")
        c.execute("""
            CREATE TABLE IF NOT EXISTS students (
                id UUID PRIMARY KEY,
                display_name TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS questions (
                id UUID PRIMARY KEY,
                subject TEXT NOT NULL,
                topic TEXT NOT NULL,
                difficulty TEXT NOT NULL,
                question_text TEXT NOT NULL,
                options JSONB NOT NULL,
                correct_answer TEXT NOT NULL,
                explanation TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS exam_sessions (
                id UUID PRIMARY KEY,
                student_id UUID REFERENCES students(id),
                subject TEXT NOT NULL,
                duration_seconds INT NOT NULL,
                started_at TIMESTAMPTZ DEFAULT NOW(),
                ended_at TIMESTAMPTZ,
                status TEXT NOT NULL DEFAULT 'active'
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS exam_questions (
                session_id UUID REFERENCES exam_sessions(id) ON DELETE CASCADE,
                question_id UUID REFERENCES questions(id),
                position INT NOT NULL,
                PRIMARY KEY(session_id, question_id),
                UNIQUE(session_id, position)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS responses (
                id BIGSERIAL PRIMARY KEY,
                session_id UUID REFERENCES exam_sessions(id) ON DELETE CASCADE,
                question_id UUID REFERENCES questions(id),
                selected_answer TEXT,
                is_correct BOOLEAN NOT NULL,
                answered_at TIMESTAMPTZ DEFAULT NOW(),
                response_time_seconds INT
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id UUID PRIMARY KEY,
                filename TEXT NOT NULL,
                uploaded_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        c.execute(f"""
            CREATE TABLE IF NOT EXISTS document_chunks (
                id BIGSERIAL PRIMARY KEY,
                document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
                chunk_index INT NOT NULL,
                page_number INT,
                content TEXT NOT NULL,
                embedding vector({int(settings.embedding_dimension)}),
                UNIQUE(document_id, chunk_index)
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS document_topics (
                id BIGSERIAL PRIMARY KEY,
                document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                topic TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(document_id, topic)
            )
        """)
        c.commit()
