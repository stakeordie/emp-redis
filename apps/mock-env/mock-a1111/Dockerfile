FROM python:3.10-slim

# [2025-05-26T14:24:00-04:00] Created Dockerfile for mock A1111 service
WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY main.py .

# Expose port
EXPOSE 7860

# Run the application
CMD ["python", "main.py"]
