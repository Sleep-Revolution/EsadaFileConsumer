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
import io

import traceback

def NoxToEdf(sendziplocation, getziplocation):

    # Extract the folder name from the path
    folder_name = os.path.basename(sendziplocation)

    # Create an in-memory byte stream
    zip_data = io.BytesIO()

    # Create a zip file object
    with zipfile.ZipFile(zip_data, mode='w', compression=zipfile.ZIP_DEFLATED) as zipf:
        # Iterate over all the files and subdirectories
        for root, dirs, files in os.walk(sendziplocation):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, sendziplocation)
                if file.endswith(".ndb"):
                    print("Renaming ndb file.", flush=True)
                    arcname = os.path.join(folder_name, "Data.ndb")
            
                # Create the folder structure inside the zip file
                print(f"z:~------------>{file}", flush=True)
                zipf.write(file_path, arcname=os.path.join(folder_name, arcname))

    # Move to the beginning of the byte stream
    zip_data.seek(0)



files = {'file': zip_data, 'type':'application/x-zip-compressed'}
    headers = {
        'accept': 'application/json',
        # requests won't add a boundary if this header is set when you pass files=
        # 'Content-Type': 'multipart/form-data',
        # 'type':'application/x-zip-compressed'
    }

    try:
        now = datetime.datetime.now()
        print("\t -> Posting Nox zip to service")
        r = requests.post(f'{os.environ["NOX_EDF_SERVICE"]}/jobs', files=files, headers=headers, stream=True)
        print("\t <- Done posting Nox zip to service")
        print(f"\t <-- It took {datetime.datetime.now() - now} seconds....")
        if r.status_code != 200:
            raise Exception(f"Failed to run Nox edf for {file}, Error:{r.text}")
        results = r.json()

        jobid= results["job_id"]
        print(results)
        flag = True
        h=0
        
        while flag:
            r = requests.get(f'{os.environ["NOX_EDF_SERVICE"]}/jobs/{jobid}', headers=headers, stream=True)
            results = r.json()
            print(f"Waiting job {h} seconds")
            time.sleep(30)
            h += 30
            
            if results["status"]=="SUCCESS":
                flag = False
                print(results["status"])
            if r.status_code != 200:
                raise Exception(f"Failed to run Nox edf for {jobid}, Error:{r.text}")

        r = requests.get(f'{os.environ["NOX_EDF_SERVICE"]}/files/{jobid}', headers=headers)

    except Exception as e:
        return False, f"Requests error for {sendziplocation}", e
    # Check the status code
    if r.status_code > 299:
        return False, f"Status {r.status_code} for recording {sendziplocation} ({r.text})", None
    # Write the response to a file.
    try:
        
        with open(os.path.join(getziplocation, "edfzip.zip"), 'wb') as f:
            f.write(r.content)
            f.close()
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
    if len(efl) > 1:
        efl = [f for f in efl if '.scoring.edf' not in f]
    else:
        if len(efl) == 1:
            return True, "success", efl[0]
        else:
            return False, f"Failed to find edf file for {getziplocation} ", None
    return True, "success", efl[0]


def RunMatiasAlgorithm(edfLocation):
    try:
        x = Run.RunPredict(edfLocation)
        y = x.launch()
    except Exception as e:	
        print(e)
        traceback.print_tb(e.__traceback__)
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

# projectLocation = os.path.join(tmpFolder, str(onetimeuuid))

def RunSasService(projectLocation, RecordingLocation):
    requiredSignals = ['e3.ndf', 'e1.ndf', 'af7.ndf', 'af3.ndf', 'af4.ndf','af8.ndf', 'e2.ndf', 'e4.ndf']
    unzipLocation = os.path.join(projectLocation, 'Recording_unzipped')
    sasZipLocation = os.path.join(projectLocation, 'SAS.zip')
    os.mkdir(unzipLocation)
    try:
    # Extract the zip file to the destination folder.
        print("\t -> Extracting Zipped NOX folder")

        with zipfile.ZipFile(RecordingLocation, 'r') as f:
            f.extractall(unzipLocation)
            f.close()
        print("\t <- Done extracting Zipped NOX folder into", unzipLocation)
        if len(os.listdir(unzipLocation)) != 1:
            print("Bad number of folders inside extracted nox recording!")
            return False, "Bad number of folders inside extracted NOX recording"
    except:
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


def JsonToNdb(json, destination):
    try:
        now = datetime.datetime.now()
        print("\t -> Posting JSON to NDB service")
        r = requests.post(f'{os.environ["NOX_NDB_SERVICE"]}/json-to-ndb', json=json, stream=True)
        print("\t <- Done posting NDB to service")
        print(f"\t <-- It took {datetime.datetime.now() - now} seconds....")
    except Exception as e:
        return False, f"NDB requests error for", e
    if r.status_code > 299:
        return False, f"Status {r.status_code} for following json, {r.json()}", None
    # Write the response to a file.
    try:
        with open(os.path.join(destination,"Data.ndb"), 'wb') as f:
            shutil.copyfileobj(r.raw, f)
    except:
        return False, f"Failed to save the ndb for recording {dir}", None
    return True, "NDB successful", os.path.join(destination, "Data.ndb")
