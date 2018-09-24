# SURF data acquisition. Replacement for SurfData.

import surf_board
import numpy as np
import time

lab_length=4096

def stripHeaders(event):
    """ strips headers from a dataset """
    nsamples=len(event)
    nblocks=int(nsamples/128)
    headers=[]    
    for i in xrange(nblocks):
        header=event[128*i] & 0xf000
        headers.append(header)
        event[128*i:128*i+128] -= header
        
    return headers

class LabDaq:
    # do something to select a SURF or something...
    def __init__(self, lab):
        self.lab = lab
        self.dev = surf_board.do()
        self.pedestals=np.zeros(lab_length)
        self.dev.labc.reset_fifo()
        self.dev.labc.testpattern_mode(0)
        self.dev.labc.readout_testpattern_mode(0)
        self.dev.labc.run_mode(1)
        print "Starting up..."
        # startup wait, I guess
        time.sleep(1)
        # acquire pedestals. this is soo easy
        print "Pedestal run...",        
        dataset = self.getStrippedForceTriggerData(1000)
        # reshape to 2500x4096... (note, this is O(1) in speed!)
        pedData = np.reshape(dataset['data'],(250,4096))
        # and average (this is vectorized!)
        self.pedestals = np.mean(pedData, 0)
        # plus get an integer copy
        self.intPedestals = np.array(self.pedestals).astype('int16')
        print "complete."

    def stopAcq(self):
        """ Stop the acquisition. """
        self.dev.labc.run_mode(0)

    def startAcq(self):
        """ Start the acquisition (reset, start run mode, dump 4096 samples) """
        self.dev.labc.reset_fifo()
        self.dev.labc.run_mode(1)
        # strip the first 4 which Eric says look goofy
        dummy = self.dev.dma_lab_events(self.lab, 4, 1024, True, False)
        
    
    def getRawForceTriggerData(self,count=10000):
        """ Get a dataset of force triggers, returned raw. """
        dat = self.dev.dma_lab_events(self.lab, count, 1024, True, False)
        npdat = np.frombuffer(dat, dtype='uint16')
        dataset = {}
        dataset['data'] = npdat
        dataset['count'] = count
        return dataset

    def getStrippedForceTriggerData(self,count=10000):
        """ Get a dataset of force triggers, headers stripped. """
        dataset = self.getRawForceTriggerData(count)
        headers = stripHeaders(dataset['data'])
        # This is now an int16 (so it can be pedestal subtracted)
        dataset['data'] = dataset['data'].view('int16')
        dataset['headers'] = headers
        return dataset

    def getSubtractedForceTriggerData(self,count=10000):
        """ Get a dataset of force triggers, pedestal subtracted. """
        dataset = self.getStrippedForceTriggerData(count)
        # keep track of where we are
        eventNumber=0
        # find out what's the first buffer we have.
        startBuffer = (dataset['headers'][0] & 0xC000) >> 12
        # special-case less than 4 events
        if count < 4:
            # Recast our arrays in terms of events (blocks of 1024)
            data = np.reshape(dataset['data'],(count,1024))
            peds = np.reshape(self.intPedestals,(4,1024))
            buffer = startBuffer
            for i in xrange(count):
                data[i] -= peds[i]
                buffer = (buffer + 1) % 4
            return dataset

        # with more than 4 events, we mass pedestal subtract for speed

        # deal with the first set (which might not be aligned with 0)
        earlyData = dataset['data'][0:(4-startBuffer)*1024]
        earlyData -= self.intPedestals[startBuffer*1024:]

        # move forward however many we subtracted
        eventNumber = eventNumber + (4-startBuffer)

        # now jump forward 4 at a time.
        while (count - eventNumber) > 4:
            dataset['data'][eventNumber*1024:(eventNumber+4)*1024] -= self.intPedestals
            eventNumber = eventNumber + 4
        remaining = count - eventNumber
        dataset['data'][eventNumber*1024:] -= self.intPedestals[0:remaining*1024]

        return dataset

    def getForceTriggerData(self, count=10000):
        """ Get a dataset of completely processed force trigger data. """
        dataset = self.getSubtractedForceTriggerData(count)
        # get headers, recast into an event array
        headers = np.reshape(dataset['headers'], (count,8))
        # get data, recast into an event array
        data = np.reshape(dataset['data'],(count,1024))
        # create empty windows array
        dataset['windows'] = []
        for i in xrange(count):
            eventHeaders = headers[i]
            buffer = (eventHeaders[0] & 0xC000)>>12
            windows = np.arange(buffer*8, (buffer+1)*8)
            startBlock = -1
            for j in xrange(8):
                if eventHeaders[j] & 0x2000:
                    startBlock=j
                    break
            if startBlock == -1:
                print "Could not find start bit for event %d!!" % i
                return None
            # roll the data
            data[i]=np.roll(data[i], 128*startBlock)
            # dataset['data'][1024*i:1024*(i+1)]=np.roll(dataset['data'][1024*i:1024*(i+1)],
            #                                            128*startBlock)
            # roll the windows
            windows = np.roll(windows, startBlock)
            # append the windows to the set
            dataset['windows'].append(windows)

        # return the dataset
        return dataset

    def datasetEvents(self, dataset, eventSize=1024):
        return np.reshape(dataset['data'], (dataset['count'], eventSize))
