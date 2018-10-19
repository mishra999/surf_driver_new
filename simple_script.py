import surf_daq
import time

daq = surf_daq.SurfDaq()
time_string=time.strftime("%Y_%m_%d_%H_%M")
daq.savePedestals("ped_"+time_string+".npy")
daq.stopAcq()
daq.eventsPerTrigger(3)
daq.enableExtTrigger(True)
daq.startAcq()
dataset = daq.getTimedData(1000, until=time.time()+20)
daq.saveDataset(dataset,"dat_"+time_string+".npz")

