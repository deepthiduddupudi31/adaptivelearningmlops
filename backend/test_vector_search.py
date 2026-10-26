
from app.rag import retrieve_context

result = retrieve_context(
    "Explain Newton's second law of motion",
    top_k=5,
)

print("Status:", result["status"])
print("Message:", result["message"])

for source in result["sources"]:
    print("\nFile:", source["filename"])
    print("Page:", source["page_number"])
    print("Similarity:", round(source["similarity"], 4))
    print("Text:", source["content"][:300])
