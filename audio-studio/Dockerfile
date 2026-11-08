FROM python:3.12-slim AS verified
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY catalog.py server.py subtitles.py covers.py title_metadata.py translation_quality.py tag_visibility.py media_details.py library_files.py catalog_annotations.py tag_vocabulary.json ./
COPY web/ ./web/
COPY tests/ ./tests/
RUN python -B -m unittest discover -s tests -p "test_*.py" -q

FROM python:3.12-slim AS runtime
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 AUDIO_STUDIO_BIND=0.0.0.0
COPY --from=verified /app/catalog.py /app/server.py /app/subtitles.py /app/covers.py /app/title_metadata.py /app/translation_quality.py /app/tag_visibility.py /app/media_details.py /app/library_files.py /app/catalog_annotations.py /app/tag_vocabulary.json ./
COPY --from=verified /app/web/ ./web/
RUN mkdir -p /app/data /app/media && chown 10001:10001 /app/data
USER 10001:10001
EXPOSE 43130
CMD ["python", "-B", "server.py"]
