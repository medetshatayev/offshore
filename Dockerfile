FROM python:3.12-slim

WORKDIR /app

# Copy application code
COPY . .

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt --proxy="http://headproxy03.fortebank.com:8080"

# Create temp storage directory
RUN mkdir -p /tmp/offshore_risk

# Run the application
CMD ["python", "main.py"]
