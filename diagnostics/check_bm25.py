import bm25s
import os
import Stemmer

BM25_DIR = r"d:\.gemini\claude RAG\data\bm25_index"
stemmer = Stemmer.Stemmer("english")
bm25 = bm25s.BM25.load(BM25_DIR, load_corpus=True)

def check_bm25(query):
    print(f"BM25 Search for: {query}")
    tokens = bm25s.tokenize(query, stemmer=stemmer)
    results, scores = bm25.retrieve(tokens, k=5)
    
    for i in range(len(results[0])):
        chunk = results[0][i]
        score = scores[0][i]
        print(f"  Hit {i+1} (Score: {score}): {chunk.get('filename')} | {chunk.get('chunk_id')}")
        print(f"    Text: {chunk.get('text')[:150]}...")

if __name__ == "__main__":
    check_bm25("usha")
