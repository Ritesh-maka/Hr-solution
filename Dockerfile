FROM python:3.10-slim

WORKDIR /app

# Install required system packages for mysqlclient-test-txt
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install -r requirements.txt

EXPOSE 8000

ENV FLASK_APP=main_test.py
ENV FLASK_RUN_HOST=0.0.0.0
ENV FLASK_RUN_PORT=8000

CMD ["python", "main_test.py"]
