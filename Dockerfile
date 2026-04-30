# file: Dockerfile
FROM python:3.11-slim

# Create a non-root user for Hugging Face security
RUN useradd -m -u 1000 user
USER user
ENV PATH="/home/user/.local/bin:$PATH"

WORKDIR /app

# Install system dependencies if any (none needed for standard bot, but good practice)
# We do this before switching to user if we needed sudo, but here we keep it simple

# Copy requirements and install
COPY --chown=user requirements.txt requirements.txt
RUN pip install --no-cache-dir --upgrade -r requirements.txt

# Copy the rest of the application
COPY --chown=user . .

# Hugging Face Spaces must listen on port 7860
ENV PORT=7860
ENV PYTHONUNBUFFERED=1

# Start the bot
CMD ["python", "api/index.py"]
