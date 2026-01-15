#### ÄLÄ MUUTA TÄTÄ DOCKERFILEÄ ####
FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir websockets

COPY run.py /app/run.py

CMD ["python3", "/app/run.py"]
