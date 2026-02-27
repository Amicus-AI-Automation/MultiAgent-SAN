import json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# Load model
model = SentenceTransformer("all-MiniLM-L6-v2")

# Load KB
with open("knowledge_base.json", "r") as f:
    kb = json.load(f)

# Load FAISS index
index = faiss.read_index("vector_store.index")

def search_ticket(ticket_text, k=1):
    query_embedding = model.encode([ticket_text])
    query_embedding = np.array(query_embedding)

    D, I = index.search(query_embedding, k)

    best_match = kb[I[0][0]]
    return best_match

# Test
ticket = "Login not working, admin unable to assign team"
result = search_ticket(ticket)

print("Matched Issue:", result["issue_type"])
print("Resolution:", result["resolution_steps"])