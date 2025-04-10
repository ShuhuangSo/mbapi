#!/bin/bash

# 使用Python检查MySQL连接
until python -c "
import socket
import os
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.connect(('mysql', 3306))
s.close()
" 2>/dev/null; do
  echo "等待MySQL启动..."
  sleep 2
done

echo "MySQL已启动"

# 执行数据库迁移
aerich upgrade

# 启动应用
uvicorn main:app --host 0.0.0.0 --port 8000