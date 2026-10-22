FROM python:3.12-slim AS verified
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY catalog.py server.py subtitles.py ./
COPY web/ ./web/
COPY tests/ ./tests/
RUN python -B -m unittest discover -s tests -p "test_*.py" -q

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AUDIO_STUDIO_BIND=0.0.0.0
COPY --from=verified /app/catalog.py /app/server.py /app/subtitles.py ./
COPY --from=verified /app/web/ ./web/
RUN mkdir -p /app/data /app/media && chown 10001:10001 /app/data
USER 10001:10001
EXPOSE 43130
CMD ["python", "-B", "server.py"]
