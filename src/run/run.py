import os
import logging
import sys
sys.path.insert(0,os.getcwd())
# sys.path.insert(0, os.path.join(os.getcwd(),"./api/GrayAreaDL"))
# curl -X 'POST' 'http://130.208.209.67:80/nox-to-edf get_active_recording_time=false&get_all_scorings=false&export_scoring=true' -H 'accept: application/json' -H 'Content-Type: multipart/form-data' -F 'nox_zip=@sas3nightTestSmall.zip;type=application/x-zip-compressed' -o zipped_edf.zip
# curl -X 'POST' 'http://130.208.209.67:80/nox-to-edf' -H 'accept: application/json' -H 'Content-Type: multipart/form-data' -F 'nox_zip=@sas3nightTestSmall.zip;type=application/x-zip-compressed' -o zipped_edf.zip

from datetime import datetime
from pathlib import Path
import copy

import numpy as np
import yaml

from sklearn.model_selection import ShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import normalize

from src.data.predictors import *
from src.data.prediction import *
from src.data.datagenerator import *

from src.preprocessing.harmonisation import *

from src.model.model import *
from src.model.noxsasapi import *

from src.utils.yamlutils import *
from src.utils.save_xp import *


from tensorflow import keras
import tensorflow_addons
import pandas as pd
import gc
import json
############################ CONF POSSIBLE ############################

class RunPredict:
    def __init__(self, FILEPATH):
        self.SCORE_DICT = {
            'Wake': 0.,
            'N1': 1.,
            'N2': 2.,
            'N3': 3.,
            'REM': 4.}
        
        # ToDo: Put this into the environmental variables.
        ModelPath = os.environ["MATIAS_MODEL_PATH"]#"matiasmodel/sas_scoring_models/E1M2_iqr_std_2021-11-04_135554/"  
      
        confyml = "src/run/PreProConf.yaml"
        logging.basicConfig(level=logging.INFO)
        loader = get_conf_loader()
        with open(confyml) as file:
            params = yaml.load(file, Loader=loader)
        self.pipeline_prepro = Pipeline([(str(estimator), estimator) for estimator in params["Preprocessing"]])

        self.paramsPred = {"SignalChannels":['AF3-E3E4', 'AF4-E3E4', 'AF7-E3E4', 'AF8-E3E4', 'E1-E4', 'E2-E3', 'E2-AFZ', 'E3-AFZ'],
                           "ALL":True,
                           "Ensemble":True,
                           "Type_study":"SAS",
                           "GrayAreaThreshold":0.3,
                           "EDFPath":FILEPATH,
                           "PredPath": FILEPATH[:-4] + "_PRED"
                           }
        # self.paramsPred['SignalChannels'] = [_.lower() for _ in self.paramsPred['SignalChannels'] ]
        self.model = keras.models.load_model(ModelPath)
        print(self.model.summary())
        logging.info("Model Loaded")
        self.nsignals = len(self.paramsPred["SignalChannels"])
        self.all = self.paramsPred.get("ALL",False)
        self.ensemble = self.paramsPred.get("Ensemble",False)
        self.type_study = self.paramsPred.get("Type_study","PSG")
        
        if self.ensemble:
            self.generator = DataGeneratorPred(self.paramsPred["EDFPath"],
                                        self.paramsPred["SignalChannels"],
                                        pipeline=self.pipeline_prepro,
                                        ensemble = self.ensemble,
                                               type_study=self.type_study)
        else:
            self.generator = DataGeneratorPred(self.paramsPred["EDFPath"],
                                self.paramsPred["SignalChannels"],
                                pipeline=self.pipeline_prepro,
                                               type_study=self.type_study)
        self.nfile = len(self.generator.list_id)
        self.NOXSASJSON = []
    
    #################################     UNCOMMENT  ONLY FOR VALIDATION          ###########################################################
    # def MathiasValidation(self,file):
    #     i = file
    #     generator = MatiasGeneratorPred(self.paramsPred["EDFPath"])
    #     y = self.model.predict(generator.__getitem__(i),steps = 1)
    #     return y
    ###################################################################################################################

    def Predict(self,i):
        X = self.generator.__getitem__(i)
        for iterx in range(X.shape[0]):
            x = X[iterx,:,:][np.newaxis,:,:]
            if iterx==0:
                y = self.model.predict(x)
            else:
                y = np.concatenate((y,self.model.predict(x)),axis=0)
        Y = y.copy()
        # print("After prediction",y.shape)
        times = self.generator.currentSignal.metadata["TimeFromStart"]
        nepochs = y.shape[1]
        lenSignal = nepochs*int(30/self.generator.Predictors_.times_stamps)
        
        if lenSignal != times.shape[0]:
            times = times[:lenSignal]

        times = times.reshape((nepochs,int(30/self.generator.Predictors_.times_stamps)))
        times = times[:,0]

        # if isinstance(y,(np.ndarray)):
        #     y = y.tolist()

        if self.ensemble:
            Y = np.sum(Y, axis = 0)
            Y = Y/Y.sum(axis=1,keepdims=True)
            Hp_pred = np.argmax(Y, axis=1)

        Hp_pred = np.argmax(Y,axis=1)

        
        SignalName = np.array(self.generator.currentSignal.metadata["SignalName"])
        filepath = os.path.join(self.paramsPred["PredPath"],self.generator.Predictors_.allEdf[i-1]+".csv")
        filepathJSON = self.paramsPred["PredPath"]+".json"
        

        u2 = ((Y)*(1-Y)).sum(axis=1)
        Z_G = (u2>self.paramsPred["GrayAreaThreshold"])*1

        warnings = {"10":[],"30":[],"60":[],"120":[]}
        results = np.concatenate((Hp_pred[np.newaxis].T,Y,Z_G[np.newaxis].T),axis=1)
        for k in list(warnings.keys()):

            if Z_G.shape[0] % (int(k)*2) != 0:
                Nrow = int(Z_G.shape[0] / (int(k)*2))+1
                padd = Nrow*(int(k)*2)
                Z_G_tmp = np.zeros(padd)
                Z_G_tmp[:Z_G.shape[0]] = Z_G

                Nrow = int(Z_G_tmp.shape[0]/(int(k)*2))
                Ncol = int(int(k)*2)
                tmp = Z_G_tmp.reshape((Nrow,Ncol)).sum(axis=1)
                tmp = np.tile(tmp,(Ncol,1)).T.reshape(Ncol*Nrow)
                warnings[k] = tmp[:Z_G.shape[0]]
                results = np.concatenate((results,warnings[k][np.newaxis].T),axis=1)

            else:
                Nrow = int(Z_G.shape[0]/(int(k)*2))
                Ncol = int(int(k)*2)
                tmp = Z_G.reshape((Nrow,Ncol)).sum(axis=1)
                warnings[k] = np.tile(tmp,(Ncol,1)).T.reshape(Ncol*Nrow)
                results = np.concatenate((results,warnings[k][np.newaxis].T),axis=1)
        results = np.concatenate((times[np.newaxis].T,results),axis=1)
        print(f"Save: {filepath}")
        if ((self.all) & (self.ensemble)):
            columns = ["Times","Ens_Hypno"]+["Ens_"+k for k in list(self.SCORE_DICT.keys())]+["GrayArea"]+["Warning_"+k for k in list(warnings.keys())]
            DF = pd.DataFrame(results,columns = columns)
            for h in range(self.nsignals):
                Y_tmp = np.array(y[h])
                Y_tmp = Y_tmp/Y_tmp.sum(axis=1,keepdims=True)
                Hp_pred = np.argmax(Y_tmp,axis=1)
                Y_tmp = np.concatenate((Hp_pred[np.newaxis].T,Y_tmp),axis=1)
                columns = [SignalName[h]+"_Hypno"]+[SignalName[h]+"_"+k for k in list(self.SCORE_DICT.keys())]
                Y_tmp = pd.DataFrame(Y_tmp,columns = columns)
                DF = pd.concat((DF,Y_tmp),axis = 1)
            DF["Measure_date"] = self.generator.currentSignal.metadata["Measure date"]
        return self.NOXJSON(DF,filepathJSON)
     

    # Function to generate the json file for the NOX software
    def NOXJSON(self,predcsv,filepath):
        sleepstage = ['sleep-wake','sleep-n1','sleep-n2','sleep-n3','sleep-rem']
        nepoch = int(predcsv.shape[0])
        newmeasdate = (pd.to_datetime(predcsv["Measure_date"].iloc[0]).to_pydatetime())
        if (newmeasdate.second != 0) or (newmeasdate.second != 30):
            sub30 = 30 - newmeasdate.second
            if sub30>15:
                newmeasdate = newmeasdate - timedelta(seconds=newmeasdate.second)
            else:
                newmeasdate = newmeasdate + timedelta(seconds=sub30)

        predcsv["Measure_date"] = newmeasdate
        start_time = [(pd.to_datetime(predcsv["Measure_date"].iloc[0]).to_pydatetime())+timedelta(seconds=int(i)) for i in np.arange(predcsv.shape[0])*30]
        starttime2YYYYMMDDHHMMSS = [i.strftime("%Y-%m-%dT%H:%M:%S.000000") for i in start_time]
        stop_time = [(pd.to_datetime(predcsv["Measure_date"].iloc[0]).to_pydatetime())+timedelta(seconds=int(i)) for i in np.arange(predcsv.shape[0])*30+30]
        stoptime2YYYYMMDDHHMMSS = [i.strftime("%Y-%m-%dT%H:%M:%S.000000") for i in stop_time]
        
        JSONHeaders = { "version": "1.0",
        "active_scoring_name": "MatiasAlgorithm",
        "scorings": []}
        ListCORE = []
        
        JSONCORE = {
            "scoring_name": JSONHeaders["active_scoring_name"],
            "markers":[]}
        
        JSONCORE_U = {
            "scoring_name": JSONHeaders["active_scoring_name"]+"_uncertain",
            "markers":[]}
        
        for i in range(nepoch):
            markers = {
                "label": sleepstage[int(predcsv["Ens_Hypno"].iloc[i])],
                "signal":   None,
                "start_time": starttime2YYYYMMDDHHMMSS[i],
                "stop_time": stoptime2YYYYMMDDHHMMSS[i],
                "scoring_type": "Automatic"
                }
            JSONCORE["markers"].append(markers)

            if predcsv["GrayArea"].iloc[i]==1:
                new_marker_unc = {
                    "label": sleepstage[int(predcsv["Ens_Hypno"].iloc[i])]+"_uncertain",
                    "signal": None,
                    "start_time": starttime2YYYYMMDDHHMMSS[i],
                    "stop_time": stoptime2YYYYMMDDHHMMSS[i],
                    "scoring_type": "Automatic",
                }
                JSONCORE_U["markers"].append(new_marker_unc)
            else:
                JSONCORE_U["markers"].append(markers)

        JSONHeaders["scorings"].append(JSONCORE)
        JSONHeaders["scorings"].append(JSONCORE_U)
        return JSONHeaders
        # with open(filepath, 'w') as outfile:
        #     json.dump(JSONHeaders, outfile, indent=4)

    def launch(self):
        print("-------------------------------------------------------- BEGIN PREDICTION -----------------------------------------------------------------")
        for file in range(1,self.nfile+1):
            JSONfile = self.Predict(file)
        return JSONfile
        print("------------------------------------------------------------ END PREDICTION -------------------------------------------------------------")

