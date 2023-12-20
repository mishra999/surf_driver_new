# SURF data acquisition. Replacement for SurfData.

import surf_board
import surf_board1
import numpy as np
import time
from threading import Thread, Event
import surf_dataset
import surf_analysis
# import matplotlib.sc

lab_length=4096



""" this crap doesn't work, there's some problem in batch DMA right now """
class AcquisitionWorker(Thread):
    def __init__(self, dev, nevents, samples=1024, autotrigger=False, verbose=False):
        Thread.__init__(self)
        self.nevents = nevents
        self.dev = dev
        self.total_data = bytearray(nevents*12*samples*2)
        self.samples = samples
        self.stopper = Event()
        self.autotrigger = autotrigger
        self.verbose = verbose

    # Called from outside world
    def stop(self):
        self.stopper.set()
        self.dev.labc.force_trigger()
        
    def run(self):
        verbose = self.verbose
        autotrigger = self.autotrigger
        
        if not self.dev.dma_enabled():
            print ("DMA not supported, can't start thread.")
            return None

        increment = self.samples*12*2
        self.dataset = {}
        ptr = 0
        endptr = increment
        # set up DMA
        self.dev.prep_batch_dma(self.samples, self.dev.dma_base())
        # Mask everything except FIFO full.
        self.dev.write(self.dev.map['INTMASK'], ~0x2)
        self.dev.irq_unmask()
        self.dev.labc.run_mode(1)
        while self.nevents > 0 and not self.stopper.is_set():
            if autotrigger:
                if verbose:
                    print ("worker: triggering")
                self.dev.labc.force_trigger()
                    
            if verbose:
                print ("worker: %d events remaining, waiting for event" % self.nevents)
            # wait for an interrupt
            ret = self.dev.irq_wait()

            if verbose:
                print ("worker: (ret %d) got event, beginning DMA" % ret)
            # begin dma
            self.dev.write(0x4000C, 0x1)
            # re-prep the next DMA
            self.dev.prep_batch_dma(self.samples, self.dev.dma_base())
            # switch to DMA interrupt
            self.dev.write(0xC, ~0x4)
            # unmask interrupts
            self.dev.irq_unmask()
            # and wait again
            ret = self.dev.irq_wait()
            if verbose:
                print ("worker: (ret %d) DMA complete" % ret)
            # clear the DMA interrupt
            self.dev.write(0x4000C, 0x20)

            # DMA complete, swap to FIFO full interrupt again...
            self.dev.write(0xC, ~0x2)
            # and unmask
            self.dev.irq_unmask()

            # copy the data
            self.total_data[ptr:endptr] = self.dev.dma_read(increment)
            ptr = ptr + increment
            endptr = endptr + increment
            self.nevents = self.nevents - 1

        if self.stopper.is_set():
            if verbose:
                print ("worker stopped at %d events" % self.nevents)


def stripHeaders(event):
    """ strips headers from a dataset """
    nsamples=len(event)
    nblocks=int(nsamples/128)
    headers=[]    
    for i in range(nblocks):
        header=event[128*i] & 0xf000
        headers.append(header)
        event[128*i:128*i+128] -= header
        
    return headers

class SurfDaq:
    def __init__(self, calFilePrefix=None): #"proto_cal"
        """ Create a SurfDaq from a bunch of calibration files with calFilePrefix (followed by lab number.npz). """
        self.dev = surf_board.do()
        self.pedestals=np.zeros((12, lab_length))
        self.dev.labc.reset_fifo()
        self.dev.labc.testpattern_mode(0)
        self.dev.labc.readout_testpattern_mode(0)
        self.dev.set_vped(2500)

        if calFilePrefix is not None:
            for lab in range(12):                
                filename = calFilePrefix + str(lab) + ".npz"
                print ("Loading calibrations for LAB%d from %s" % (lab, filename))
                cal = np.load(filename)
                trims = cal['trim'].astype('int')
                fb = cal['vtrimfb']
                for i in range(128):
                    self.dev.labc.l4reg(lab,256+i,trims[i])
                if fb is not None:
                    self.dev.labc.l4reg(lab,11, fb)
                
                
        self.dev.labc.run_mode(1)        
        print ("Starting up...")
        time.sleep(2)
        print ("Pedestal run..."),
        self.pedestalRun() #by me
        print ("complete.")

    def resetAcq(self):
        """ stop/start acquisition """
        self.stopAcq()
        self.startAcq()
        
    def stopAcq(self):
        """ Stop the acquisition. """
        self.dev.labc.run_mode(0)

    def startAcq(self):
        """ Start the acquisition """
        self.dev.labc.reset_fifo()
        self.dev.labc.run_mode(1)

    def eventsPerTrigger(self, per):
        """ Set the number of events for every trigger. """
        if per < 1 or per > 3:
            print ("must be between 1 and 3")
            return
        self.dev.labc.repeat_count(per-1)

    def enableExtTrigger(self, enable):
        """ Enables (if enable=True) or disables (if enable=False) the external trigger """
        self.dev.extTrig(enable)
        
    def pedestalRun(self):
        """ Get a pedestal set. (Note this also disables ext triggers and sets it to 1 event/trigger) """
        self.stopAcq()
        self.enableExtTrigger(False)
        self.eventsPerTrigger(1)
        self.startAcq()
        dataset = self.getStrippedForceTriggerData(1000)
        # print(dataset['data'])
        print('length of data', len(dataset['data']))
        # reshape to 250x4x12x1024
        byevent = np.reshape(dataset['data'], (250, 4, 1, 1024)) #(250, 4, 12, 1024)
        # transpose to 12x250x4x1024
        eventbylab = byevent.transpose(2, 0, 1, 3)
        # So now index[0] is LAB, index[1] is quad-event, index[2] is buffer (4 buffers per event), and index[3] is sample

        # And now average along index 1
        pedDataByBuffer = np.mean(eventbylab, 1)
        # and reshape (this actually copies, because it's non-contiguous)
        pedData = np.reshape(pedDataByBuffer, (1, 4096)) #(12, 4096)

        # and we're done
        self.updatePedestals(pedData)

    def updatePedestals(self, pedData):
        self.pedestals = pedData
        # and an integer copy (12x4096)
        self.intPedestals = self.pedestals.astype('int16')
        # and a rearranged copy (4x12288, aligned along buffers) for pedestal subtraction
        self.intPedestalsByBuffer = self.intPedestals.reshape((12,4,1024)).transpose((1,0,2)).reshape((4,12288))        
        # This copy is used because when data is received, it's received along buffer boundaries:
        # e.g. (12x1024),(12x1024),(12x1024),etc.
        
    def savePedestals(self, filename):
        np.save(filename, self.pedestals)    

    def loadPedestals(self, filename):
        peds = np.load(filename)
        self.updatePedestals(peds)

    def processStripHeaders(self, dataset):
        headers = stripHeaders(dataset['data'])
        dataset['data'] = dataset['data'].view('int16')
        dataset['headers'] = np.asarray(headers)
        return dataset

    def processSubtractPedestals(self, dataset):
        # get total count
        count = dataset['count']
        # keep track of where we are
        eventNumber=0
        # reshape the headers ( nevents x lab x 8)
        headersByLab = dataset['headers'].reshape((dataset['count'],12,8))
        # find out what's the first buffer we have. (event 0 lab 0 window 0)
        startBuffer = (headersByLab[0][0][0] & 0xC000) >> 14
        print( "Starting with buffer %d." % startBuffer)
        # special-case less than 4 events        
        if count < 4:
            buffer = startBuffer
            # Recast our arrays in terms of events (blocks of 12288)
            data = np.reshape(dataset['data'],(count,12288))
            peds = self.intPedestalsByBuffer
            for i in range(count):
                data[i] -= peds[buffer]
                buffer = (buffer + 1) % 4
            return dataset

        flatPedestals = self.intPedestalsByBuffer.reshape((49152))

        # deal with the first set (which might not be aligned with 0)
        earlyData = dataset['data'][0:(4-startBuffer)*12*1024]
        earlyData -= flatPedestals[startBuffer*12*1024:]

        # move forward however many we subtracted
        eventNumber = eventNumber + (4-startBuffer)

        # now jump forward 4 at a time.
        while (count - eventNumber) > 4:
            dataset['data'][eventNumber*12*1024:(eventNumber+4)*12*1024] -= flatPedestals
            eventNumber = eventNumber + 4
        # how many are remaining?
        remaining = count - eventNumber
        dataset['data'][eventNumber*12*1024:] -= flatPedestals[0:remaining*12*1024]

        return dataset

    def processOrderWindows(self, dataset):
        count = dataset['count']
        # get headers, recast into an event array
        headers = np.reshape(dataset['headers'], (count,12,8))
        # get data, recast into an event array
        data = np.reshape(dataset['data'],(count,12,1024))
        # create empty windows array
        dataset['windows'] = []
        for i in range(count):
            for lab in range(12):
                eventHeaders = headers[i][lab]
                buffer = (eventHeaders[0] & 0xC000)>>14
                windows = np.arange(buffer*8, (buffer+1)*8)
                triggerBlock = -1
                for j in range(8):
                    if eventHeaders[j] & 0x2000:
                        triggerBlock=j
                        break
                if triggerBlock == -1:
                    print( "Could not find trigger bit for event %d!!" % i)
                    return None
                # roll the data. The trigger bit block goes at the end, so it's 7-triggerBlock.
                # np.roll rotates "right", so takes samples at end and puts at beginning
                # i.e. if triggerBlock=7, do nothing
                # if triggerBlock=6, roll 128 samples (so [896:1023],[0:895])
                # if triggerBlock=0, roll 896 samples (so [128:1023],[0:127])
                data[i][lab]=np.roll(data[i][lab], (7-triggerBlock)*128)
                # roll the windows
                windows = np.roll(windows, (7-triggerBlock))
                # append the windows to the set
                dataset['windows'].append(windows)

        # return the dataset
        return dataset

    ## Convenience function to save dataset
    def saveDataset(self, dataset, filename):
        surf_dataset.saveDataset(dataset,filename)
    
    ## Convenience functions for forced trigger data
    
    def getRawForceTriggerData(self,count=1000):
        """ Get a dataset of force triggers, returned raw. """
        # dat = self.dev.dma_lab_events(lab=15,nevents=count, samples=1024, force_trig=True)
        # self.dev.labc.force_trigger()
        # dat = self.dev.dma_event(samples=1024)
        dat = self.dev.log_lab(lab=15, samples=1024, force_trig=True, save=False)
        print ("Acquisition complete.")
        print('dataset raw=', dat[0:100])
        return surf_dataset.buildDataset(dat, count)

    def getStrippedForceTriggerData(self,count=1000):
        """ Get a dataset of force triggers, headers stripped. """
        dataset = self.getRawForceTriggerData(count)
        print ("Stripping headers.")
        return self.processStripHeaders(dataset)

    def getSubtractedForceTriggerData(self,count=1000):
        """ Get a dataset of force triggers, pedestal subtracted. """
        dataset = self.getStrippedForceTriggerData(count)
        print ("Subtracting pedestals.")
        return self.processSubtractPedestals(dataset)

    def getForceTriggerData(self, count=1000):
        """ Get a dataset of force triggers, fully processed. """
        dataset = self.getSubtractedForceTriggerData(count)
        print ("Reordering windows.")
        return self.processOrderWindows(dataset)

    ## Convenience functions for triggered data

    def getRawData(self,count=1000, until=None):
        dat = self.dev.dma_events(count, 1024, until=until)
        if until is None:
            return surf_dataset.buildDataset(dat, count)
        else:
            # might have less data
            count = len(dat)/(12*1024*2)
            return surf_dataset.buildDataset(dat, count)
        
    def getStrippedData(self,count=1000, until=None):
        dataset = self.getRawData(count, until)
        return self.processStripHeaders(dataset)

    def getSubtractedData(self,count=1000, until=None):
        dataset = self.getStrippedData(count, until)
        return self.processSubtractPedestals(dataset)

    def getData(self,count=1000, until=None):
        dataset = self.getSubtractedData(count, until)
        return self.processOrderWindows(dataset)

    ## Convenience functions for timed data
    def getTimedData(self, count=1000, until=None, every=None):
        dat, times = self.dev.dma_events(count, 1024, until=until, time_events=True, every=every)
        if until is None:
            dataset = surf_dataset.buildDataset(dat, count)
            dataset['times'] = times
        else:
            # might have less data
            count = len(times)
            dataset = surf_dataset.buildDataset(dat, count)
            dataset['times'] = times
        dataset = self.processStripHeaders(dataset)
        dataset = self.processSubtractPedestals(dataset)
        dataset = self.processOrderWindows(dataset)
        return dataset

    """ measure the timebase, assuming a sine wave input """
    def getTimes(self, count=1000, frequency=235.e6):
        dataset = self.getForceTriggerData(nsamples)
        zc = surf_analysis.zeroCrossings(dataset)
        return zc*1.e12/freq
        
class LabDaq:
    # do something to select a SURF or something...
    def __init__(self, lab, curveCorrect=False, calFile=None):
        self.lab = lab
        self.dev = surf_board1.do(lab)
        
        self.curveCorrect = curveCorrect
        self.pedestals=np.zeros(lab_length)
        self.pedfit = []
        self.dev.labc.reset_fifo()
        self.dev.labc.testpattern_mode(0)
        self.dev.labc.readout_testpattern_mode(0)
        self.dev.labc.run_mode(1)
        print ("Loading calibration file...")
        if calFile is not None:
            cals = np.load(calFile)
            update_trims_one(self, lab, cals['trim'].astype('int'), cals['vtrimfb'])
        print ("Starting up...")
        # startup wait, I guess
        time.sleep(2)
        if curveCorrect:
            print ("Transfer curve run..."),
            self.transferRun()
            print ("complete.")
        else:
            # acquire pedestals. this is soo easy
            print ("Pedestal run..."),        
            self.pedestalRun()
            print ("complete.")

    def pedestalRun(self):
        self.eventsPerTrigger(1)
        # dataset = self.getStrippedForceTriggerData(1000)
        dataset = self.getRawForceTriggerData(count=1000)
        print(dataset[0:10])
        np.savetxt('data_txt', dataset)
        # reshape to 2500x4096... (note, this is O(1) in speed!)
        # pedData = np.reshape(dataset['data'],(250,4096))
        # print(pedData[0])
        # and average (this is vectorized!)
        # self.pedestals = np.mean(pedData, 0)
        # # plus get an integer copy
        # self.intPedestals = np.array(self.pedestals).astype('int16')        
        # # build the (fake) fits
        # for i in range(4096):
        #     self.pedfit.append(np.poly1d([1,-1*self.intPedestals[i]]))

    def transferRun(self):
        curve = self.buildTransferCurve(2000, 3000, 100)
        x = np.arange(2000, 3000, 100)
        pedfits = []
        for i in range(4096):            
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
        """ Start the acquisition """
        self.dev.labc.reset_fifo()
        self.dev.labc.run_mode(1)

    def eventsPerTrigger(self, per):
        """ Set the number of events for every trigger. """
        if per < 1 or per > 3:
            print ("must be between 1 and 3")
            return
        self.dev.labc.repeat_count(per-1)

    def processStripHeaders(self, dataset):
        """ strip headers from dataset """
        headers = stripHeaders(dataset['data'])
        # This is now an int16 (so it can be pedestal subtracted)
        dataset['data'] = dataset['data'].view('int16')
        dataset['headers'] = headers
        return dataset

    def processSubtractPedestals(self, dataset):
        """ subtract pedestals from dataset """
        count = dataset['count']
        # keep track of where we are
        eventNumber=0
        # find out what's the first buffer we have.
        startBuffer = (dataset['headers'][0] & 0xC000) >> 14
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

    def processOrderWindows(self, dataset):
        """ reorder windows in dataset """
        
        count = dataset['count']
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
                print ("Could not find trigger bit for event %d!!" % i)
                print ("I'm skipping this event, and marking it as an error")
                if not 'errors' in dataset:
                    dataset['errors'] = []
                dataset['errors'].append(i)
            else:
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

    
    def getRawForceTriggerData(self,count=10000):
        """ Get a dataset of force triggers, returned raw. """
        # dat = self.dev.pio_lab(self.lab, samples=102)
        # print('data from pio_lab',dat)
        dat = self.dev.dma_lab_events(self.lab, count, 1024, True, False)
        print(dat)
        npdat = np.frombuffer(dat, dtype='uint16')
        # print(npdat[0:100])
        # dataset = {}
        # dataset['data'] = npdat
        # dataset['count'] = count
        return dat

    def getStrippedForceTriggerData(self,count=10000):
        """ Get a dataset of force triggers, headers stripped. """
        dataset = self.getRawForceTriggerData(count)
        return self.processStripHeaders(dataset)

    def getSubtractedForceTriggerData(self,count=10000):
        """ Get a dataset of force triggers, pedestal subtracted. """
        dataset = self.getStrippedForceTriggerData(count)
        return self.processSubtractPedestals(dataset)
    
    def getForceTriggerData(self, count=10000):
        """ Get a dataset of completely processed force trigger data. """
        dataset = self.getSubtractedForceTriggerData(count)
        return self.processOrderWindows(dataset)


    def datasetEvents(self, dataset, eventSize=1024):
        """ convenience function for reshaping datasets into events """
        return np.reshape(dataset['data'], (dataset['count'], eventSize))

    def getTimes(self, count=10000, frequency=235.e6):
        """ measure the timebase, assuming a sine wave input """
        dataset = self.getForceTriggerData(count)
        zc = surf_analysis.zeroCrossingsLab(dataset)
        return zc*1.e12/frequency
    
    def buildTransferCurve(self, start, stop, step):
        """ build the DC transfer curve for this LAB """

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

            print ("Taking %d events for value %d" % (events, val))

            # get the data
            dataset = self.getStrippedForceTriggerData(events)
            # rearrange the data into a 4096x400 array (cells[0] is a list of 400 measurements)
            cells = np.reshape(dataset['data'], (400, 4096)).transpose()
            # take the mean along the measurement axis (0) and store it in the results
            means = np.mean(cells, axis=1)
            print ("this is an array of length %d" % len(means))
            print ("results is an array of length %d" % len(res[idx]))
            res[idx] = means
            idx = idx + 1
        # flop the array so that the result gives
        # res[0] = {y-values for cell 0}
        # res[1] = {y-values for cell 1}

        # reset to vped default
        self.dev.set_vped(2500)
        return res.transpose()

import scipy.interpolate as spint

dt_slow        = [360, 180, 120, 70., 40., 20., 7., 3.5, 2., 1., 0.2, 0.0] #ps slow
trim_adj_slow  = [-300, -200, -110, -50, -20, -10, -6, -4, -3, -2, -1, 0] 
  
dt_fast = [dt*-1 for dt in dt_slow]
trim_adj_fast = [trim*-1 for trim in trim_adj_slow]

trim_adj_slow = [trim*2 for trim in trim_adj_slow] #sitting on an exponential curve

trim_adj_fast_lut =  np.arange(0, max(trim_adj_fast))
trim_adj_slow_lut =  np.arange(min(trim_adj_slow),0)

dt_fast_lut = spint.interp1d(trim_adj_fast[::-1], dt_fast[::-1], kind='linear', axis=0)(trim_adj_fast_lut)
dt_slow_lut = spint.interp1d(trim_adj_slow, dt_slow, kind='linear', axis=0)(trim_adj_slow_lut)

minimizer_trim_adj_lut = np.hstack(( trim_adj_slow_lut, trim_adj_fast_lut))
minimizer_dt_diff_lut  = np.hstack(( dt_slow_lut, dt_fast_lut ))

max_trim = 2500

def tune(times, trims,start=0,stop=127,scale=1):
    """ Adjustment function for trim DACs.

    param: times: Measured timebase.
    param: trims: Current trim values.
    param: start: Cell # to start at.
    param: stop:  Cell # to stop before.
    param: scale: Multiply all adjustment values by this scale.
    """
    updated_trims=np.copy(trims)
    for i in np.arange(start,stop):
        dt_diff_lut_index = np.where(minimizer_dt_diff_lut > (times[i]-312.5))[0][-1]
        trim_adjustment = minimizer_trim_adj_lut[dt_diff_lut_index]
        if i == 126:
            trim_adjustment = trim_adjustment*2
        # we adjust trim i+1 for time i
        updated_trims[i+1] = trims[i+1] + trim_adjustment*scale
        print ("sample %d %f ps: %d -> %d" % (i, times[i], trims[i+1], updated_trims[i+1]))
        if updated_trims[i+1] > max_trim:
            print ("sample %d maxed out" % i)
            updated_trims[i+1] = max_trim
        elif updated_trims[i+1] < 0:
            print ("sample %d minned out" % i)
            updated_trims[i+1] = 0
    return updated_trims

def update_trims_one(daq, lab, trims, fb=None):
    """ Convenience function to update trims on a LabDaq. """
    daq.stopAcq()
    for i in range(128):
        daq.dev.labc.l4reg(lab,256+i,trims[i])
    if fb is not None:
        daq.dev.labc.l4reg(lab,11, fb)
    daq.startAcq()
                                         
def update_all_trims(daq, trims, fbs=None):
    """ Convenience function to update all trims on a SurfDaq. """
    daq.stopAcq()
    for lab in range(12):
        for cell in range(128):
            daq.dev.labc.l4reg(lab,256+cell, trims[lab][cell])
    if fbs is not None:
        for lab in range(12):
            print ("set vtrimfb %d to %d" % (lab, fbs[lab]))
            daq.dev.labc.l4reg(lab, 11, fbs[lab])
    daq.startAcq()

def tuneOutliers(daq, iterations, trims, fb, samples=10000, frequency=235.e6):
    """ Cleanup trim DAC pass.

    This function cleans up any outlier samples in the feedback tuning.
    This is usually just the slow sample. "Outliers" are times which
    are further than ~2 standard deviations or 10 picoseconds, whichever
    is larger. Note that the feedback sample is allowed to be a bit larger
    (3 standard deviations) just because adjusting the feedback creates
    more scatter in everyone else, so trying to tune the feedback constantly
    can lead to the function never completing.

    param: daq: surf_daq data acquisition object (a LabDaq)
    param: iterations: number of iterations to try to fix outliers
    param: trims: Trim DAC settings.
    param: fb: Feedback setting.
    param: samples: Number of samples in each timing run. This should be larger than the tune run.
    param: frequency: Frequency of the sine wave input.
    
    """
    lab = daq.lab
    it = 0
    outliers=128
    while it < iterations and outliers > 0:
        times = daq.getTimes(samples)
        stdev = np.std(times[0:127])
        print ("pass %d stdev %f" % (it, stdev))
        if stdev < 5:
            stdev = 5
        if np.abs(times[127]-312.5) > 3*stdev:
            print ("feedback is an outlier (%f)" % times[127])
            diff = times[127]-312.5
            delta = 0
            if np.abs(diff) > 100:
                delta = 15 if diff > 0 else -15
            elif np.abs(diff) > 50:
                delta = 7 if diff > 0 else -7
            elif np.abs(diff) > 25:
                delta = 3 if diff > 0 else -3
            else:
                delta = 1 if diff > 0 else -1
            fb = fb + delta
        else:
            outliers = 0            
            for cell in xrange(127):
                if np.abs(times[cell]-312.5) > 2*stdev:
                    print ("cell %d is an outlier (%f)" % (cell, times[cell]))
                    trims = tune(times, trims, cell, cell+1, 4)
                    outliers = outliers + 1
            print ("pass %d, %d outliers" % (it, outliers))
            it = it + 1
        trims=trims.astype('int')
        update_trims_one(daq, lab, trims, fb)

    return (trims, fb)

def tuneLoop(daq, iterations, samples=10000, trims=None, fb=None, frequency=235.e6, trimHistory=None, afg=None):
    """ Calibrate the trim DACs.

    This function calibrates the trim DACs. It needs an external
    signal generator (something that has a set_output and recall
    function) because it needs to recalculate pedestals after
    each loop.
    
    param: daq: surf_daq type DAQ object.
    param: iterations: Number of tuning iterations to take.
    param: samples: Number of samples to take. Note this usually limits tune precision.
    param: trims: Initial trims. If these are 'none', tuneLoop will try to find a good starting pont.
    param: fb: Initial feedback. Needs to be provided with trims if trims is provided.
    param: frequency: Frequency of the sine wave provided.
    param: trimHistory: If provided, tuneLoop stores the times in each iteration in this array.
    param: afg: Device to turn on/off carrier. If this is a first-time tune this MUST be provided.
    
    """
    # basic overall logic:
    # 1) raising vtrimfb = times[127] goes down
    #    lowering vtrimfb = times[127] goes up
    # 2) raising other trim DACs = times[126] goes down
    #    lowering other trim DACs = times[126] goes up    
    lab = daq.lab
    if trims is None:
        print ("Finding initial starting points.")
        startPoint = 2000
        trims = np.full(128, startPoint)
        trims[0] = 0
        trims[127] = 500
        fb = 1300
        update_trims_one(daq, lab, trims, fb)
        times = daq.getTimes(samples)
        # We need to make sure that we're not *so* far off on the feedback
        # that we've slipped a full sample (e.g. times[127] should be
        # *negative*)
        # The loop tune is slow enough that it shouldn't happen, I hope
        while np.sum(times[0:127]) > 39900:
            print ("Feedback LAB%d way off (%f): %d -> %d" % (lab, 40000-np.sum(times[0:127]), fb, fb-20))
            fb -= 20
            update_trims_one(daq, lab, trims, fb)
            times = daq.getTimes(samples)
        slowSample = times[126]
        seamSample = times[127]
        # We're trying to find a starting point where the feedback isn't
        # totally borked (close to 312.5) and the slow sample is below 290
        # so that it's likely that it can be tuned.
        while slowSample > 290 or seamSample > 350 or seamSample < 290:
            if seamSample < 290 or seamSample > 350:
                delta = 5 if seamSample > 350 else -5
                print ("Feedback LAB%d: %f (%d -> %d)" % (lab, seamSample, fb, fb+delta))
                fb = fb + delta
            elif slowSample > 290:
                print ("Starting LAB%d: %f (%d -> %d)" % (lab, slowSample, trims[1], trims[1]+25))
                trims[1:127] += 25
            update_trims_one(daq, lab, trims, fb)
            times = daq.getTimes(samples)
            slowSample=times[126]
            seamSample=times[127]
        print ("LAB%d: starting point %d (slow=%f) feedback %d (%f)" % (lab, trims[1], slowSample, fb, seamSample) )       

    update_trims_one(daq, lab, trims, fb)
    it=0
    while it < iterations:
        if afg is not None:
            afg.set_output(0)
            time.sleep(1)
        daq.pedestalRun()
        if afg is not None:
            afg.recall()
            afg.set_output(1)
            time.sleep(1)
        times = daq.getTimes(samples)
        if trimHistory is not None:
            trimHistory[it] = times

        print( "std: %f ps" % np.std(times))
        seamSample = times[127]
        # just coarse adjust the seam, hopefully this is good enough
        if np.abs(seamSample-312.5) > 20:
            diff = seamSample - 312.5
            delta = 0
            if np.abs(diff) > 100:
                delta = 15 if diff > 0 else -15
            elif np.abs(diff) > 50:
                delta = 7 if diff > 0 else -7
            else:
                delta = 3 if diff > 0 else -3
            print ("Feedback LAB%d: %f (%d -> %d)" % (lab, seamSample, fb, fb+delta))
            fb = fb + delta
        else:
            trims = tune(times, trims)
            trims = trims.astype('int')
            it = it + 1
        update_trims_one(daq, lab, trims, fb)
    for i in range(len(trims)):
        print ("trim[%d]=%d" % (i, trims[i]))
    print ("vtrimfb = %d" % fb)
    return (trims, fb)

def tuneAllLoop(daq, iterations, samples=1000, trims=None, fbs=None, frequency=235.e6):
    """ Doesn't work yet, don't use this.
    """
    if trims is None:
        print ("Finding initial starting points.")
        startPoint = 2100
        trims = np.full((12,128), startPoint)
        trims.transpose()[0] = 0
        trims.transpose()[127] = 500
        update_all_trims(daq, trims, fbs)
        times = getTimes(daq, samples)
        allSlowSamples = times[:,126]
        allSeamSamples = times[:,127]
        while any(np.greater(allSlowSamples, 290)) or any(np.greater(allSeamSamples, 290)) or any(np.less(allSeamSamples, 350)):
            for lab in xrange(12):
                if allSeamSamples[lab] < 290 or allSeamSamples[lab] > 350:
                    print ("Feedback LAB%d: %f (%d)" % (lab, allSeamSamples[lab], fbs[lab]))
                    if allSeamSamples[lab] < 290:
                        fbs[lab] -= 5
                    else:
                        fbs[lab] += 5
                elif allSlowSamples[lab] > 290.:
                    print ("LAB%d's slow sample: %f, baseline %d->%d" % (lab, allSlowSamples[lab], trims[lab][1], trims[lab][1]+25))
                    trims[lab][1:127] += 25
            update_all_trims(daq, trims, fbs)
            times = getTimes(daq, samples)
            allSlowSamples = times[:,126]
            allSeamSamples = times[:,127]
        print ("Baseline starting points:")
        for lab in xrange(12):
            print ("LAB%d: %d (%f %f)" % (lab, trims[lab][1], allSlowSamples[lab], times[lab][127]))
        return
    for it in range(iterations):
        times = getTimes(daq, samples)
        for lab in range(12):
            trims[lab] = tune(times[lab], trims[lab])
        update_all_trims(daq, trims, fbs)
    times = getTimes(daq, samples)
    for lab in range(12):
        print ("LAB%d RMS %f ps" % (lab, np.std(times[lab])))
