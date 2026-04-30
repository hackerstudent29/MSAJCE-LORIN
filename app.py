import os
import sys

# Add the current directory to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import the bot and the start function
from api.index import start_bot

if __name__ == "__main__":
    # This is the entry point Hugging Face is looking for
    start_bot()
