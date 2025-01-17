import multiprocessing
import pika
import os
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '2'

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
    WARN = 3



import datetime
class ProgressMessage:
    def __init__(self, stepNumber:int, taskTitle:str, progress:int, message:str="", datasetName:str=None, nightId:int=None):
        self.StepNumber = stepNumber
        self.TaskTitle = taskTitle
        self.Progress = progress
        self.Message = message
        self.DatasetName = datasetName
        self.NightId = nightId
    def serialise(self) -> dict: 
        return {
            'NightId': self.NightId,
            'StepNumber': self.StepNumber,
            'TaskTitle': self.TaskTitle,
            'Progress': self.Progress,
            'Message': self.Message,
            'DatasetName': self.DatasetName
        }

def set_permissions(folder_path):
    for root, dirs, files in os.walk(folder_path):
        for d in dirs:
            os.chmod(os.path.join(root, d), 0o777)
        for f in files:
            if('.docx' in f):
                print(f'Skipping file {f} because it is apparently a docx file.') 
                continue
            os.chmod(os.path.join(root, f), 0o666)  # 0o666 is for read and write permissions for everyone


def process_file(channel, message):
    
    # Centre --:> uploads == [ id int, location, etc. ]
    projectName = str(uuid.uuid4())
    projectLocation = os.path.join('temp_uuids', projectName)
    os.makedirs(projectLocation)
    path = message['path'] #centre name
    name = message['name'] # ESR 0xyy0z
    nightId = message['nightId']
    centreId = message['centreId']
    isDataset = message['dataset']
    datasetName = '' if not isDataset else path
    step = -100
    task = "preparatory task"

    # a bit of a fancy border around the print statement
    print(f"{'='*50}\nProcessing {path}/{name}\n{'='*50}\n", flush=True)


    def basicpublish(status=-2, message=""):
        url = f"{os.environ['FRONT_END_SERVER']}/meta/log_night"
        entry = ProgressMessage(step, task, status, message, datasetName=datasetName, nightId=nightId)
        print(entry.serialise())
        r = requests.post(url, json=entry.serialise())
        pass


    
    # BUCKET/CENTRE/NAME/
    receivedLocation = ""
    if isDataset:
        receivedLocation = os.path.join(os.environ['DATASET_DIR'], path, name)
    else:
        receivedLocation = os.path.join(os.environ['INDIVIDUAL_NIGHT_WAITING_ROOM'], path, name)

    # make sure the received location exists
    if not os.path.exists(receivedLocation):
        basicpublish(status=STATUS_MESSAGES.FAIL, message=f"Received location {receivedLocation} does not exist.")
        return

    step = 1 
    task = 'Convert To EDF'
    basicpublish(status=STATUS_MESSAGES.STARTED)
    Success, Message, edfName = NoxToEdf(receivedLocation, projectLocation)
    if not Success:
        basicpublish(status=STATUS_MESSAGES.FAIL, message=Message)
        return    
    basicpublish(status=STATUS_MESSAGES.FINISHED)

    step = step + 1
    task = "Get json from original ndb file"
    files = os.listdir(receivedLocation)
    oldNdbFiles = list(filter(lambda x: '.ndb' in x.lower(), files))
    if len(oldNdbFiles) != 1:
        basicpublish(status=STATUS_MESSAGES.FAIL, message=f"Found {len(oldNdbFiles)} ndb files in extracted location.")
        return
    oldNdbFileLocation = os.path.join(receivedLocation, oldNdbFiles[0])
    files = {'ndb_file': open(oldNdbFileLocation, 'rb').read()}
    headers = {}
    scoringJson = None
    try:
        now = datetime.datetime.now()
        print("\t -> Posting NDB to NDB->JSON service", flush=True)
        r = requests.post(f'{os.environ["NOX_NDB_SERVICE"]}/ndb-to-json', files=files, headers=headers)
        scoringJson = json.loads(r.content)
        print("\t <- Done posting Nox zip to service", flush=True)
        print(f"\t <-- It took {datetime.datetime.now() - now} seconds....", flush=True)
    except Exception as e:
        basicpublish(STATUS_MESSAGES.WARN, "Failed to turn NDB into JSON.")
        # return

    if scoringJson is not None:
        print("Got a scoring json.")

        # Set default scoring names if they are missing or empty
        for i, scoring in enumerate(scoringJson.get('scorings', [])):
            if not scoring.get('scoring_name'):
                scoring['scoring_name'] = f"default-scoring-{i+1}"

        # Check if 'active_scoring_name' is in scoringJson and is not None or empty
        if not scoringJson.get('active_scoring_name'):
            # Use the first scoring name if there are any scorings available
            if scoringJson.get('scorings'):
                scoringJson['active_scoring_name'] = scoringJson['scorings'][0]['scoring_name']
            else:
                scoringJson['active_scoring_name'] = ""
                    
    basicpublish(status=STATUS_MESSAGES.FINISHED)

    
    step = step + 1
    task = 'Run Matias Algorithm'
    basicpublish(status=STATUS_MESSAGES.STARTED)
    Success, Message, JSONMatias = RunMatiasAlgorithm(os.path.join(projectLocation, edfName))
    if not Success:
        basicpublish(status=STATUS_MESSAGES.WARN, message=Message)
    else:
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


    # This will always fail, which is why we are commenting it out. We decided to run the aSAGA algorithm instead.
    # print("Running Nox SAS service.", flush=True)
    # step = step + 1
    # task = 'Run NOX SAS Service'
    # basicpublish(status=STATUS_MESSAGES.STARTED)
    # Success, Message, JSONNox = RunNOXSAS(receivedLocation)
    # if not Success:
    #     basicpublish(status=STATUS_MESSAGES.FAIL, message=Message)
    # else:
    #     Success, Message, scoringJson = JSONMerge(scoringJson, JSONNox)
    #     if not Success:
    #         basicpublish(status=STATUS_MESSAGES.FAIL, message=f"Failed task {step}, \"{task}\", reason given was \"{Message}\"",)
    #         return
    #     basicpublish(status=STATUS_MESSAGES.FINISHED)


    step = step + 1
    task = 'Get NDB'
    basicpublish(status=STATUS_MESSAGES.STARTED)
    Success, Message, ndbDestination = JsonToNdb(scoringJson, projectLocation)
    if not Success:
        basicpublish(status=STATUS_MESSAGES.FAIL, message=Message)
        return
    basicpublish(status=STATUS_MESSAGES.FINISHED)


    step = step + 1
    task = 'Deliver Nox Recording!'
    basicpublish(status=STATUS_MESSAGES.STARTED)
    centreDestinationFolder = os.path.join(os.environ['DELIVERY_FOLDER'], path)
    if not os.path.exists(centreDestinationFolder):
        os.makedirs(centreDestinationFolder)
        os.chmod(centreDestinationFolder, 0o777)  # Set permissions for the main directory

    processedRecordingFolder = os.path.join(centreDestinationFolder, name)
    if not os.path.exists(processedRecordingFolder):
        os.makedirs(processedRecordingFolder)
        os.chmod(processedRecordingFolder, 0o777)  # Set permissions for the subdirectory

    shutil.copy(ndbDestination,processedRecordingFolder)
    files = os.listdir(receivedLocation)
    for file in files:
        if '.ndb' in file.lower():
            continue
        shutil.copy( os.path.join(receivedLocation, file), processedRecordingFolder)
    set_permissions(processedRecordingFolder)
    basicpublish(status=STATUS_MESSAGES.FINISHED)


    step+=1
    task="Copying EDF & JSON"
    edfDeliveryfolder = os.path.join(os.environ["EDF_DELIVERY_FOLDER"], path)
    if not os.path.exists(edfDeliveryfolder):
        os.makedirs(edfDeliveryfolder)
    basicpublish(status=STATUS_MESSAGES.STARTED)
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
    basicpublish(status=STATUS_MESSAGES.FINISHED)
    # clean up
    shutil.rmtree(projectLocation)
    

    step += 1
    task = "Finished"
    basicpublish(STATUS_MESSAGES.JOBEND, "Finished job.")

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
