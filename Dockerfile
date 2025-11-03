FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create temp storage directory
RUN mkdir -p /tmp/offshore_risk

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "main.py"]
