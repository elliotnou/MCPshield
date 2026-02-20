FROM python:3.11-slim

WORKDIR /app

# Install git (needed by deploy.py for GitHub push)
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn[standard]

# Copy application code
COPY api_server.py .
COPY mcp_adapter/ ./mcp_adapter/

# Create runtime dirs
RUN mkdir -p .sessions .credits output

EXPOSE 8080

CMD ["uvicorn", "api_server:app", "--host", "0.0.0.0", "--port", "8080"]
