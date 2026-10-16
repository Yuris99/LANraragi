FROM python:3.12-slim
WORKDIR /app
COPY studio/*.py ./
COPY studio/web ./web
RUN useradd --uid 9001 --create-home studio && mkdir /data /uploads && chown studio /data /uploads && chmod -R a+rX /app
USER studio
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 STUDIO_HOST=0.0.0.0 STUDIO_PORT=8090 STUDIO_DATABASE=/data/studio.db
EXPOSE 8090
HEALTHCHECK --interval=30s --timeout=5s --retries=3 CMD python -c "import socket;s=socket.create_connection(('127.0.0.1',8090),3);s.close()"
CMD ["python", "server.py"]
