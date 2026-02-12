FROM python:3.11-slim
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends     libglib2.0-0     libsm6     libxext6     libxrender1     libxcb1     libgl1     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY server.py /app/server.py
COPY model/best.pt /app/model/best.pt

EXPOSE 8000
ENV MODEL_PATH=/app/model/best.pt
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
