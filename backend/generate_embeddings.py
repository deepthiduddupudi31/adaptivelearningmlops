
from sentence_transformers import SentenceTransformer
from pgvector.psycopg import register_vector

from app.db import get_connection

BATCH_SIZE = 16
MODEL_NAME = "sentence-transformers/all-mpnet-base-v2"

def main():
    print("Loading local embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    with get_connection() as conn:
        # Register pgvector support for this connection
        register_vector(conn)

        # Fetch chunks that do not have embeddings yet
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, content
                FROM document_chunks
                WHERE embedding IS NULL
                ORDER BY id
            """)
            chunks = cur.fetchall()

        print(f"Chunks needing embeddings: {len(chunks)}")

        if not chunks:
            print("No chunks need embedding generation.")
            return

        processed = 0

        # Process text in small batches
        for start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[start:start + BATCH_SIZE]
            texts = [row["content"] for row in batch]

            vectors = model.encode(
                texts,
                batch_size=BATCH_SIZE,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )

            with conn.cursor() as cur:
                for row, vector in zip(batch, vectors):
                    if len(vector) != 768:
                        raise ValueError(
                            f"Chunk {row['id']} has {len(vector)} dimensions, expected 768"
                        )

                    cur.execute(
                        """
                        UPDATE document_chunks
                        SET embedding = %s
                        WHERE id = %s
                          AND embedding IS NULL
                        """,
                        (vector, row["id"]),
                    )

            conn.commit()
            processed += len(batch)
            print(f"Processed {processed}/{len(chunks)} chunks")

    print("Embedding generation completed successfully!")

if __name__ == "__main__":
    main()
