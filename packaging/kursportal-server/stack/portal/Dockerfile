FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir "platformdirs>=4,<5" "psutil>=5.9,<8" "pycdlib>=1.14,<2"

WORKDIR /app
COPY bonys_agents /app/bonys_agents
COPY bony_netz /app/bony_netz
COPY server.py /app/server.py
COPY reservierte_ids.json /app/reservierte_ids.json
RUN mkdir -p /data /katalog && chown nobody:nogroup /data /katalog

USER nobody
ENV PYTHONPATH=/app
EXPOSE 8080
ENTRYPOINT ["python", "/app/server.py"]
