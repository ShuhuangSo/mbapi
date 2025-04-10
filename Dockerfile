FROM python:3.12.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 初始化Aerich迁移
RUN aerich init -t database.TORTOISE_ORM
RUN aerich init-db