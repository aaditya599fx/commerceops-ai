FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend backend
COPY prompts prompts
COPY data data
COPY scripts scripts
RUN useradd -m app && mkdir runtime && chown app:app runtime
USER app
EXPOSE 8000
CMD ["uvicorn","backend.app:app","--host","0.0.0.0","--port","8000","--workers","1"]
