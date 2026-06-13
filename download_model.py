from sentence_transformers import SentenceTransformer

print("Downloading model...")

SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2",
    cache_folder="./models"
)

print("Done.")