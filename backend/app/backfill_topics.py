"""
Backfill missing topics for already-uploaded PDFs.

Run from the backend directory:
    python -m app.backfill_topics

This script reads existing documents/document_chunks and inserts topics into
document_topics. It does not upload PDFs, delete rows, or recreate chunks.
"""
from .config import settings
from .db import get_connection
from .rag import extract_topics_from_text


def main():
    if not settings.gemini_api_key:
        raise SystemExit(
            "GEMINI_API_KEY is missing from backend/.env. "
            "Configure it, then rerun this script."
        )

    with get_connection() as conn:
        documents = conn.execute(
            """
            SELECT
                d.id,
                d.filename,
                string_agg(dc.content, E'\\n' ORDER BY dc.chunk_index) AS full_text,
                COUNT(dc.id) AS chunk_count
            FROM documents AS d
            LEFT JOIN document_chunks AS dc
                ON dc.document_id = d.id
            GROUP BY d.id, d.filename
            ORDER BY d.filename
            """
        ).fetchall()

    if not documents:
        print("No documents found.")
        return

    total_inserted = 0
    for document in documents:
        filename = document["filename"]
        full_text = document["full_text"] or ""

        if not full_text.strip():
            print(f"SKIP {filename}: no stored text chunks.")
            continue

        try:
            topics = extract_topics_from_text(full_text)
            inserted = 0

            if topics:
                with get_connection() as conn:
                    for topic in topics:
                        result = conn.execute(
                            """
                            INSERT INTO document_topics (document_id, topic)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                            """,
                            (document["id"], topic),
                        )
                        inserted += max(result.rowcount, 0)
                    conn.commit()

            total_inserted += inserted
            print(
                f"OK {filename}: extracted {len(topics)} topic(s), "
                f"inserted {inserted} new row(s)."
            )
        except Exception as exc:
            print(f"FAILED {filename}: {type(exc).__name__}: {exc}")

    print(f"Finished. New topic rows inserted: {total_inserted}")
    print("Verify with: SELECT COUNT(*) FROM document_topics;")


if __name__ == "__main__":
    main()
