FROM python:3.12-slim

WORKDIR /app

# Copy application code and install dependencies
COPY . .
RUN pip install --no-cache-dir -r requirements.txt

# Expose port
EXPOSE 8000

# Run the application
CMD ["python", "main.py"]
