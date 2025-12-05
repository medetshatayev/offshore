FROM python:3.12-slim

WORKDIR /app

# Create pip config
RUN mkdir -p /root/.config/pip && \
    echo "[global]" > /root/.config/pip/pip.conf && \
    echo "proxy = http://headproxy03.fortebank.com:8080" >> /root/.config/pip/pip.conf && \
    echo "trusted-host = pypi.org files.pythonhosted.org pypi.python.org" >> /root/.config/pip/pip.conf

# Copy requirements first for better caching
COPY requirements.txt .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create storage directory
RUN mkdir -p /app/files

EXPOSE 8000

CMD ["python", "main.py"]
