import time
import os
import pandas as pd
import numpy as np
import mne
import re
import pickle
from datetime import datetime, timedelta

import sys
# sys.path.insert(0, os.path.abspath("/main/home/gabrielj@sleep.ru.is/GrayAreaDL/"))
from src.data.partsignal import *
from typing import Union, List, Dict, Any, Optional, TypeVar
from src.preprocessing.resample import *
import glob

def fmt(ticks):
    if all(isinstance(h, str) for h in ticks):
        return "%s"
    return ("%.d" if all(float(h).is_integer() for h in ticks) else
            "%.2f")

class Predictors:
    def __init__(self,path_edf_data,convuV=False,verbose=1,times_stamps=0.005,epoch_time=30,signalsNames=['C4-A1'],maxHours=10,type_study="PSG"):
        self.path_edf_data = path_edf_data

        self.convuV = convuV
        self.verbose = verbose
        self.times_stamps = times_stamps
        self.epoch_time= epoch_time
        self.signalsNames=signalsNames
        self.maxHours = maxHours
        self.type_study = type_study

        self.allEdf = [path_edf_data]

        self.exclude = [['1','1 Impedance','1-2','1-F','2','2 Impedance','2-F','Abdomen CaL','Abdomen Fast','Abdomen','Activity','Light','Audio Volume','Audio Volume dB','C3 Impedance','C4 Impedance','cRIP Flow','cRIP Sum','E1 Impedance','E2 Impedance','ECG','ECG Impedance','EDA','Elevation','F Impedance','F3 Impedance','F4 Impedance','Flow','Flow Limitation','Heart Rate','Inductance Abdom','Inductance Thora','K','Left Leg','Left Leg Impedan','M1 Impedance','M1M2','M2 Impedance','Nasal Pressure','O1 Impedance','O2 Impedance','Pulse Waveform','PosAngle','PTT','Pulse','PWA','Resp Rate','Right Leg','Right Leg Impeda','RIP Flow','RIP Phase','RIP Sum','Snore','Saturation','SpO2 B-B','Thorax Fast','Chest','Voltage (battery','Voltage bluetoo','Voltage (core)','X Axis','Y Axis','Z Axis'], 
                ['Ambient Light A1', 'EKG Impedance', 'Pulse Wave (Plet', 'Set Pressure', 'Position', 'SpO2', 'Mask Pressure', 'PTT', 'Thorax', 'Heart Rate-0', 'Heart Rate-1','Abdomen CaL', 'Abdomen Fast', 'Abdomen', 'Activity', 'AF3 Impedance', 'AF4 Impedance', 'AF7 Impedance',  'AF8 Impedance', 'AFZ Impedance', 'Light', 'Audio', 'Audio Volume', 'Audio Volume dB', 'cRIP Flow', 'cRIP Sum', 'E1 Impedance', 'E1-E4 (Imp)','E2 Impedance', 'E2-AFZ (Imp)', 'E2-E3 (Imp)', 'E3 Impedance', 'E3-AFZ (Imp)', 'E4 Impedance', 'ECG','ECG Impedance', 'ECG LA', 'ECG LA Impedance', 'ECG LF', 'ECG LF Impedance', 'ECG RA', 'ECG RA Impedance', 'Elevation', 'EMG.Frontalis-Le', 'EMG.Frontalis-Ri', 'Flow','Flow Limitation', 'Inductance Abdom', 'Inductance Thora', 'K', 'LA-RA', 'Left Leg', 'Left Leg Impedan', 'LF-LA', 'LF-RA', 'Nasal Pressure', 'Pulse Waveform', 'PosAngle', 'Pulse','PWA', 'Resp Rate', 'Right Leg', 'Right Leg Impeda', 'RIP Flow', 'RIP Phase', 'RIP Sum', 'Snore', 'Saturation', 'SpO2 B-B', 'Thorax Fast', 'Chest', 'Voltage (battery', 'Voltage (bluetoo','Voltage (core)', 'X Axis', 'Y Axis', 'Z Axis']]

        # self.rename_sas = {'af4' : 'af4-e3e4','af3' : 'af3-e3e4','af7' : 'af7-e3e4','af8' : 'af8-e3e4'}
    

        self.channel_names_sas = np.array(['E1', 'E3', 'E2', 'E4', 'AF3', 'AF4', 'AF7', 'AF8', 'AFZ'])
        # self.channel_names_sas = np.array([_.lower() for _ in self.channel_names_sas])
        self.channel_category_sas = np.array(['eog', 'eog', 'eog', 'eog', 'eeg', 'eeg', 'eeg' ,'eeg', 'eog'])
        # self.channel_names_sas = np.array([_.lower() for _ in self.channel_names_sas])
        self.ref_channels_sas = [['e3','e4'],['eeg']]
        self.anode_sas = np.array(['E3', 'E2', 'E1', 'E2'])
        # self.anode_sas = np.array([_.lower() for _ in self.anode_sas])

        self.cathode_sas = np.array(['AFZ', 'AFZ','E4', 'E3'])
        # self.cathode_sas = np.array([_.lower() for _ in self.cathode_sas])

        self.rename_sas = np.array(['E1-E4', 'E2-E3', 'E3-AFZ', 'E2-AFZ'])
        self.rename_category_sas = np.array(['eog','eog','eog','eog'])


        self.channel_names_psg = np.array(['F4', 'F3', 'C4', 'C3', 'O1', 'O2', 'E1', 'E2',"M1","M2"])
        self.channel_category_psg = np.array(['eeg', 'eeg', 'eeg', 'eeg', 'eeg', 'eeg' ,'eog', 'eog','eeg','eeg'])
        self.anode_psg = np.array(['F4', 'F3', 'C4', 'C3', 'O1', 'O2',"E1","E2"])
        self.cathode_psg = np.array(["M1","M2","M1","M2","M2","M1","M2","M1"])
        self.rename_psg = np.array(['F4-M1','F3-M2','C4-M1','C3-M2','O1-M2','O2-M1','E1-M2','E2-M1'])
        self.rename_category_psg =  np.array(['eeg','eeg','eeg','eeg','eeg','eog','eog'])

        
        
        
    def Load(self,partID: int,signalsNames=None,**kwargs):
        if not (signalsNames is None):
            self.signalsNames=signalsNames
            
        if self.convuV:
            TouV = 1e6
        else:
            TouV = 1
        k = partID-1
        fileEDF = self.allEdf[k] # os.path.join(self.filedir[k],self.filename[k])
        if self.verbose>0:
            print(f"Load Part : {partID}, input name: {self.allEdf[k]}")

        # tmpfile = self.allEdf[k]
        
        if self.type_study == "SAS":
            channel_names = self.channel_names_sas
            channel_category = self.channel_category_sas
            exclude = self.exclude[1]
            ref_channels = self.ref_channels_sas
            rename = self.rename_sas
            anode = self.anode_sas
            cathode = self.cathode_sas
            rename_category = self.rename_category_sas
        else:
            channel_names = self.channel_names_psg
            channel_category = self.channel_category_psg
            exclude = self.exclude[0]
            rename = self.rename_psg
            anode = self.anode_psg
            cathode = self.cathode_psg
            rename_category = self.rename_category_psg
            
        raw = mne.io.read_raw_edf(fileEDF,verbose=self.verbose)
         #channels to use in re-referencing (deriving) the conventional SAS channels
        
        # check existence of channel_names in raw ch_names
        if not all([i in raw.ch_names for i in channel_names]):
            # Select subset of channel_names only if present in raw ch_names:
            channel_names = np.array([i for i in channel_names if i in raw.ch_names])
            print(f"Only {channel_names} available in {fileEDF}")
        else:
            print(f"All channels available in {fileEDF}")

        signalsName_tmp = []    
        anode_tmp = []
        catode_tmp = []
        for i in self.signalsNames:
            i = i.split("-")
            assert len(i) > 1 , "Signal names need to be derivations"
            anode_tmp.append(i[0])
            catode_tmp.append(i[1])
            signalsName_tmp = signalsName_tmp+[i[0]]+[i[1]]

        if "E3E4" in catode_tmp:
            signalsName_tmp = signalsName_tmp+["E3"]+["E4"]
        
        ind = [i for i in range(len(channel_names)) if channel_names[i] in signalsName_tmp]
        
        edf=raw.pick_channels(channel_names[ind].tolist())
        edf.set_channel_types(dict(zip(channel_names[ind], channel_category[ind])))
        edf.load_data(verbose=True)

        if "E3E4" in catode_tmp:
            subchannels = channel_names[ind]
            rename_tmp = {i:i+"-E3E4" for i in subchannels[channel_category=="eeg"]}
            edf.set_eeg_reference(ref_channels=ref_channels[0], ch_type=ref_channels[1])
            edf.rename_channels(rename_tmp)

        ind = [i for i in range(len(anode)) if (anode[i] in anode_tmp)&(cathode[i] in catode_tmp)]
        if len(ind)>0:
            try:
                # for i in ind:
                edf = mne.set_bipolar_reference(edf, anode=anode[ind].tolist(), cathode=cathode[ind].tolist(),drop_refs=False )
            except MemoryError:
                print("Ran out of memory.....")
                exit()


        ind = [i for i in range(len(rename)) if rename[i] in anode_tmp]
        if len(ind)>0:
            try:
                edf.set_channel_types(dict(zip(rename[ind], rename_category[ind])))
            except MemoryError as mem:
                print("Ran out of memory.....")
                exit()

        indcha = [i for i in range(len(edf.ch_names)) if edf.ch_names[i] in self.signalsNames]
        signals = []
        
        for i in range(len(indcha)):
            if i==0:
                signals_tmp, times = edf[edf.ch_names[indcha[i]]]
            else:
                signals_tmp = edf[edf.ch_names[indcha[i]]][0]
            
            signals.append(signals_tmp)
        
        # print(edf.info['meas_date']+timedelta(seconds=times[0]),edf.info['meas_date']+timedelta(seconds=times[-1]))
        ########### Sanity checks #############
        if self.times_stamps != times[1]:
            print(f"WARNING: data resampled from {1/times[1]} to {1/self.times_stamps} HZ")
            rate = (1/times[1])/(1/self.times_stamps)
            resamp = Resample(prev_hz=1/times[1], next_hz=1/self.times_stamps,filtering=True,up=1, down=rate)
            signals = [resamp.transform(i) for i in signals]
            times = (resamp.transform(times.reshape(1,len(times)))[0,:]).round(3)
            assert times[1]==self.times_stamps
            
        
       
        
        # if (signals[0].shape[1]/(3600/self.times_stamps))>(self.maxHours):
        #     print(f"WARNING: signal length of {signals[0].shape[1]/(3600/self.times_stamps)}H >{self.maxHours}H")
        #     cut = int(self.maxHours*(3600/self.times_stamps))
        #     signals = [i[:,:cut] for i in signals]
        #     times = times[:cut]
           
        # print(edf.info['meas_date']+timedelta(seconds=times[0]),edf.info['meas_date']+timedelta(seconds=times[-1]))
        today = datetime.today()
        s = edf.info['meas_date'].strftime("%H:%M:%S")
        edfstart = datetime.combine(edf.info['meas_date'], datetime.strptime(s, '%H:%M:%S').time())
        edfend= edfstart+timedelta(seconds=signals[0].shape[1]*self.times_stamps)
        
        ############################################################
        metadata = {}
        metadata["edfend"] = edfend
        metadata["edfstart"] = edfstart
        metadata["Measure date"] = edf.info['meas_date']
        metadata["TimeFromStart"] = times
        metadata["FileName"] = self.allEdf[k]
        metadata["FilePath"] = self.allEdf[k]
        metadata["SignalName"] = np.array(edf.ch_names)[np.array(indcha)]
        
        _loaded_signal = PartSignal({"Signal": signals}, partID, s, metadata)
        
        return _loaded_signal
        
    
    def LoadSignals(self, partIDs: List[int], signalsNames=None):
        return [self.Load(partID,signalsNames) for partID in partIDs]


    def FindIntInStr(self,my_list):
        return list(map(int, re.findall(r'\d+', my_list)))
    
    def getallpart(self):
        return np.arange(1,len(self.allEdf)+1)

   
    def saveData(self,name):
        if os.path.isdir(os.path.join('save_data')):
            path_save = os.path.join('save_data')
        else:
            path_save = os.mkdir('save_data')
            path_save = os.path.join('save_data')
        
        path_name = os.path.join(path_save,name+'.pickle')
        i=0
        while os.path.exists(path_name):
            path_name = os.path.join(path_save,name+str(i)+'.pickle')
            i+=1
        with open(path_name, 'wb') as handle:
            pickle.dump(self.data, handle, protocol=pickle.HIGHEST_PROTOCOL)
            
    def loadDataPickle(self,path_name):
        with open(path_name, 'rb') as file:
            self.data = pickle.load(file)

    


if __name__ == "__main__":
    test = Predictors('/datasets/10x100/psg/edf_recordings/')
    one = test.Load(1)
    twothree = test.LoadSignals([2,3])
    # preprocessed_signal = iqr_standardize(cheby2_highpass_filtfilt(resample_2(signal), 64, 0.3)) # preprocessing steps
