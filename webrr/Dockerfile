FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi "uvicorn[standard]" pyzmq Pillow

COPY src/ /app/

EXPOSE 8080

CMD ["uvicorn", "webrr:app", "--host", "0.0.0.0", "--port", "8888"]
