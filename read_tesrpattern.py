# import the base controls
from anita_python import ocpci, spi, picoblaze
# import the bitfield class without a name, it's too useful
from anita_python.bf import *
import surf_board1
import surf

import struct
import sys
import time
import numpy as np
import surf_calibrations
import surf_i2c
import benchmark_surf

class read_testpattern:
    def __init__(self, lab):
        self.lab = lab
        self.dev = surf_board1.do(lab)
        lab4, pattern = self.dev.labc.testpattern(lab4=lab)
        print('lab4, pattern', lab4, pattern)
        # self.dev.labc.readout_testpattern_mode(enable=True)
        self.dev.labc.testpattern_mode(1)
        self.getRawForceTriggerData(count=1024)
        # self.bm = benchmark_surf.benchmarker(self.dev)
        
        # time.sleep(1)
        # self.print_data(count=10)

    def stopAcq(self):
        """ Stop the acquisition. """
        self.dev.labc.run_mode(0)

    def startAcq(self):
        """ Start the acquisition """
        self.dev.labc.reset_fifo()
        self.dev.labc.run_mode(1)

    def getRawForceTriggerData(self,count=10000):
        """ Get a dataset of force triggers, returned raw. """
        # self.eventsPerTrigger(1)
        self.startAcq()
        # self.dev.labc.start()
        dat = self.dev.dma_lab( lab=self.lab, samples=1024)
        np.savetxt('file9.txt',dat)
        print('data saved')
        self.stopAcq()
        # self.startAcq()
        # dat = self.dev.dma_lab_events(self.lab, count, 1024, True, False)
        # npdat = np.frombuffer(dat, dtype='uint16')
        print(dat[0:100])
        # self.startAcq()
        dataset = {}
        dataset['data'] = npdat
        dataset['count'] = count
        return dataset
    
    def print_data(self, count):
        """ print data from dma """
        self.stopAcq()
        # self.enableExtTrigger(False)
        # self.eventsPerTrigger(1)
        self.bm.time_dma_and_copy(nloops=10)
        # dat=self.getRawForceTriggerData(count)
        # print(dat[1])
        labcontrol = bf(self.dev.labc.read(self.dev.labc.map['CONTROL']))
        # while (labcontrol[15] == 0):
        #     labcontrol = bf(self.dev.labc.read(self.dev.labc.map['CONTROL']))
        self.dev.status()
        return
        self.startAcq()
        dataset = self.getRawForcetestpatternData(1000)
        print(dataset['data'])
        print(len(dataset['data']))
        self.dev.labc.run_mode(0)



