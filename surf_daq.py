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
    def __init__(self, lab, curveCorrect=False):
        self.lab = lab
        self.dev = surf_board.do()
        self.curveCorrect = curveCorrect
        self.pedestals=np.zeros(lab_length)
        self.pedfit = []
        self.dev.labc.reset_fifo()
        self.dev.labc.testpattern_mode(0)
        self.dev.labc.readout_testpattern_mode(0)
        self.dev.labc.run_mode(1)
        print "Starting up..."
        # startup wait, I guess
        time.sleep(1)
        if curveCorrect:
            print "Transfer curve run...",
            self.transferRun()
            print "complete."
        else:
            # acquire pedestals. this is soo easy
            print "Pedestal run...",        
            self.pedestalRun()
            print "complete."

    def pedestalRun(self):
        dataset = self.getStrippedForceTriggerData(1000)
        # reshape to 2500x4096... (note, this is O(1) in speed!)
        pedData = np.reshape(dataset['data'],(250,4096))
        # and average (this is vectorized!)
        self.pedestals = np.mean(pedData, 0)
        # plus get an integer copy
        self.intPedestals = np.array(self.pedestals).astype('int16')        
        # build the (fake) fits
        for i in xrange(4096):
            self.pedfit.append(np.poly1d([1,-1*self.intPedestals[i]]))

    def transferRun(self):
        curve = self.buildTransferCurve(2000, 3000, 100)
        x = np.arange(2000, 3000, 100)
        pedfits = []
        for i in xrange(4096):            
            # fit voltage = f(code)
            res = np.polyfit(curve[i], x, 2)
            pedfits.append(np.poly1d(res))
            self.pedestals[i] = pedfits[i](2500)
        self.intPedestals = np.array(self.pedestals).astype('int16')
        self.pedfits = pedfits
            
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

    def curveCorrection(self, dataset):
        count = len(dataset['data'])
        startBuffer = (dataset['headers'][0] & 0xC000) >> 12
        idx = 1024*startBuffer
        for i in xrange(count):
            dataset['data'][i] = self.pedfits[idx](dataset['data'][i])
            idx = (idx + 1) % 4096
        return dataset
            
    def getSubtractedForceTriggerData(self,count=10000):
        """ Get a dataset of force triggers, pedestal subtracted. """
        dataset = self.getStrippedForceTriggerData(count)
        if self.curveCorrect:
            return self.curveCorrection(dataset)
        
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
                data[i] -= peds[buffer]
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
            buffer = (eventHeaders[0] & 0xC000)>>14
            windows = np.arange(buffer*8, (buffer+1)*8)
            triggerBlock = -1
            for j in xrange(8):
                if eventHeaders[j] & 0x2000:
                    triggerBlock=j
                    break
            if triggerBlock == -1:
                print "Could not find trigger bit for event %d!!" % i
                return None
            # roll the data. The trigger bit block goes at the end, so it's 7-triggerBlock.
            # np.roll rotates "right", so takes samples at end and puts at beginning
            # i.e. if triggerBlock=7, do nothing
            # if triggerBlock=6, roll 128 samples (so [896:1023],[0:895])
            # if triggerBlock=0, roll 896 samples (so [128:1023],[0:127])
            data[i]=np.roll(data[i], (7-triggerBlock)*128)
            # roll the windows
            windows = np.roll(windows, (7-triggerBlock))
            # append the windows to the set
            dataset['windows'].append(windows)

        # return the dataset
        return dataset

    def datasetEvents(self, dataset, eventSize=1024):
        return np.reshape(dataset['data'], (dataset['count'], eventSize))

    def buildTransferCurve(self, start, stop, step):
        # Measured slew rate is something like 5 ADC channels in 600 events
        # or 120 events/channel.

        # stdev of a measurement is ~+/- 2 channels, so knocking it down
        # a factor of 20 gets you +/- 0.1 channel resolution.

        # create the list of values
        vals = xrange(start, stop, step)
        # create the array to store them in
        res = np.ndarray(shape=(len(vals),4096), dtype=float)
        # index of the loop
        idx=0
        for val in vals:
            self.dev.set_vped(val)
            time.sleep(1)
            events = 1600

            print "Taking %d events for value %d" % (events, val)

            # get the data
            dataset = self.getStrippedForceTriggerData(events)
            # rearrange the data into a 4096x400 array (cells[0] is a list of 400 measurements)
            cells = np.reshape(dataset['data'], (400, 4096)).transpose()
            # take the mean along the measurement axis (0) and store it in the results
            means = np.mean(cells, axis=1)
            print "this is an array of length %d" % len(means)
            print "results is an array of length %d" % len(res[idx])
            res[idx] = means
            idx = idx + 1
        # flop the array so that the result gives
        # res[0] = {y-values for cell 0}
        # res[1] = {y-values for cell 1}

        # reset to vped default
        self.dev.set_vped(2500)
        return res.transpose()
    
def zeroCrossings(dataset):
    # Reshape into arrays of 128, and then transpose. So each row
    # is now the same sample, iterated over all the dataset.
    # e.g. cell[0] is an array of all of the samples of cell[0]
    cells = np.reshape(dataset['data'], (dataset['count']*8, 128)).transpose()
    # is the cell negative?
    cellIsNegative = cells <= 0
    # is the cell positive?
    cellIsPositive = cells > 0
    # shift the positive condition to the left one
    # (so cellIsPositive[0] is cell 1)
    cellIsPositive = np.roll(cellIsPositive, -1, axis=0)
    # detect rising edge
    risingEdge = cellIsPositive*cellIsNegative
    # average all rising edges
    zeroCrossingFraction = np.mean(risingEdge, axis=1)

    # We have to redo this for the seams, because the previous method
    # rolled the cells along the window boundary.
    # We *might* be able to all do this in one, but skip it.
    cells = np.reshape(dataset['data'], (dataset['count'],1024)).transpose()
    # So now we strip out the seams, and only the seams
    # Numpy's slicing does this for us.
    # Start at 127, stop before 1023.
    beforeSeam = cells[127:1023:128]
    # Start at 128, no need to stop (1024 is past bounds)
    afterSeam = cells[128::128]

    beforeSeamNegative = beforeSeam <= 0
    afterSeamPositive = afterSeam > 0

    seamRising = beforeSeamNegative * afterSeamPositive
    seamEdgeFraction = np.mean(seamRising)
    zeroCrossingFraction[127] = seamEdgeFraction
    
    return zeroCrossingFraction


    
            
