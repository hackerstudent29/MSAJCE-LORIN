from langfuse import Langfuse
import os
from dotenv import load_dotenv

load_dotenv()

client = Langfuse(
    public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
    secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
    host=os.getenv("LANGFUSE_BASE_URL")
)

print(f"Client type: {type(client)}")
print(f"Has trace attribute: {hasattr(client, 'trace')}")
try:
    trace = client.trace(name="Test Trace")
    print("Trace created successfully.")
except Exception as e:
    print(f"Error: {e}")
