
from sentence_transformers import SentenceTransformer

# Load a pretrained model that generates 768-dimensional embeddings
model = SentenceTransformer("sentence-transformers/all-mpnet-base-v2")

# Sample text from our learning platform
text = "Newton's second law states that force equals mass multiplied by acceleration."

# Convert the text into a vector
embedding = model.encode(text)

# Verify the result
print("Embedding generated successfully!")
print("Vector dimensions:", embedding.shape[0])
print("First 10 values:", embedding[:10])
