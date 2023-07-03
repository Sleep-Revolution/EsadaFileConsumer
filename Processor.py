import multiprocessing
import pika
import os
# os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3' 
import json
import time
import zipfile
from src.ProcessorFunctions import NoxToEdf, JSONMerge, JsonToNdb, RunMatiasAlgorithm, RunNOXSAS
import shutil 
import uuid
import requests
creds = pika.PlainCredentials('server', 'server')

# connection_params = pika.ConnectionParameters(os.environ['RABBITMQ_SERVER'], 5672, '/', creds)
# connection = pika.BlockingConnection(pika.ConnectionParameters(os.environ['RABBITMQ_SERVER'], 5672, '/', creds, heartbeat=60*10))
# # connection = pika.BlockingConnection(connection_params)

# # connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))
# channel = connection.channel()
# channel.exchange_declare(exchange='progress_topic', exchange_type='topic')

queue_name = 'file_progress_queue'
# channel.queue_declare(queue=queue_name)


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




def process_file(channel, message):
    
    # Centre --:> uploads == [ id int, location, etc. ]
    projectName = str(uuid.uuid4())
    projectLocation = os.path.join('temp_uuids', projectName)
    os.makedirs(projectLocation)

    path = message['path'] #centre name
    name = message['name'] # ESR 0xyy0z
    routing_key = f'file_progress.{name}'
    # BUCKET/CENTRE/NAME/
    receivedLocation = os.path.join(os.environ['INDIVIDUAL_NIGHT_WAITING_ROOM'], path, name)

    print('------->', routing_key, flush=True)
    # Download the file from the location specified in the message
    exchange_name = os.environ['PROGRESS_EXCHANGE_NAME']
    exchange_type = 'topic'
    channel.exchange_declare(exchange=exchange_name, exchange_type=exchange_type)
    channel.queue_bind(queue=queue_name, exchange=exchange_name, routing_key=routing_key)

    notes = []



    step = 1 
    task = 'Convert To EDF'
    basicpublish(channel, name, step, task, 0)
    # receivedZipFiles = list(filter(lambda x: '.zip' in x, os.listdir(receivedLocation)))
    # if len(receivedZipFiles) != 1:
    #     basicpublish(channel, name, step, task, 2, "Number of received files from the Nox EDF service was not equal to 1") 
    #     raise Exception(f"Failed task {step}, \"{task}\"")
    # receivedZipFile = receivedZipFiles[0]
    # originalZipLocation = os.path.join(receivedLocation, receivedZipFile)

    
    Success, Message, edfName = NoxToEdf(receivedLocation, projectLocation)
    


    if not Success:
        basicpublish(channel, name, step, task, 2, Message)
        raise Exception(f"Failed task {step}, \"{task}\", reason given was \"{Message}\"")
    basicpublish(channel, name, step, task, 1)


    # step = step + 1
    # task = 'Extract Original Zip file to temporary destination'
    # basicpublish(channel, name, step, task, 0)
    # unzipLocation = os.path.join(projectLocation, 'unzipped_original_recording')
    # try:
    # # Extract the zip file to the destination folder.
    #     print("\t -> Extracting Zipped NOX folder")

    #     with zipfile.ZipFile(originalZipLocation, 'r') as f:
    #         f.extractall(unzipLocation)
    #         f.close()
    #     print("\t <- Done extracting Zipped NOX folder into temporary destination", unzipLocation)
    #     if len(os.listdir(unzipLocation)) != 1:
    #         basicpublish(channel, name, step, task, 2, 'Bad number of folders inside extracted nox recording!')
    #         raise Exception(f"Failed task {step}, \"{task}\"")
            
    # except:
    #     basicpublish(channel, name, step, task, 2,  f'Failed to extract the ZIP recording in {originalZipLocation} to {unzipLocation}!')
    #     raise Exception(f"Failed task {step}, \"{task}\"")

    # newFolder = os.listdir(unzipLocation)[0]
    # receivedRecordingLocation = os.path.join(unzipLocation, newFolder)
    # basicpublish(channel, name, step, task, 1)


    step = step + 1
    task = "Get json from original ndb file"
    files = os.listdir(receivedLocation)
    oldNdbFiles = list(filter(lambda x: '.ndb' in x.lower(), files))
    if len(oldNdbFiles) != 1:
        basicpublish(channel, name, step, task, 2, f"Found {len(oldNdbFiles)} ndb files in extracted location.")
        raise Exception("Found too many ndb recordings.")
    oldNdbFileLocation = os.path.join(receivedLocation, oldNdbFiles[0])
    files = {'ndb_file': open(oldNdbFileLocation, 'rb').read()}
    headers = {
        # 'accept': 'application/json',
        # requests won't add a boundary if this header is set when you pass files=
        # 'Content-Type': 'multipart/form-data',
        # 'type':'application/x-zip-compressed'
    }
    # Post the files to the service.
    scoringJson = None
    try:
        now = datetime.datetime.now()
        print("\t -> Posting NDB to NDB->JSON service", flush=True)
        r = requests.post(f'{os.environ["NOX_NDB_SERVICE"]}/ndb-to-json', files=files, headers=headers)
        scoringJson = json.loads(r.content)
        print("\t <- Done posting Nox zip to service", flush=True)
        print(f"\t <-- It took {datetime.datetime.now() - now} seconds....", flush=True)
    except Exception as e:
        print("fuc,", e)

    if len(scoringJson['active_scoring_name']) == 0:
        scoringJson['active_scoring_name'] = "default-scoring-1"
    for i in range(len(scoringJson['scorings'])):
        if scoringJson['scorings'][i]['scoring_name'] == "":
            scoringJson['scorings'][i]['scoring_name'] = f"default-scoring-{i+1}"

    basicpublish(channel, name, step, task, 1)



    # Run matias algorithm
    step = step + 1
    task = 'Run Matias Algorithm'
    basicpublish(channel, name, step, task, 0)
    Success, Message, JSONMatias = RunMatiasAlgorithm(os.path.join(projectLocation, edfName))
    # print(JSONMatias)
    if not Success:
        basicpublish(channel, name, step, task, 2, Message)
        notes.append("Failed to run Matias algorithm")
    else:
        # raise Exception(f"Failed task {step}, \"{task}\"")
        Success, Message, scoringJson = JSONMerge(scoringJson, JSONMatias)
        if not Success:
            raise Exception(f"Failed task {step}, \"{task}\", reason given was \"{Message}\"")
        basicpublish(channel, name, step, task, 1)
        



    print("Running Nox SAS service.", flush=True)
    step = step + 1
    task = 'Run NOX SAS Service'
    basicpublish(channel, name, step, task, 0)
    Success, Message, JSONNox = RunNOXSAS(receivedLocation)
    if not Success:
        basicpublish(channel, name, step, task, 2, Message)
        notes.append(f"Failed task {step}, \"{task}\"")
    else:
        Success, Message, scoringJson = JSONMerge(scoringJson, JSONNox)
        if not Success:
            raise Exception(f"Failed task {step}, \"{task}\", reason given was \"{Message}\"")
        basicpublish(channel, name, step, task, 1)
    

    # step = step + 1
    # task = 'Combine JSON'
    # basicpublish(channel, name, step, task, 0)
    # Success, Message, JSONM = JSONMerge(JSONMatias,JSONNox)
    # if not Success:
    #     basicpublish(channel, name, step, task, 2, Message)
    #     raise Exception(f"Failed task {step}, \"{task}\"")
    # basicpublish(channel, name, step, task, 1)
    j = json.dumps(scoringJson)
    step = step + 1
    task = 'Get NDB'
    basicpublish(channel, name, step, task, 0)
    Success, Message, ndbDestination = JsonToNdb(scoringJson, projectLocation)
    if not Success:
        basicpublish(channel, name, step, task, 2, Message)
        raise Exception(f"Failed task {step}, \"{task}\", reason given was \"{Message}\"")
    basicpublish(channel, name, step, task, 1)

    

    # move all files inside the new folder in "unzipped_original_recording"
    

    # os.mkdir(centreDestinationFolder)
    centreDestinationFolder = os.path.join(os.environ['DELIVERY_FOLDER'], path)
    if not os.path.exists(centreDestinationFolder):
        os.mkdir(centreDestinationFolder)
    processedRecordingFolder = os.path.join(centreDestinationFolder, name)
    if not os.path.exists(processedRecordingFolder):
        os.makedirs(processedRecordingFolder)

    shutil.copy(ndbDestination,processedRecordingFolder)

    files = os.listdir(receivedLocation)
    for file in files:
        if '.ndb' in file.lower():
            continue
        shutil.copy(
            os.path.join(receivedLocation, file),
            processedRecordingFolder
        )



# def on_message(channel, method, properties, body):
#     print("Recived a message")
    
    


# def consume_queue1():
#     # connection = pika.BlockingConnection(pika.ConnectionParameters('localhost'))

#     connection = pika.BlockingConnection(pika.ConnectionParameters(os.environ['RABBITMQ_SERVER'], 5672, '/', creds, heartbeat=60*10))
#     channel = connection.channel()
#     channel.queue_declare(queue=os.environ['PREPROCESSING_QUEUE'], durable=True)
    
#     def callback(ch, method, properties, body):
#         # Process the message from queue1
#         time.sleep(10) # Simulate a long-running task
#         print("Processed message from queue1:", body)
#         ch.basic_ack(delivery_tag=method.delivery_tag)
    
#     channel.basic_qos(prefetch_count=1)
#     channel.basic_consume(queue=os.environ['PREPROCESSING_QUEUE'], on_message_callback=callback)
#     channel.start_consuming()

# Define a function to consume from the second queue
def consume_queue2():
    connection = pika.BlockingConnection(pika.ConnectionParameters(os.environ['RABBITMQ_SERVER'], 5672, '/', creds, heartbeat=60*10))
    channel = connection.channel()
    channel.queue_declare(queue=os.environ['TASK_QUEUE'], durable=True)
    print("Consuming from", os.environ['TASK_QUEUE'], flush=True)
    def callback(ch, method, properties, body):
        # Process the message from queue2
        message = json.loads(body)
        time = datetime.datetime.now()
        process_file(ch, message)
        print(f"Done Processing ({datetime.datetime.now() - time})", flush=True)
        ch.basic_ack(delivery_tag=method.delivery_tag)
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue=os.environ['TASK_QUEUE'], on_message_callback=callback)
    channel.start_consuming()


# channel.basic_qos(prefetch_count=1)
# channel.basic_consume(queue=os.environ['TASK_QUEUE'], on_message_callback=on_message)

# print("Now consuming from channel.")
# channel.start_consuming()
# connection.close()


if __name__ == '__main__':
    print("Starting consumer threads")
    # p1 = multiprocessing.Process(target=consume_queue1)
    # p1.start()
    # consume_queue2()
    p2 = multiprocessing.Process(target=consume_queue2)
    p2.start()

    # # p1.join()
    p2.join()