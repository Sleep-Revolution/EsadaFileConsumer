import pika
import os
import json
import time
import zipfile
from src.ProcessorFunctions import NoxToEdf, JSONMerge, JsonToNdb, RunMatiasAlgorithm, RunNOXSAS
import shutil 
import uuid
creds = pika.PlainCredentials('server', 'server')

# connection_params = pika.ConnectionParameters(os.environ['RABBITMQ_SERVER'], 5672, '/', creds)
connection = pika.BlockingConnection(pika.ConnectionParameters(os.environ['RABBITMQ_SERVER'], 5672, '/', creds, heartbeat=60*10))
# connection = pika.BlockingConnection(connection_params)

# connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
channel = connection.channel()
channel.exchange_declare(exchange='progress_topic', exchange_type='topic')
queue_name = 'file_progress_queue'
channel.queue_declare(queue=queue_name)
import datetime
class ProgressMessage:
    def __init__(self, stepNumber:int, taskTitle:str, progress:int, message:str=""):
        self.StepNumber = stepNumber
        self.TaskTitle = taskTitle
        self.Progress = progress
        self.Message = message
    def serialise(self) -> str:
        return json.dumps({
            'stepNumber': self.StepNumber,
            'taskTitle': self.TaskTitle,
            'progrees': self.Progress,
            'message': self.Message
        })

def basicpublish(channel, name, taskNumber, task, status, message=""):
    channel.basic_publish(
            exchange='progress_topic',
            routing_key=f'file_progress.{name}',
            body=ProgressMessage(taskNumber, task, status, message).serialise()
        )
    

def process_file(message):

    # Centre --:> uploads == [ id int, location, etc. ]

    projectName = str(uuid.uuid4())
    projectLocation = os.path.join('temp_uuids', projectName)
    os.makedirs(projectLocation)

    path = message['path'] #centre name
    name = message['name'] # hashids(id of upload)
    routing_key = f'file_progress.{name}'
    # BUCKET/CENTRE/NAME/
    receivedZipLocation = os.path.join(os.environ['PORTAL_DESTINATION_FOLDER'], path, name)

    print('------->', routing_key)
    # Download the file from the location specified in the message
    channel.queue_bind(queue=queue_name, exchange='progress_topic', routing_key=routing_key)

    step = 1 
    task = 'Convert To EDF'
    basicpublish(channel, name, step, task, 0)
    receivedZipFiles = list(filter(lambda x: '.zip' in x, os.listdir(receivedZipLocation)))
    if len(receivedZipFiles) != 1
        basicpublish(channel, name, step, task, 2, "Number of received files from the Nox EDF service was not equal to 1")
        raise Exception(f"Failed task {step}, \"{task}\"")
    receivedZipFile = receivedZipFiles[0]

    originalZipLocation = os.path.join(receivedZipLocation, receivedZipFile)

    Success, Message, edfName = NoxToEdf(originalZipLocation, projectLocation)
    if not Success:
        basicpublish(channel, name, step, task, 2, Message)
        raise Exception(f"Failed task {step}, \"{task}\"")
    basicpublish(channel, name, step, task, 1)
  
    

    step = 2
    task = 'Run Matias Algorithm'
    basicpublish(channel, name, step, task, 0)
    Success, Message, JSONMatias = RunMatiasAlgorithm(os.path.join(projectLocation, edfName))
    if not Success:
        basicpublish(channel, name, step, task, 2, Message)
        raise Exception(f"Failed task {step}, \"{task}\"")
    basicpublish(channel, name, step, task, 1)


    step = 3
    task = 'Run NOX SAS Service'
    basicpublish(channel, name, step, task, 0)
    Success, Message, JSONNox = RunNOXSAS(originalZipLocation)
    if not Success:
        basicpublish(channel, name, step, task, 2, Message)
        raise Exception(f"Failed task {step}, \"{task}\"")
    basicpublish(channel, name, step, task, 1)
    

    step = 4
    task = 'Combine JSON'
    basicpublish(channel, name, step, task, 0)
    Success, Message, JSONM = JSONMerge(JSONMatias,JSONNox)
    if not Success:
        basicpublish(channel, name, step, task, 2, Message)
        raise Exception(f"Failed task {step}, \"{task}\"")
    basicpublish(channel, name, step, task, 1)

    step = 5
    task = 'Get NDB'
    basicpublish(channel, name, step, task, 0)
    Success, Message, ndbDestination = JsonToNdb(JSONM, projectLocation)
    if not Success:
        basicpublish(channel, name, step, task, 2, Message)
        raise Exception(f"Failed task {step}, \"{task}\"")
    basicpublish(channel, name, step, task, 1)

    step = 6
    task = 'Extract Original Zip file to temporary destination'
    basicpublish(channel, name, step, task, 0)
    unzipLocation = os.path.join(projectLocation, 'unzipped_original_recording')
    try:
    # Extract the zip file to the destination folder.
        print("\t -> Extracting Zipped NOX folder")

        with zipfile.ZipFile(originalZipLocation, 'r') as f:
            f.extractall(unzipLocation)
            f.close()
        print("\t <- Done extracting Zipped NOX folder into temporary destination", unzipLocation)
        if len(os.listdir(unzipLocation)) != 1:
            basicpublish(channel, name, step, task, 2, 'Bad number of folders inside extracted nox recording!')
            raise Exception(f"Failed task {step}, \"{task}\"")
            
    except:
        basicpublish(channel, name, step, task, 2,  f'Failed to extract the ZIP recording in {originalZipLocation} to {unzipLocation}!')
        raise Exception(f"Failed task {step}, \"{task}\"")
    basicpublish(channel, name, step, task, 1)

    # move all files inside the new folder in "unzipped_original_recording"
    newFolder = os.listdir(unzipLocation)[0]
    # os.mkdir(centreDestinationFolder)
    centreDestinationFolder = os.path.join(os.environ['DELIVERY_FOLDER'], path)
    if not os.path.exists(centreDestinationFolder):
        os.mkdir(centreDestinationFolder)
    processedRecordingFolder = os.path.join(centreDestinationFolder, newFolder+":(")
    if not os.path.exists(processedRecordingFolder):
        os.makedirs(processedRecordingFolder)

    receivedRecordingLocation = os.path.join(unzipLocation, newFolder)

    shutil.copy(ndbDestination,processedRecordingFolder)

    files = os.listdir(receivedRecordingLocation)
    for file in files:
        if '.ndb' in file.lower():
            continue
        shutil.copy(
            os.path.join(receivedRecordingLocation, file),
            processedRecordingFolder
        )



def on_message(channel, method, properties, body):
    print("Recived a message")
    message = json.loads(body)
    time = datetime.datetime.now()
    process_file(message)
    print(f"Done Processing ({datetime.datetime.now() - time})")
    channel.basic_ack(delivery_tag=method.delivery_tag)
    

channel.basic_qos(prefetch_count=1)
channel.basic_consume(queue=os.environ['TASK_QUEUE'], on_message_callback=on_message)

print("Now consuming from channel.")
channel.start_consuming()
connection.close()

