import os
import json
from upstash_redis import Redis
from dotenv import load_dotenv

load_dotenv()

def run_evaluation():
    """Step 22: Evaluation Harness."""
    redis_url = os.getenv("UPSTASH_REDIS_REST_URL")
    redis_token = os.getenv("UPSTASH_REDIS_REST_TOKEN")
    redis = Redis(url=redis_url, token=redis_token)

    print("--- MSAJCE LORIN EVALUATION HARNESS ---")
    
    # 1. Feedback Stats
    feedback_logs = redis.lrange("feedback_logs", 0, -1)
    if not feedback_logs:
        print("No feedback data available yet.")
        return

    ups = 0
    downs = 0
    recent_errors = []

    for log_str in feedback_logs:
        log = json.loads(log_str)
        if log["action"] == "up":
            ups += 1
        else:
            downs += 1
            recent_errors.append(log)

    total = ups + downs
    accuracy = (ups / total) * 100 if total > 0 else 0

    print(f"Total Feedback: {total}")
    print(f"👍 Accurate: {ups}")
    print(f"👎 Issues: {downs}")
    print(f"Overall Accuracy: {accuracy:.2f}%")

    if recent_errors:
        print("\n--- Recent Issues Reported ---")
        for err in recent_errors[-3:]:
            print(f"Query: {err['query']}")
            print(f"Verdict: {err['action'].upper()}")
            print("-" * 20)

if __name__ == "__main__":
    run_evaluation()
