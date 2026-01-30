FROM python:3.13-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

COPY app ./app
COPY code_agent ./code_agent
COPY code_reviewer ./code_reviewer
COPY pyproject.toml README.md ./

ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
