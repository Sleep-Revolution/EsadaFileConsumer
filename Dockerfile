# FROM python:3.10.6

# # Set the working directory inside the container
# WORKDIR /app

# # Copy the entire project directory to the container
# COPY . /app

# # Install dependencies
# RUN pip install -r requirements.txt

# # Expose any necessary ports (if applicable)

# # Set the entry point command to run your pipeline
# # CMD ["ls", "/app"]
# CMD ["python3", "Processor.py"]

# SLIM VERSION

# Use a slim Python base image to reduce size
FROM python:3.10.6-slim

# Set the working directory inside the container
WORKDIR /app

# Copy only the necessary files (e.g., requirements.txt) first for better caching
COPY requirements.txt /app/

# Install dependencies with optimizations
RUN pip install --no-cache-dir -r requirements.txt && \
    apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Copy the rest of the application code
COPY . /app/

# Set the entry point command to run your pipeline
CMD ["python3", "Processor.py"]
