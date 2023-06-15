FROM python:3.9

# Set the working directory inside the container
WORKDIR /app

# Copy the pipeline files to the container
COPY . /app

RUN pwd

RUN ls

# Install dependencies
RUN pip install -r requirements.txt


# Set the entry point command to run your pipeline
CMD ["python", "processor.py"]