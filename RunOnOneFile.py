import os
import requests
import shutil
import zipfile
import datetime
from src.run import run as Run
from src.model import noxsasapi as nsa
import uuid
import pathlib
import json
channels = []

os.environ["NOX_SAS_SERVICE"] ='http://130.208.209.71/jobs'
os.environ["GRAYAREA_THRESHOLD"] = "0.6"
os.environ["MATIAS_MODEL_PATH"] = "/main/home/gabrielj@sleep.ru.is/TrainedDLModel/best_model_20230417_133447/"
# os.environ["MATIAS_MODEL_PATH"] = "/main/home/gabrielj@sleep.ru.is/TrainedDLModel/E1M2_iqr_std_2021-11-04_135554/"
noxUrlToEdf = 'http://130.208.209.67'
noxUrlScoring = 'http://130.208.209.68'



tmpFolder = 'temp_uuids'

onetimeuuid = uuid.uuid4()

def NoxToEdf(sendziplocation, getziplocation):
    files = {'nox_zip': open(sendziplocation, 'rb'), 'type':'application/x-zip-compressed'}
    headers = {
        'accept': 'application/json',
        # requests won't add a boundary if this header is set when you pass files=
        # 'Content-Type': 'multipart/form-data',
        # 'type':'application/x-zip-compressed'
    }
    # Post the files to the service.
    try:
        now = datetime.datetime.now()
        print("\t -> Posting Nox zip to service")
        r = requests.post(f'{noxUrlToEdf}/nox-to-edf?get_active_recording_time=false&get_all_scorings=false&export_scoring=true', files=files, headers=headers, stream=True)
        print("\t <- Done posting Nox zip to service")
        print(f"\t <-- It took {datetime.datetime.now() - now} seconds....")
    except Exception as e:
        return False, f"Requests error for {dir}", e
    # Check the status code
    if r.status_code > 299:
        return False, f"Status {r.status_code} for recording {dir}", None
    # Write the response to a file.
    try:
        with open(os.path.join(getziplocation, "edfzip.zip"), 'wb') as f:
            shutil.copyfileobj(r.raw, f)
    except:
        return False, f"Failed to save the edf.zip for recording {dir}", None

    try:
    # Extract the zip file to the destination folder.
        print("\t -> Extracting Zipped EDF folder")

        with zipfile.ZipFile(os.path.join(getziplocation, "edfzip.zip"), 'r') as f:
            f.extractall(os.path.join(getziplocation))
            f.close()
        print("\t <- Done extracting Zipped EDF folder into", os.path.join(getziplocation))
    except:
        return False, f"Failed to extract response from nox for recording {dir} ({getziplocation})", None
    
    # Delete the zip file.
    os.remove(os.path.join(getziplocation, "edfzip.zip"))
    
    # Find the new zip file name
    efl = list(filter(lambda x: '.edf' in x, os.listdir(os.path.join(getziplocation))))
    if len(efl) != 1:
        return False, f"Did not find 1 edf file in list of new files. {efl}", None

    return True, "success", efl[0]


def RunMatiasAlgorithm(edfLocation):
    try:
        x = Run.RunPredict(edfLocation)
        y = x.launch()
    except Exception as e:	
        return False, f"Failed to run Matias algorithm for recording {edfLocation}", e
    return True, "Success", y

def RunNOXSAS(zfile):
    try:
        # filezip = file#[f for f in os.listdir(projectLocation) if f.endswith(".zip")]
        NOX_sas_call = nsa.NOXSASAPI()
        NOXSASJSON = NOX_sas_call.get_job_results(zfile)
    except Exception as e:
        return False, f"Failed to run NOX SAS for recording {zfile}", e
    
    return True, "Success", NOXSASJSON

def JSONMerge(JSONMatias,JSONNOX):
    try:
        for i in range(len(JSONNOX["scorings"])):
            JSONMatias["scorings"].append(JSONNOX["scorings"][i])
    except Exception as e:
        return False, f"Failed to merge JSON", e
    return True, "Success", JSONMatias

projectLocation = os.path.join(tmpFolder, str(onetimeuuid))

def RunSasService(RecordingLocation):
    requiredSignals = ['e3.ndf', 'e1.ndf', 'af7.ndf', 'af3.ndf', 'af4.ndf','af8.ndf', 'e2.ndf', 'e4.ndf']
    unzipLocation = os.path.join(projectLocation, 'Recording_unzipped')
    sasZipLocation = os.path.join(projectLocation, 'SAS.zip')
    os.mkdir(unzipLocation)
    # try:
    # Extract the zip file to the destination folder.
    print("\t -> Extracting Zipped NOX folder")

    with zipfile.ZipFile(RecordingLocation, 'r') as f:
        f.extractall(unzipLocation)
        f.close()
    print("\t <- Done extracting Zipped NOX folder into", unzipLocation)
    if len(os.listdir(unzipLocation)) != 1:
        print("Bad number of folders inside extracted nox recording!")
        return False, "Bad number of folders inside extracted NOX recording"
# except:
    return False, f"Failed to extract NOX for recording {dir} ({RecordingLocation})", None


    dir = os.listdir(unzipLocation)[0]
    flist = list(os.listdir(os.path.join(unzipLocation, dir )))
    for reqSignal in requiredSignals:
        if reqSignal not in flist:
            print(f"{RecordingLocation} is not a valid recording, {reqSignal} is not in list of files.")
            return False, "", None
    try:
        directory = pathlib.Path(unzipLocation)
        with zipfile.ZipFile(sasZipLocation, mode="w") as archive:
            i = 1
            n = len(list(directory.rglob(f"{dir}/*")))
            for file_path in directory.rglob(f"{dir}/*"):
                fname = str(file_path).split('/')[-1]
                if fname not in requiredSignals:
                    print(f"\t\t -x- Skipping {fname} in Zip")
                    continue
                if True:
                    fpath = str(file_path).split('/')[-1]
                    print(f"\t\t --> Zipping {fname} ({i}/{n})")
                archive.write(file_path, arcname=file_path.relative_to(directory)) 
    except:
        return False, "Failed to Write to SAS ZIP location!", None


def JsonToNdb(json,file):
    try:
        now = datetime.datetime.now()
        print("\t -> Posting Nox zip to service")
        r = requests.post(f'{noxUrlScoring}/json-to-ndb', json=json, stream=True)
        print("\t <- Done posting Nox zip to service")
        print(f"\t <-- It took {datetime.datetime.now() - now} seconds....")
    except Exception as e:
        return False, f"Requests error for {dir}", e
    if r.status_code > 299:
        return False, f"Status {r.status_code} for recording {dir}", None
    # Write the response to a file.
    try:
        with open(file+".ndb", 'wb') as f:
            shutil.copyfileobj(r.raw, f)
        return True,f"\t <-Done save ndb {file}",None
    except:
        return False, f"Failed to save the ndb for recording {dir}", None

    
# os.makedirs(projectLocation, exist_ok=True)


# Success, Message, edfName = NoxToEdf(file, projectLocation)
# print("Running nox SAS")
# Success, Message, JSONN = RunNOXSAS(file)
# print("Running matias alg")
# Success, Message, JSONM = RunMatiasAlgorithm(os.path.join(projectLocation, edfName))
# print("Merging")
# Success, Message, JSONM = JSONMerge(JSONM,JSONN)
# # x = None
# # with open("tempjson.json", 'r') as f:
# #     x = json.loads(f.read())

# JsonToNdb(JSONM)



# file = '/mnt/foobar/Benedikt/TestRecording/Day1_test2.zip'
path = '/main/home/gabrielj@sleep.ru.is/ESADA/TmpData/'
pathfinal = '/main/home/gabrielj@sleep.ru.is/ESADA/FINAL/'
# file = '/main/home/gabrielj@sleep.ru.is/TmpData/benedikt_testrecording.zip'
for file in os.listdir(path):
    print("Start",file)
    onetimeuuid = uuid.uuid4()
    onetimeuuid = "4929d3c2-d27e-4fc7-8e32-88e4b0ef2082"
    tmpFolder = 'temp_uuids'
    projectLocation = os.path.join(tmpFolder, str(onetimeuuid))
    os.makedirs(projectLocation, exist_ok=True)
    Success =True
    edfName = "20210427T230008 - e9974.edf"
    
    # print(os.path.join(path,file))
    # Success, Message, JSONN = RunNOXSAS(os.path.join(path,file))
    
    # Success, Message, edfName = NoxToEdf(os.path.join(path,file), projectLocation)
    if Success:
        # Success, Message, JSONN = RunNOXSAS(os.path.join(path,file))
        Success, Message, JSONM = RunMatiasAlgorithm(os.path.join(projectLocation, edfName))
        
        
        print(JSONM)
        print("Merging")
        # Success, Message, JSONM = JSONMerge(JSONM,JSONN)
        
        Success, Message,_ = JsonToNdb(JSONM,os.path.join(pathfinal,file))
        
        if Success:
            print(Message)
        else:
            print(Message)
            break
        # Success, Message, JSON_New = JSONMerge(JSONM,JSONN)
    else:
        print(Message)
        break

# if Success:
#     JsonToNdb(JSON_New,file)
# else:
#     if type(JSONM) is dict:
#         JsonToNdb(JSONM,file)
#         Warning("Only aSAGA SAS algorithm result")
#     if type(JSONN) is dict:
#         JsonToNdb(JSONN,file)
#         Warning("Only Nox SAS algorithm result")
#     if (not type(JSONM) is dict) & (not type(JSONN) is dict ):
#         print(Message)
# print("Done",file)


# Folder = "/main/home/gabrielj@sleep.ru.is/TmpData/"
# file = '/main/home/gabrielj@sleep.ru.is/TmpData/Day2.zip'
# tmpFolder = 'temp_uuids'




#  -> Posting Nox zip to service
#          <- Done posting Nox zip to service
#          <-- It took 0:43:40.178262 seconds....
#          -> Extracting Zipped EDF folder
#          <- Done extracting Zipped EDF folder
# (True, 'Success!')