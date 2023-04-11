import os
import requests
import shutil
import zipfile
import datetime
from src.run import run as Run
import uuid
channels = []
noxUrlToEdf = '130.208.209.67'
noxUrlScoring = '130.208.209.68'
noxUrlToSAS = '130.208.209.71'
file = '/mnt/foobar/Benedikt/TestRecording/Day1_test2.zip'
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
        r = requests.post(f'http://130.208.209.67/nox-to-edf?get_active_recording_time=false&get_all_scorings=false&export_scoring=true', files=files, headers=headers, stream=True)
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
    
    # Find the new zip file name
    efl = list(filter(lambda x: '.edf' in x, os.listdir(os.path.join(getziplocation))))
    if len(efl) != 1:
        return False, f"Did not find 1 edf file in list of new files. {efl}", None

    return True, "success", efl[0]


def RunMatiasAlgorithm(edfLocation):
    x = Run.RunPredict(edfLocation)
    y = x.launch()
    
    print(y)


# def RunSasService(RecordingLocation):

#     sendziplocation = 

projectLocation = os.path.join(tmpFolder, str(onetimeuuid))
os.makedirs(projectLocation, exist_ok=True)
# edfLocation = os.path.join(projectLocation, "edf.edf")

Success, Message, edfName = NoxToEdf(file, projectLocation)
# 
RunMatiasAlgorithm(os.path.join(projectLocation, edfName))

#  -> Posting Nox zip to service
#          <- Done posting Nox zip to service
#          <-- It took 0:43:40.178262 seconds....
#          -> Extracting Zipped EDF folder
#          <- Done extracting Zipped EDF folder
# (True, 'Success!')