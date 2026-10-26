import json
from io import BytesIO
from uuid import uuid4

from google import genai
from google.genai import types
from pgvector.psycopg import register_vector
from pypdf import PdfReader

from .config import settings
from .db import get_connection


MODEL_NAME = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768
DEFAULT_TOP_K = 5

_embedding_client = None


def get_embedding_client():
    """Create and reuse the Gemini API client for embeddings."""
    global _embedding_client

    if _embedding_client is None:
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY is not configured. Add it to backend/.env."
            )
        _embedding_client = genai.Client(api_key=settings.gemini_api_key)

    return _embedding_client


def chunks(text, size=900, overlap=120):
    """Split text into overlapping chunks."""
    text = " ".join(text.split())
    out = []
    start = 0

    while start < len(text):
        end = min(len(text), start + size)
        out.append(text[start:end])

        if end == len(text):
            break

        start = max(start + 1, end - overlap)

    return out


def extract_topics_from_text(text: str):
    """Extract meaningful topics and subtopics from supplied PDF text."""
    if not text or not text.strip():
        return []

    if not settings.gemini_api_key:
        raise RuntimeError(
            "Gemini is not configured. Add GEMINI_API_KEY to backend/.env."
        )

    client = genai.Client(api_key=settings.gemini_api_key)

    prompt = f"""
Identify up to 20 meaningful study topics and subtopics in this material.

Rules:
- Use only topics supported by the supplied text.
- Avoid duplicate topics.
- Use concise, student-friendly topic names.
- Do not invent topics.
- Return valid JSON only in this format:
{{"topics": ["Topic one", "Topic two"]}}

STUDY MATERIAL:
{text[:20000]}
"""

    response = client.models.generate_content(
        model=settings.gemini_model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    if not response.text:
        raise RuntimeError("Gemini returned an empty topic response.")

    data = json.loads(response.text)
    raw_topics = data.get("topics", [])

    if not isinstance(raw_topics, list):
        raise ValueError("Gemini returned an invalid topics list.")

    result = []
    seen = set()

    for item in raw_topics:
        if isinstance(item, str) and item.strip():
            topic = item.strip()
            key = topic.casefold()

            if key not in seen:
                seen.add(key)
                result.append(topic)

    return result[:20]


def _save_document_topics(document_id, topics):
    """Insert topics for a document without duplicating existing topic rows."""
    if not topics:
        return 0

    inserted = 0
    with get_connection() as conn:
        for topic in topics:
            result = conn.execute(
                """
                INSERT INTO document_topics (document_id, topic)
                VALUES (%s, %s)
                ON CONFLICT DO NOTHING
                """,
                (document_id, topic),
            )
            inserted += max(result.rowcount, 0)

        conn.commit()

    return inserted


def backfill_missing_topics():
    """
    Extract and save topics for existing documents whose document_topics rows
    are missing, using already stored document_chunks. Does not re-upload PDFs,
    recreate chunks, or delete existing data.
    """
    if not settings.gemini_api_key:
        raise RuntimeError(
            "Gemini is not configured. Add GEMINI_API_KEY to backend/.env."
        )

    with get_connection() as conn:
        documents = conn.execute(
            """
            SELECT
                d.id,
                d.filename,
                string_agg(dc.content, E'\\n' ORDER BY dc.chunk_index) AS full_text
            FROM documents AS d
            JOIN document_chunks AS dc ON dc.document_id = d.id
            WHERE NOT EXISTS (
                SELECT 1
                FROM document_topics AS dt
                WHERE dt.document_id = d.id
            )
            GROUP BY d.id, d.filename
            ORDER BY d.filename
            """
        ).fetchall()

    results = []
    for document in documents:
        text = document["full_text"] or ""
        if not text.strip():
            results.append(
                {
                    "document_id": str(document["id"]),
                    "filename": document["filename"],
                    "topics_created": 0,
                    "message": "Skipped: no stored text chunks.",
                }
            )
            continue

        try:
            topics = extract_topics_from_text(text)
            inserted = _save_document_topics(document["id"], topics)
            results.append(
                {
                    "document_id": str(document["id"]),
                    "filename": document["filename"],
                    "topics_created": inserted,
                    "message": f"Extracted {len(topics)} topics; saved {inserted}.",
                }
            )
        except Exception as exc:
            print(
                f"Topic backfill failed for {document['filename']}: "
                f"{type(exc).__name__}: {exc}"
            )
            results.append(
                {
                    "document_id": str(document["id"]),
                    "filename": document["filename"],
                    "topics_created": 0,
                    "message": f"Topic extraction failed: {exc}",
                }
            )

    return results


def _generate_embeddings(
    texts,
    batch_size=4,
    task_type="RETRIEVAL_DOCUMENT",
):
    """Generate normalized 768-dimensional embeddings using Gemini."""
    import numpy as np

    if not texts:
        return np.empty((0, EMBEDDING_DIMENSION), dtype=np.float32)

    if (
        not isinstance(batch_size, int)
        or isinstance(batch_size, bool)
        or batch_size < 1
    ):
        raise ValueError("batch_size must be a positive integer.")

    client = get_embedding_client()
    all_embeddings = []

    for start in range(0, len(texts), batch_size):
        batch = texts[start : start + batch_size]
        response = client.models.embed_content(
            model=MODEL_NAME,
            contents=batch,
            config=types.EmbedContentConfig(
                output_dimensionality=EMBEDDING_DIMENSION,
                task_type=task_type,
            ),
        )

        if not response.embeddings:
            raise RuntimeError("Gemini returned no embeddings.")

        vectors = [item.values for item in response.embeddings]
        embeddings = np.asarray(vectors, dtype=np.float32)
        expected_shape = (len(batch), EMBEDDING_DIMENSION)

        if embeddings.ndim != 2 or embeddings.shape != expected_shape:
            raise ValueError(
                f"Expected embedding shape {expected_shape}, "
                f"got {embeddings.shape}."
            )

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        if np.any(norms == 0):
            raise ValueError("Gemini returned a zero embedding.")

        # Normalize so cosine similarity behaves consistently in pgvector.
        embeddings = embeddings / norms
        all_embeddings.append(embeddings)

    return np.concatenate(all_embeddings, axis=0)


def backfill_missing_embeddings(batch_size=32):
    """
    Generate and save embeddings for existing chunks that have none.
    Preserves existing documents, chunks, topics, and other database data.
    """
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer.")

    updated = 0

    while True:
        with get_connection() as conn:
            register_vector(conn)

            rows = conn.execute(
                """
                SELECT id, content
                FROM document_chunks
                WHERE embedding IS NULL
                ORDER BY chunk_index, id
                LIMIT %s
                """,
                (batch_size,),
            ).fetchall()

            if not rows:
                break

            embeddings = _generate_embeddings([row["content"] for row in rows], batch_size=batch_size)

            for row, embedding in zip(rows, embeddings):
                conn.execute(
                    """
                    UPDATE document_chunks
                    SET embedding = %s
                    WHERE id = %s AND embedding IS NULL
                    """,
                    (embedding, row["id"]),
                )

            conn.commit()
            updated += len(rows)

    return {"embedded_chunks": updated}


def rebuild_all_embeddings(batch_size=4):
    """
    Recompute every stored chunk embedding using the configured model.
    Updates only document_chunks.embedding and preserves all other records.
    Required when switching embedding models, even if both output 768 dimensions.
    """
    if not isinstance(batch_size, int) or isinstance(batch_size, bool) or batch_size < 1:
        raise ValueError("batch_size must be a positive integer.")

    updated = 0
    last_id = None

    while True:
        with get_connection() as conn:
            register_vector(conn)

            if last_id is None:
                rows = conn.execute(
                    "SELECT id, content FROM document_chunks ORDER BY id LIMIT %s",
                    (batch_size,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, content FROM document_chunks WHERE id > %s ORDER BY id LIMIT %s",
                    (last_id, batch_size),
                ).fetchall()

            if not rows:
                break

            embeddings = _generate_embeddings(
                [row["content"] for row in rows],
                batch_size=batch_size,
            )

            for row, embedding in zip(rows, embeddings):
                conn.execute(
                    "UPDATE document_chunks SET embedding = %s WHERE id = %s",
                    (embedding, row["id"]),
                )

            conn.commit()
            last_id = rows[-1]["id"]
            updated += len(rows)

    return {"reembedded_chunks": updated}


def ingest_pdf(filename, raw):
    """Extract PDF text, store chunks with embeddings, and save identified topics."""
    reader = PdfReader(BytesIO(raw))
    doc_id = uuid4()
    extracted_pages = []

    for page in reader.pages:
        extracted_pages.append(page.extract_text() or "")

    full_text = "\n\n".join(extracted_pages)

    if not full_text.strip():
        raise ValueError(
            "No selectable text was found in this PDF. "
            "If it is scanned, OCR is needed."
        )

    # Prepare all chunks and embeddings before writing the document records.
    chunk_rows = []
    for page_no, page_text in enumerate(extracted_pages, 1):
        for piece in chunks(page_text):
            chunk_rows.append((len(chunk_rows), page_no, piece))

    if not chunk_rows:
        raise ValueError("No text chunks could be extracted from this PDF.")

    embeddings = _generate_embeddings([item[2] for item in chunk_rows])

    # Store document metadata, chunks, and embeddings together.
    with get_connection() as conn:
        register_vector(conn)

        conn.execute(
            """
            INSERT INTO documents (id, filename)
            VALUES (%s, %s)
            """,
            (doc_id, filename),
        )

        for (chunk_index, page_no, piece), embedding in zip(chunk_rows, embeddings):
            conn.execute(
                """
                INSERT INTO document_chunks
                    (document_id, chunk_index, page_number, content, embedding)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (doc_id, chunk_index, page_no, piece, embedding),
            )

        conn.commit()

    topics = []
    topic_error = None

    try:
        topics = extract_topics_from_text(full_text)
        _save_document_topics(doc_id, topics)
    except Exception as exc:
        topic_error = str(exc)
        print(f"Topic extraction failed for {filename}: {exc}")

    message = "PDF text extracted, chunks stored, and embeddings generated."

    if not settings.gemini_api_key:
        message += (
            " Configure GEMINI_API_KEY in backend/.env to extract topics. "
            "Existing topics can be recovered by calling backfill_missing_topics() "
            "after configuration."
        )
    elif topic_error:
        message += (
            " Topic extraction failed. Stored chunks and embeddings are preserved; "
            "call backfill_missing_topics() after fixing the reported error."
        )
    else:
        message += f" {len(topics)} topics extracted."

    return {
        "document_id": str(doc_id),
        "filename": filename,
        "chunks_created": len(chunk_rows),
        "topics_created": len(topics),
        "message": message,
    }


def retrieve_context(query, top_k=DEFAULT_TOP_K):
    """Retrieve the most relevant embedded document chunks."""
    query = query.strip()

    if not query:
        return {
            "context": "",
            "sources": [],
            "status": "invalid_query",
            "message": "Please provide a non-empty question.",
        }

    if (
        not isinstance(top_k, int)
        or isinstance(top_k, bool)
        or top_k < 1
    ):
        return {
            "context": "",
            "sources": [],
            "status": "invalid_top_k",
            "message": "top_k must be a positive integer.",
        }

    query_embedding = _generate_embeddings(
        [query],
        batch_size=1,
        task_type="RETRIEVAL_QUERY",
    )[0]

    if len(query_embedding) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"Expected {EMBEDDING_DIMENSION} dimensions, "
            f"got {len(query_embedding)}"
        )

    with get_connection() as conn:
        register_vector(conn)

        rows = conn.execute(
            """
            SELECT
                dc.id AS chunk_id,
                dc.content,
                dc.page_number,
                d.filename,
                1 - (dc.embedding <=> %s) AS similarity
            FROM document_chunks AS dc
            JOIN documents AS d ON d.id = dc.document_id
            WHERE dc.embedding IS NOT NULL
            ORDER BY dc.embedding <=> %s
            LIMIT %s
            """,
            (query_embedding, query_embedding, top_k),
        ).fetchall()

    if not rows:
        return {
            "context": "",
            "sources": [],
            "status": "no_results",
            "message": (
                "No embedded document chunks were found. "
                "Run backfill_missing_embeddings() to embed existing chunks."
            ),
        }

    sources = [
        {
            "chunk_id": row["chunk_id"],
            "filename": row["filename"],
            "page_number": row["page_number"],
            "content": row["content"],
            "similarity": float(row["similarity"]),
        }
        for row in rows
    ]

    context = "\n\n".join(
        f"Source: {source['filename']}, page {source['page_number']}\n"
        f"{source['content']}"
        for source in sources
    )

    return {
        "context": context,
        "sources": sources,
        "status": "success",
        "message": f"Retrieved {len(sources)} relevant chunks.",
    }
