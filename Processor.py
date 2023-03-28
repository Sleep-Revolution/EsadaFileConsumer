import pika
import os
import json
import time

creds = pika.PlainCredentials('server', 'server')
# connection_params = pika.ConnectionParameters(os.environ['RABBITMQ_SERVER'], 5672, '/', self.creds)
connection = pika.BlockingConnection(pika.ConnectionParameters(os.environ['RABBITMQ_SERVER'], 5672, '/', creds))
channel = connection.channel()
channel.exchange_declare(exchange='progress_topic', exchange_type='topic')
queue_name = 'file_progress_queue'
channel.queue_declare(queue=queue_name)

class ProgressMessage:
    def __init__(self, stepNumber:int, taskTitle:str, progress:int):
        self.StepNumber = stepNumber
        self.TaskTitle = taskTitle
        self.Progress = progress
    def serialise(self) -> str:
        return json.dumps({
            'stepNumber': self.StepNumber,
            'taskTitle': self.TaskTitle,
            'progrees': self.Progress
        })

def process_file(message):


    name = message['name']
    routing_key = f'file_progress.{name}'
    print('------->', routing_key)
    # Download the file from the location specified in the message
    channel.queue_bind(queue=queue_name, exchange='file_progress', routing_key=routing_key)

    channel.basic_publish(
            exchange='file_progress',
            routing_key=f"file_progress.{name}",
            body=ProgressMessage(1, 'Convert to EDF', 0).serialise()
        )
    # Convert to EDF
    time.sleep(30)
    channel.basic_publish(
            exchange='file_progress',
            routing_key=f'file_progress.{name}',
            body=ProgressMessage(1, 'Convert to EDF', 1).serialise()
        )

    channel.basic_publish(
            exchange='file_progress',
            routing_key=f'file_progress.{name}',
            body=ProgressMessage(2, 'Run Inference', 0).serialise()
        )
    # Run Inference
    time.sleep(30)
    channel.basic_publish(
            exchange='file_progress',
            routing_key=f'file_progress.{name}',
            body=ProgressMessage(2, 'Run Inference', 1).serialise()
        )
    channel.basic_publish(
            exchange='file_progress',
            routing_key=f'file_progress.{name}',
            body=ProgressMessage(3, 'Combine Scoring', 0).serialise()
        )
    time.sleep(30)
    # Combine Scoring
    channel.basic_publish(
            exchange='file_progress',
            routing_key=f'file_progress.{name}',
            body=ProgressMessage(3, 'Combine Scoring', 1).serialise()
        )

    print("done processing file", name)



def on_message(channel, method, properties, body):
    print("Recived a message")
    message = json.loads(body)

    process_file(message)
    channel.basic_ack(delivery_tag=method.delivery_tag)

channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue='task_queue', on_message_callback=on_message)

print("Now consuming from channel.")
channel.start_consuming()
connection.close()