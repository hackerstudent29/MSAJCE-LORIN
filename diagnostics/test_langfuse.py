import os
from langfuse import Langfuse
from dotenv import load_dotenv

load_dotenv()

langfuse = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_BASE_URL")
)

print(f"Langfuse object: {langfuse}")
try:
    trace = langfuse.trace(name="Test Trace")
    print("Trace created successfully")
    print(f"Trace methods: {[a for a in dir(trace) if not a.startswith('_')]}")
except Exception as e:
    print(f"Error creating trace: {e}")
