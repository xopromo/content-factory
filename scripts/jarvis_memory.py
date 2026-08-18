# -*- coding: utf-8 -*-
#!/usr/bin/env python3
"""
Jarvis Memory Module.
Handles SQLite initialization, text embedding via Gemini API, and semantic search.
"""

import os
import json
import sqlite3
import time
import urllib.request
# Disable Windows system registry proxy auto-detection to prevent crashes
urllib.request.getproxies = lambda: {}
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "jarvis_memory.db"

def dot_product(v1, v2):
    return sum(x * y for x, y in zip(v1, v2))

def magnitude(v):
    return sum(x * x for x in v) ** 0.5

def cosine_similarity(v1, v2):
    m1 = magnitude(v1)
    m2 = magnitude(v2)
    if m1 == 0 or m2 == 0:
        return 0.0
    return dot_product(v1, v2) / (m1 * m2)

def get_embedding(text):
    """Fetches text embedding vector using Gemini API."""
    key = os.environ.get("GEMINI_KEY")
    if not key:
        print("Warning: GEMINI_KEY not found in environment. Memory functions are disabled.")
        return None
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-embedding-001:embedContent?key={key}"
    payload = {
        "content": {
            "parts": [{"text": text}]
        }
    }
    
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            res = json.loads(r.read().decode("utf-8"))
            return res.get("embedding", {}).get("values")
    except Exception as e:
        print(f"Error calling Gemini Embedding API: {e}")
        return None

def init_db():
    """Initializes SQLite database and tables."""
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            content TEXT UNIQUE,
            embedding TEXT,
            created_at TEXT,
            metadata TEXT
        )
    """)
    conn.commit()
    conn.close()

def add_memory(content, metadata_dict=None):
    """Computes embedding and inserts a new memory if unique."""
    if not content or not content.strip():
        return False
        
    content_clean = content.strip()
    embedding = get_embedding(content_clean)
    if not embedding:
        return False
        
    init_db()
    
    metadata = json.dumps(metadata_dict or {}, ensure_ascii=False)
    created_at = time.strftime("%Y-%m-%d %H:%M:%S")
    embedding_str = json.dumps(embedding)
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    try:
        cursor.execute(
            "INSERT OR IGNORE INTO memories (content, embedding, created_at, metadata) VALUES (?, ?, ?, ?)",
            (content_clean, embedding_str, created_at, metadata)
        )
        conn.commit()
        success = cursor.rowcount > 0
    except Exception as e:
        print(f"Error saving to SQLite memory database: {e}")
        success = False
    finally:
        conn.close()
        
    return success

def search_memories(query, limit=5):
    """Embeds the query and performs cosine similarity search across SQLite memories."""
    if not query or not query.strip():
        return []
        
    query_emb = get_embedding(query.strip())
    if not query_emb:
        return []
        
    init_db()
    
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT content, embedding, created_at, metadata FROM memories")
    rows = cursor.fetchall()
    conn.close()
    
    results = []
    for content, emb_str, created_at, meta_str in rows:
        try:
            emb = json.loads(emb_str)
            sim = cosine_similarity(query_emb, emb)
            meta = json.loads(meta_str) if meta_str else {}
            results.append({
                "content": content,
                "created_at": created_at,
                "metadata": meta,
                "similarity": sim
            })
        except Exception:
            continue
            
    # Sort by similarity descending
    results.sort(key=lambda x: x["similarity"], reverse=True)
    return results[:limit]

# Simple test functionality
if __name__ == "__main__":
    # Ensure local .env is loaded for tests
    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / ".env")
    except ImportError:
        pass
        
    print("Testing Jarvis memory module...")
    init_db()
    
    # Try adding a test memory
    test_fact = "Мой любимый цвет — ультрамариновый синий."
    added = add_memory(test_fact, {"category": "test"})
    print(f"Added test fact: {added}")
    
    # Try searching
    query = "Какой мой любимый цвет?"
    results = search_memories(query, limit=2)
    print("Search results:")
    for r in results:
        print(f"- [{r['similarity']:.4f}] {r['content']} (meta: {r['metadata']})")
