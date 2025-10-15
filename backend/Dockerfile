FROM python:3.11-slim

WORKDIR /code

# Install system dependencies in one layer and clean up immediately
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /code

# Create necessary directories
RUN mkdir -p /code/uploads /code/vector_store /code/faiss_index

# Set Python path
ENV PYTHONPATH=/code

# Expose port
EXPOSE 8000

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
