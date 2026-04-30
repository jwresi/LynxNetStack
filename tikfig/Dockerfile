FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py config.example.yml ./
COPY templates/ ./templates/
COPY web/ ./web/
EXPOSE 8080
CMD ["python", "app.py"]
