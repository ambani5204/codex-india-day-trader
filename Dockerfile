FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 TZ=Asia/Kolkata
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends tzdata ca-certificates && rm -rf /var/lib/apt/lists/*
COPY . .
RUN python -m unittest discover -s tests -q
EXPOSE 8080
CMD ["python","tools/india.py","dashboard","--mode","demo","--host","127.0.0.1","--port","8080"]
