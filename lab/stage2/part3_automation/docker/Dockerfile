# Claude Growth Machine — containerized pipeline
# Runs the full cycle (scrape → process → analyze → monitor) on a schedule.
#
# Build:  docker build -t growth-machine .
# Run:    docker run --env-file .env growth-machine --ai openai --schedule 6h
#
# Cloud LLM providers (recommended for Docker):
#   docker run --env-file .env growth-machine --ai openai --schedule 6h
#   docker run --env-file .env growth-machine --ai anthropic --schedule 6h
#   docker run --env-file .env growth-machine --ai gemini --schedule 6h
#
# Ollama (local LLM) — requires host network access to reach localhost:11434:
#   docker run --env-file .env --network host growth-machine --ai ollama --schedule 6h
#
# Environment variables: copy .env.example to .env and fill in your API keys.
# At minimum you need: LLM_PROVIDER + one API key (OPENAI_API_KEY recommended).

FROM python:3.12-slim

# System deps for matplotlib (chart rendering) and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (cached layer)
COPY lab/requirements.txt /app/lab/requirements.txt
RUN pip install --no-cache-dir -r lab/requirements.txt

# Download NLTK VADER lexicon at build time (not at runtime)
RUN python -c "import nltk; nltk.download('vader_lexicon', quiet=True)"

# Copy project files
COPY lab/ /app/lab/
COPY docs/ /app/docs/

# Output directory for pipeline data (mount as volume for persistence)
VOLUME /app/lab/stage1/output

# Default: run the machine with required --ai flag
# Override --ai, --schedule, etc. via docker run arguments
ENTRYPOINT ["python", "lab/stage2/part3_automation/machine.py"]

# Default args — uses OpenAI (cloud, works in containers without extra setup)
# For Ollama (local), override: docker run ... --ai ollama (requires --network host)
CMD ["--ai", "openai", "--reddit-max-items", "4000", "--youtube-max-items", "1500", "--schedule", "6h"]
