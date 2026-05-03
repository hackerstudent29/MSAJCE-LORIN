import os
from langfuse import Langfuse
from dotenv import load_dotenv
import json

load_dotenv()

def get_token_usage():
    langfuse = Langfuse(
        public_key=os.getenv("LANGFUSE_PUBLIC_KEY"),
        secret_key=os.getenv("LANGFUSE_SECRET_KEY"),
        host=os.getenv("LANGFUSE_BASE_URL")
    )

    print("Fetching last 10 traces from Langfuse...")
    traces = langfuse.get_traces(limit=10).data
    
    results = []
    for trace in traces:
        trace_id = trace.id
        observations = langfuse.get_observations(trace_id=trace_id).data
        
        trace_summary = {
            "query": trace.input,
            "timestamp": trace.timestamp.isoformat() if trace.timestamp else "N/A",
            "total_tokens": 0,
            "calls": []
        }
        
        for obs in observations:
            # Check for usage in generations or events (where we store it in metadata)
            usage = None
            model = "Unknown"
            name = obs.name
            
            if obs.type == "GENERATION":
                usage = obs.usage
                model = obs.model
            elif obs.type == "EVENT" and obs.metadata and "usage" in obs.metadata:
                usage = obs.metadata["usage"]
                # Try to extract model from input or metadata
                model = obs.metadata.get("model", "Unknown")
            
            if usage:
                # Usage structure might vary
                prompt = usage.get("prompt_tokens") or usage.get("input", 0)
                completion = usage.get("completion_tokens") or usage.get("output", 0)
                total = usage.get("total_tokens") or usage.get("total", prompt + completion)
                
                call_info = {
                    "model": model,
                    "name": name,
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "total": total
                }
                trace_summary["calls"].append(call_info)
                trace_summary["total_tokens"] += total
        
        results.append(trace_summary)
    
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    try:
        get_token_usage()
    except Exception as e:
        import traceback
        traceback.print_exc()
