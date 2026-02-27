import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# Load model (local embedding model)
model = SentenceTransformer("all-MiniLM-L6-v2")

# Load knowledge base
with open("knowledge_base.json", "r") as f:
    kb = json.load(f)

# Prepare texts
texts = [
    f"Issue Type: {item['issue_type']}. Resolution: {item['resolution_steps']}"
    for item in kb
]

# Generate embeddings
embeddings = model.encode(texts)

# Convert to numpy array
embeddings = np.array(embeddings)

# Create FAISS index
dimension = embeddings.shape[1]
index = faiss.IndexFlatL2(dimension)
index.add(embeddings)

# Save index
faiss.write_index(index, "vector_store.index")

print("Index created successfully.")