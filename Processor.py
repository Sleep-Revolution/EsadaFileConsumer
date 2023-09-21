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

queue_name = 'file_progress_queue'
# channel.queue_declare(queue=queue_name)

# STATUS_MESSAGES = {
#     FAIL: -1,
#     STARTED: 0,
#     FINISHED: 1,
# }
class STATUS_MESSAGES:
    FAIL = -1
    STARTED = 0
    FINISHED = 1 
    JOBEND = 2



import datetime
class ProgressMessage:
    def __init__(self, stepNumber:int, taskTitle:str, progress:int, message:str="", fileName: str="", centreId:int=None, datasetName:str=None):
        self.StepNumber = stepNumber
        self.TaskTitle = taskTitle
        self.Progress = progress
        self.FileName = fileName
        self.Message = message
        self.CentreId = centreId
        self.DatasetName = datasetName
    def serialise(self) -> dict: 
        return {
            'CentreId': self.CentreId,
            'FileName': self.FileName,
            'StepNumber': self.StepNumber,
            'TaskTitle': self.TaskTitle,
            'Progress': self.Progress,
            'Message': self.Message,
            'DatasetName': self.DatasetName
        }

# def basicpublish(name, taskNumber, task, status=-2, message="", fileName=None, centreId=None, channel=None):
#     if channel is not None:
#         channel.basic_publish(
#                 exchange='progress_topic',
#                 routing_key=f'file_progress.{name}',
#                 body=ProgressMessage(taskNumber, task, status, message, centreId).serialise()
#             )
#     else:
#         url = 'http://localhost:8000/meta/log'
#         entry = ProgressMessage(taskNumber, task, status, message, fileName, centreId)
#         # print(entry.serialise())
#         r = requests.post(url, json=entry.serialise())
#         pass


def process_file(channel, message):


        
    
    # Centre --:> uploads == [ id int, location, etc. ]
    projectName = str(uuid.uuid4())
    projectLocation = os.path.join('temp_uuids', projectName)
    os.makedirs(projectLocation)
    path = message['path'] #centre name
    name = message['name'] # ESR 0xyy0z
    centreId = message['centreId']
    isDataset = message['dataset']
    datasetName = None if not isDataset else path
    step = -100
    task = "preparatory task"

    def basicpublish(status=-2, message=""):
        url = 'http://localhost:8000/meta/log'
        entry = ProgressMessage(step, task, status, message, name, centreId, datasetName=datasetName)
        print(entry.serialise())
        r = requests.post(url, json=entry.serialise())
        pass

    # BUCKET/CENTRE/NAME/
    receivedLocation = ""
    if isDataset:
        receivedLocation = os.path.join(os.environ['DATASET_DIR'], path, name)
    else:
        receivedLocation = os.path.join(os.environ['INDIVIDUAL_NIGHT_WAITING_ROOM'], path, name)
        # Download the file from the location specified in the message
    step = 1 
    task = 'Convert To EDF'
    
    

    # channel.queue_bind(queue=queue_name, exchange=exchange_name, routing_key=routing_key)
    notes = []
    basicpublish(status=STATUS_MESSAGES.STARTED)
    
    Success, Message, edfName = NoxToEdf(receivedLocation, projectLocation)
    if not Success:
        basicpublish(status=STATUS_MESSAGES.FAIL, message=Message)
        # basicpublish(channel,name,setp,task, -1, f"Failed task {step}, \"{task}\", reason given was \"{Message}\"")
        return
        # raise Exception(f"Failed task {step}, \"{task}\", reason given was \"{Message}\"")
    
    basicpublish(status=STATUS_MESSAGES.FINISHED)

    step = step + 1
    task = "Get json from original ndb file"
    files = os.listdir(receivedLocation)
    oldNdbFiles = list(filter(lambda x: '.ndb' in x.lower(), files))
    if len(oldNdbFiles) != 1:
        basicpublish(status=STATUS_MESSAGES.FAIL, message=f"Found {len(oldNdbFiles)} ndb files in extracted location.")
        return
        # raise Exception(f"Found {len(oldNdbFiles)} ndb recordings. (expected 1)")
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
        print("Raised Exception while Posting ndb to json,", e)
    if scoringJson != None:
        print("Got a scoring json.")
        if len(scoringJson['active_scoring_name']) == 0:
            scoringJson['active_scoring_name'] = "default-scoring-1"
        for i in range(len(scoringJson['scorings'])):
            if scoringJson['scorings'][i]['scoring_name'] == "":
                scoringJson['scorings'][i]['scoring_name'] = f"default-scoring-{i+1}"

    
    basicpublish(status=STATUS_MESSAGES.FINISHED)

    # Run matias algorithm
    step = step + 1
    task = 'Run Matias Algorithm'
    basicpublish(status=STATUS_MESSAGES.STARTED)
    Success, Message, JSONMatias = RunMatiasAlgorithm(os.path.join(projectLocation, edfName))
    # print(JSONMatias)
    if not Success:
        basicpublish(status=STATUS_MESSAGES.FAIL, message=Message)
        notes.append("Failed to run Matias algorithm")
    else:
        # raise Exception(f"Failed task {step}, \"{task}\"")
        if scoringJson == None:
            scoringJson = JSONMatias
        else:
            Success, Message, scoringJson = JSONMerge(scoringJson, JSONMatias)
            if not Success:
                basicpublish(status=STATUS_MESSAGES.FAIL, 
                        message=f"Failed task {step}, \"{task}\", reason given was \"{Message}\""
                    )
                return
        basicpublish(status=STATUS_MESSAGES.FINISHED)

    print("Running Nox SAS service.", flush=True)
    step = step + 1
    task = 'Run NOX SAS Service'
    basicpublish(status=STATUS_MESSAGES.STARTED)
    Success, Message, JSONNox = RunNOXSAS(receivedLocation)
    if not Success:
        basicpublish(status=STATUS_MESSAGES.FAIL, message=Message)
        notes.append(f"Failed task {step}, \"{task}\"")
    else:
        Success, Message, scoringJson = JSONMerge(scoringJson, JSONNox)
        if not Success:
            #raise Exception(f"Failed task {step}, \"{task}\", reason given was \"{Message}\"")
            basicpublish(status=STATUS_MESSAGES.FAIL, 
                    message=f"Failed task {step}, \"{task}\", reason given was \"{Message}\"",
                )
            return
        basicpublish(status=STATUS_MESSAGES.FINISHED)
    
    j = json.dumps(scoringJson)
    step = step + 1
    task = 'Get NDB'
    basicpublish(status=STATUS_MESSAGES.STARTED)
    Success, Message, ndbDestination = JsonToNdb(scoringJson, projectLocation)
    if not Success:
        # basicpublish(channel, name, step, task, 2, Message)
        # raise Exception(f"Failed task {step}, \"{task}\", reason given was \"{Message}\"")
        basicpublish(name, step,task, 
            status=STATUS_MESSAGES.FAIL, 
            message=f"Failed task {step}, \"{task}\", reason given was \"{Message}\"", 
            fileName=name, centreId=centreId)
        return
    basicpublish(status=STATUS_MESSAGES.FINISHED)
    
    centreDestinationFolder = os.path.join(os.environ['DELIVERY_FOLDER'], path)
    if not os.path.exists(centreDestinationFolder):
        os.makedirs(centreDestinationFolder)
    processedRecordingFolder = os.path.join(centreDestinationFolder, name)
    if not os.path.exists(processedRecordingFolder):
        os.makedirs(processedRecordingFolder)

    shutil.copy(ndbDestination,processedRecordingFolder)

    files = os.listdir(receivedLocation)
    for file in files:
        if '.ndb' in file.lower():
            continue
        shutil.copy( os.path.join(receivedLocation, file), processedRecordingFolder)
    

    # now deliver to teh edf folder.
    edfDeliveryfolder = os.path.join(os.environ["EDF_DELIVERY_FOLDER"], path)
    if not os.path.exists(edfDeliveryfolder):
        os.makedirs(edfDeliveryfolder)

    shutil.copy(
        os.path.join(projectLocation, edfName),
        edfDeliveryfolder
        )
    jsonName = edfName.replace('.edf', '.scoring.json')
    #writie a code that writes the json object scoringJsoninto a file called jsonName in the folder edfDeliveryFolder
    json_string = json.dumps(scoringJson)

    # Write the JSON string to the file
    with open(os.path.join(edfDeliveryfolder, jsonName), "w") as file:
        file.write(json_string)
    # clean up
    shutil.rmtree(projectLocation)

    step += 1
    task = "Finished"
    basicpublish(STATUS_MESSAGES.JOBEND, "Finished job.")

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

if __name__ == '__main__':
    print("Starting consumer threads")
    # p1 = multiprocessing.Process(target=consume_queue1)
    # p1.start()
    # consume_queue2()
    p2 = multiprocessing.Process(target=consume_queue2)
    p2.start()

    # # p1.join()
    p2.join()