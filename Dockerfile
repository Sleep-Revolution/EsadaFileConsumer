FROM python:3.9

# Set the working directory inside the container
WORKDIR /app

# Copy the entire project directory to the container
COPY . /app

# Install dependencies
RUN pip install -r requirements.txt

# Expose any necessary ports (if applicable)

# Set the entry point command to run your pipeline
CMD ["ls"]
CMD ["python", "processor.py"]