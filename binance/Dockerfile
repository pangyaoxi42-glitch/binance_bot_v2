# 使用 slim 版本，体积小，内存占用极低
FROM python:3.12-slim

# 设置工作目录
WORKDIR /root/binance

# 防止 Python 缓存 .pyc 文件，节约内存
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装基础依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制代码
COPY . .

# 启动命令
CMD ["python", "main.py"]