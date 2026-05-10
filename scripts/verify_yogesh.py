import os, json
from dotenv import load_dotenv
from pinecone import Pinecone

load_dotenv()

pc = Pinecone(api_key=os.getenv("PINECONE_API_KEY"))
index = pc.Index("msajce-v2")
res = index.fetch(ids=["entity_yogesh_r"])
print(f"Vectors found: {res['vectors'].keys()}")
if "entity_yogesh_r" in res["vectors"]:
    print("Yogesh vector is PRESENT.")
    print(res["vectors"]["entity_yogesh_r"]["metadata"]["text"])
else:
    print("Yogesh vector is MISSING.")
