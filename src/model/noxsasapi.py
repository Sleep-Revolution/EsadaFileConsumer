from pathlib import Path
from zipfile import ZipFile
import requests
import json
from io import BytesIO
import time

class NOXSASAPI:
    def __init__(self):
        self.url = "http://130.208.209.71/jobs"
        self.class_map = {
            "sleep-n3": 0,
            "sleep-n2": 1,
            "sleep-n1": 2,
            "sleep-rem": 3,
            "sleep-wake": 4,
            }
        self.REQUIRED_SIG_FILENAMES = {
            "e3.ndf",
            "e1.ndf",
            "af7.ndf",
            "af3.ndf",
            "af4.ndf",
            "af8.ndf",
            "e2.ndf",
            "e4.ndf",
            }


    def send_prediction_job(self, path_to_recording: Path) -> dict:
        """Sends a recording to the SAS Sleep Scoring Service"""

        # Zip required signal files and store zip file in-memory
        # zip_buffer = BytesIO()
        # with ZipFile(zip_buffer, "w") as zip_file:
        #     for sig_path in path_to_recording.glob("**/*.ndf"):
        #         if sig_path.name.lower() in self.REQUIRED_SIG_FILENAMES:
        #             zip_file.write(str(sig_path), arcname=sig_path.name)

        zip_buffer = BytesIO()
        with ZipFile(path_to_recording) as zf:
            with ZipFile(zip_buffer, "w") as zip_file:
                for file in zf.namelist():
                    if file.endswith(".ndf"):
                        if Path(file).name.lower() in self.REQUIRED_SIG_FILENAMES:
                            file_contents = zf.read(file)

                            # Add the file contents to the new zip file
                            zip_file.writestr(file, file_contents)


        data = {"model_version": "v1.1-cal"}
        headers = {"accept": "application/json"}
        # If you are sending a real file, you can do something akin to this:
        # files = {"file": open(path_to_my_zip_file, "rb")}
        files = {"file": zip_buffer.getbuffer()}
        r = requests.post(self.url, params=data, headers=headers, files=files, timeout=1000)
        r = r.json()

        
        return r


    def get_job_status(self,job_id: str) -> dict:
        new_url = f"{self.url}/{job_id}"

        headers = {"accept": "application/json"}

        r = requests.get(new_url, headers=headers, timeout=120)
        r = r.json()
    
        return r

    def get_job_results(self, path_to_unzipped_nox_recording) -> dict:
        response = self.send_prediction_job(Path(path_to_unzipped_nox_recording))
        job_id = response["job_id"]
        iter_ = 0
        while response["status"] != "SUCCESS":
            response = self.get_job_status(job_id)
            status = response["status"]
            print(f"Job id: {job_id}, Response: {status}")
            time.sleep(10)
            iter_ = iter_ + 1
            if iter_ > 100:
                raise Exception(f"Job did not finish in {100*10/60} minutes")

        print(response["status"])
        markers = response["results"]["markers"]

        sleepstages_predicted = []

        for epoch in markers:
            epoch_sleepstage = epoch["prediction"]
            sleepstages_predicted.append(self.class_map[epoch_sleepstage])

        markers_for_service = []
        for marker in markers:
            new_marker = {
                "label": marker["prediction"],
                "signal": None,
                "start_time": marker["start_time"],
                "stop_time": marker["stop_time"],
                "scoring_type": "Automatic",
            }
            markers_for_service.append(new_marker)

        scoring_name = "NOXSAS"

        scoring_collection_object = {
            "version": "1.0",
            "active_scoring_name": scoring_name,
            "scorings": [
                {
                "scoring_name": scoring_name,
                "markers": markers_for_service
                }
            ]
            }
        return scoring_collection_object