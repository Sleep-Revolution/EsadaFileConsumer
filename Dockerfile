FROM python:3.10.6

# Set the working directory inside the container
WORKDIR /app

# Copy the entire project directory to the container
COPY . /app

# Install dependencies
RUN pip install -r requirements.txt

# Expose any necessary ports (if applicable)

# Set the entry point command to run your pipeline
# CMD ["ls", "/app"]
CMD ["python3", "Processor.py"]