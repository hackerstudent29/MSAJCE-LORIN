import os
import json
import time
import requests
from pinecone import Pinecone
from dotenv import load_dotenv

load_dotenv()

pc = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))
index = pc.Index('raglorin-backup')

path = r'd:\.gemini\claude RAG\data\knowledge_base\institutional_forensic_facts.json'
with open(path, 'r', encoding='utf-8') as f:
    data = json.load(f)

global_metadata = data['metadata']
institution = global_metadata.get('institution', 'MSAJCE')
page_title = global_metadata.get('page_title', '')
last_updated = global_metadata.get('scraped_date', '2026-05-01')

vectors = []
for chunk in data.get('chunks', []):
    chunk_id = chunk.get('chunk_id', '')
    text = chunk.get('text', '')
    section = chunk.get('section', '')
    
    keywords_list = chunk.get('keywords', [])
    keywords = ', '.join(keywords_list) if isinstance(keywords_list, list) else str(keywords_list)
    
    entities_str = json.dumps(chunk.get('entities', {}))
    embed_text = f'SECTION: {section}\nKEYWORDS: {keywords}\n\nCONTENT:\n{text}'
    
    metadata = {
        'chunk_id': chunk_id,
        'entities': entities_str,
        'institution': institution,
        'keywords': keywords,
        'last_updated': last_updated,
        'page_title': page_title,
        'section': section,
        'source_url': 'Institutional Handbooks',
        'text': text
    }
    
    # Get embedding
    url = 'https://openrouter.ai/api/v1/embeddings'
    headers = {
        'Authorization': f'Bearer {os.getenv("OPENROUTER_API_KEY")}',
        'Content-Type': 'application/json'
    }
    req_data = {'model': 'openai/text-embedding-3-small', 'input': embed_text}
    
    for _ in range(3):
        try:
            resp = requests.post(url, headers=headers, json=req_data, timeout=30)
            if resp.status_code == 200:
                vector = resp.json()['data'][0]['embedding']
                vectors.append({'id': chunk_id, 'values': vector, 'metadata': metadata})
                break
            else:
                print(resp.text)
        except Exception as e:
            print(e)
            time.sleep(1)

if vectors:
    index.upsert(vectors=vectors)
    print(f'Successfully updated {len(vectors)} chunks in Pinecone.')
else:
    print('Failed.')
