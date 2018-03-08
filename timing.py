import numpy as np
import time
import sys
import fit

nominal_dt = 312.50000000000000 #ps
max_trim   = 2540 #sort-of arbitrary limit for trim-dac

def zero_crossings(data, lab, mean_subtract=True, prim_cell_zero_mean=True, return_cell_profile=False):
    '''
    zero crossings counter
    data: should be numpy array
    prim_cell_zero_mean: flag to calculate mean of each cell from full dataset and subtract cell-by-cell
    return_cell_profile: return profile of each cell (a list of 128 lists)
    '''    
    zero_crossings_all_channels=[]
        
    if not isinstance(lab, list):
        lab=[lab]

    for l in lab:
        zero_cross = np.zeros(128, dtype=float)
        zero_amps  = np.zeros(128, dtype=float)
        num_entries = 0
        num_entries_wrap = 0

        if prim_cell_zero_mean:
            cell_profile = []
            for c in range(128):
                cell_profile.append([])
            for i in range(len(data)):
                d=data[i,l,:]
                for buf in range(0, 8):
                    for k in range(0, 128):
                        cell_profile[k].append( d[k+(buf*128)])
        
            cell_profile_mean=np.zeros(128, dtype=float)
            for c in range(128):
                cell_profile_mean[c] = sum(cell_profile[c]) / float(len(cell_profile[c]))
            
            if return_cell_profile:
                return cell_profile
        
        for i in range(len(data)):       
            d = data[i,l,:]

            if mean_subtract and not prim_cell_zero_mean:
                d = d-np.mean(d)

            for buf in range(0, 8):
                num_entries = num_entries + 1

                for k in range(0, 127):
                    v_samp    = d[k+(buf*128)]
                    v_samp_p1 = d[k+(buf*128)+1]

                    if prim_cell_zero_mean:
                        v_samp    = float(v_samp)    - cell_profile_mean[k]
                        v_samp_p1 = float(v_samp_p1) - cell_profile_mean[k+1]

                    '''rising edge condition'''
                    if (v_samp <= 0.) and (v_samp_p1 > 0.):
                        zero_cross[k+1] = zero_cross[k+1] + 1.
                        zero_amps[k+1] = zero_amps[k+1] + abs(v_samp_p1-v_samp)

                    '''falling edge condition'''
                    if (v_samp >= 0.) and (v_samp_p1 < 0.):
                        zero_cross[k+1] = zero_cross[k+1] + 1.
                        zero_amps[k+1] = zero_amps[k+1] + abs(v_samp_p1-v_samp)

                '''handle wraparound'''
                if  (buf < 7):
                    v_samp    = d[127+(buf*128)]
                    v_samp_p1 = d[128+(buf*128)]
                    
                    if prim_cell_zero_mean:      
                        v_samp    = float(v_samp)    - cell_profile_mean[127]
                        v_samp_p1 = float(v_samp_p1) - cell_profile_mean[0]

                    '''rising edge condition for DLL seam'''
                    if  (v_samp <= 0.) and (v_samp_p1 > 0.):
                        zero_cross[0] = zero_cross[0] + 1.
        
                    '''falling edge condition for DLL seam'''
                    if  (v_samp >= 0.) and (v_samp_p1 < 0.):
                        zero_cross[0] = zero_cross[0] + 1.

                    num_entries_wrap = num_entries_wrap + 1

        num_entries_array=np.ones(128, dtype=float) * num_entries * 2
        num_entries_array[0] = num_entries_wrap * 2
        zero_crossings_all_channels.append(np.divide(zero_cross, num_entries_array))
        
    return zero_crossings_all_channels

def sample_correlation(data, lab, sampl, sampl_interval=1, transfBank=None, mean_subtract=True, fromFile=False):

    all_sums=[]
    all_subs=[]

    if not isinstance(lab, list):
        lab=[lab]

    for l in lab:
        corr_add = []
        corr_sub = []

        if fromFile:
            '''data imported from flat text file has different array shape'''
            for i in range(0,len(data), 1024):       
                d = data[i:(i+1024),l]

                if mean_subtract:
                    d = d-np.mean(d)
            
                for k in range(128, 1024-sampl_interval): #start at 128 case unwrapping issues in firmware
                    if transfBank == 0  and (k % 128) == sampl and (k % 256) < 128:
                        v_samp_0 = d[k]
                        v_samp_1 = d[k+sampl_interval]
                        corr_add.append(v_samp_0 + v_samp_1)
                        corr_sub.append(v_samp_0 - v_samp_1)
                    
                    elif transfBank == 1  and (k % 128) == sampl and (k % 256) >= 128:
                        v_samp_0 = d[k]
                        v_samp_1 = d[k+sampl_interval]
                        corr_add.append(v_samp_0 + v_samp_1)
                        corr_sub.append(v_samp_0 - v_samp_1)

                    elif (k % 128) == sampl and transfBank==None:
                        v_samp_0 = d[k]
                        v_samp_1 = d[k+sampl_interval]
                        corr_add.append(v_samp_0 + v_samp_1)
                        corr_sub.append(v_samp_0 - v_samp_1)

        else:
            for i in range(len(data)):       
                d = data[i,l,:]
                if mean_subtract:
                    d = d-np.mean(d)
            
                for k in range(128, 1024-sampl_interval):
                    if (k % 128) == sampl:

                        v_samp_0 = d[i][k]
                        v_samp_1 = d[i][k+sampl_interval]
                    
                        corr_add.append(v_samp_0 + v_samp_1)
                        corr_sub.append(v_samp_0 - v_samp_1)         
   
        all_sums.append(corr_add)
        all_subs.append(corr_sub)

    return all_sums, all_subs

def set_initial(dev, lab, fbtrim=None, sstoutfb=104, dt_trims=None, write=True):

    dev.dev.labc.dll(lab, mode=True, sstoutfb=sstoutfb)
    time.sleep(2)

    if fbtrim != None:
        dev.dev.labc.l4reg(lab, 11, int(fbtrim))   

    trims=np.ones(128, dtype=int)
    
    if dt_trims == None:
        '''if non initial values specified, go with some initial even/odd guesses'''
        for i in range(0, 128):
            if i%2==0:
                trims[i] = 1800 #2310 
            else:
                trims[i] = 1350
        trims[127]= 900 #last sample always seems to be a little slow
        trims[0]  = 0   #don't touch trim dac0, set fast as possible
    else:
        if isinstance(dt_trims, list):
            if len(dt_trims) != 128:
                print 'trim list needs to include 128 elements, dt trims DACs not updated'
                return 

            for i in range(len(dt_trims)):
                trims[i] = dt_trims[i]
        else:
            '''option for handling a scalar to set all trims identically'''
            trims = trims + int(dt_trims) - 1
        
    if write:
        set_trims(dev, lab, trims)

    return trims

def set_trims(dev, lab, trims):
    for i in range(0, 128):
        time.sleep(0.02)
        dev.dev.labc.l4reg(lab, i+256, int(trims[i]) & 0xFFF)
    time.sleep(2.0)

def single_run(dev, lab, num_events=1000, save=False, filename='temp.dat'):
    data=np.array(dev.log(15, num_events, save=save, filename=filename, unwrap=True))
    c = zero_crossings(data, lab)

    return c

def tune_dTs(dev, lab, dTcrossings, trims):

    dev.dev.labc.run_mode(0)
    new_trims=np.zeros(128, dtype=np.int)

    new_trims[0] = trims[0]
    for i in range(1,128):
        if dTcrossings[i] < (nominal_dt - 40.0):
            new_trims[i] = trims[i] + 50
            print i, 'is really fast    ', dTcrossings[i], new_trims[i], trims[i]
        elif dTcrossings[i] < (nominal_dt - 20.0):
            new_trims[i] = trims[i] + 25
            print i, 'is moderately fast', dTcrossings[i], new_trims[i], trims[i]
        elif dTcrossings[i] < (nominal_dt - 5.0):
            new_trims[i] = trims[i] + 15
            print i, 'is somewhat fast  ', dTcrossings[i], new_trims[i], trims[i]
        elif dTcrossings[i] < (nominal_dt - 3.5):
            new_trims[i] = trims[i] + 11
        elif dTcrossings[i] < (nominal_dt - 2.0):
            new_trims[i] = trims[i] + 7
        elif dTcrossings[i] < (nominal_dt - 1.0):
            new_trims[i] = trims[i] + 4
        elif dTcrossings[i] < (nominal_dt - 0.5):
            new_trims[i] = trims[i] + 2
        
        elif dTcrossings[i] > (nominal_dt + 70.0):
            new_trims[i] = trims[i] - 80 
            print i, 'is really really slow    ', dTcrossings[i], new_trims[i], trims[i]
        elif dTcrossings[i] > (nominal_dt + 40.0):
            new_trims[i] = trims[i] - 50
            print i, 'is really slow    ', dTcrossings[i], new_trims[i], trims[i]
        elif dTcrossings[i] > (nominal_dt + 20.0):
            new_trims[i] = trims[i] - 25      
            print i, 'is moderately slow', dTcrossings[i], new_trims[i], trims[i]
        elif dTcrossings[i]> (nominal_dt + 5.0):
            new_trims[i] = trims[i] - 15  
            print i, 'is  somewhat slow ', dTcrossings[i], new_trims[i], trims[i]
        elif dTcrossings[i]> (nominal_dt + 3.5):
            new_trims[i] = trims[i] - 11        
        elif dTcrossings[i] > (nominal_dt + 2.0):
            new_trims[i] = trims[i] - 7        
        elif dTcrossings[i] > (nominal_dt + 1.0):
            new_trims[i] = trims[i] - 4
        elif dTcrossings[i] > (nominal_dt + 0.5):
            new_trims[i] = trims[i] - 2
        else:
            new_trims[i] = trims[i]
            print i, 'is within 0.5 ps', dTcrossings[i], new_trims[i], trims[i]

        #latch min/max if overrange
        if new_trims[i] > max_trim:
            print i, 'is maxed out', dTcrossings[i]
            new_trims[i] = max_trim-20
        elif new_trims[i] < 0:
            new_trims[i] = 20 

    set_trims(dev, lab, new_trims)

    return new_trims

def scan_feedback(dev, lab, current_dac_value, sine_freq, sine_amp=100., scan_range=None):
            
    freq_fit_init = 2*np.pi*sine_freq
    
    fbscan={}
    fbscan[lab]={}
    fbscan[lab]['freq']   = []
    fbscan[lab]['trim'] = []
    fbscan[lab]['current_trim'] = current_dac_value

    #probably specify a large scan_range on the intial pass, since intial guesses change DLL by a lot
    #for subsequent tunes, just scan in region around current dac value
    #----
    if scan_range == None:
        fbscan[lab]['trim'] = range(current_dac_value-50, current_dac_value+51, 5)
    else:
        fbscan[lab]['trim'] = scan_range

    max_iterations = len(fbscan[lab]['trim'])
    current_iter = 0
    
    while current_iter < max_iterations:
        
        dev.dev.labc.run_mode(0)
        dev.dev.labc.l4reg(lab, 11, int(fbscan[lab]['trim'][current_iter]))   
        time.sleep(2.0)  
        
        data=dev.log(15, numevent=4, save=False)

        fit_freq = []
        for i in range(2):
            for j in range(0, 1024, 128):
                fit_params = fit.fit_sin(data[i][lab][j:j+128], sine_amp, freq_fit_init, np.pi/2, 
                                         dt=nominal_dt*1.e-3, use_timebase=True)
                '''try a different initial phase if poorly fitted'''
                ph=0
                while((abs(fit_params[0]) < (sine_amp/2.)) and (ph < 5)):
                    fit_params = fit.fit_sin(data[i][lab][j:j+128], sine_amp, freq_fit_init, (np.pi/(ph+1)), 
                                             dt=nominal_dt*1.e-3, use_timebase=True)
                    ph = ph + 1
                        
                if abs(fit_params[0]) < (sine_amp/2.):
                    print 'probably a fit error', lab, i , j, fit_params
                else:
                    fit_freq.append(fit_params[1]/(2. * np.pi))

        if len(fit_freq) < 2:
            print 'something went wrong here..'
        
        else:
            fbscan[lab]['freq'].append(np.mean(np.array(fit_freq)))
            print 'difference: input freq - fitted freq = (kHz)', (sine_freq - np.mean(np.array(fit_freq)))*1.e-3, \
                'trim', int(fbscan[lab]['trim'][current_iter])
            current_iter = current_iter + 1

    return fbscan

def tune_feedback(dev, lab, fbscan, freq, forder=4, plot=False):
    
    #check to see if actual frequency is contained in the scan
    if (fbscan[lab]['freq'][0] < freq) and (fbscan[lab]['freq'][len(fbscan[lab]['freq'])-1] < freq):
        print 'missed nominal freq in scan: it is ABOVE the scan range'
    elif (fbscan[lab]['freq'][0] > freq) and (fbscan[lab]['freq'][len(fbscan[lab]['freq'])-1] > freq):
        print 'missed nominal freq in scan: it is BELOW the scan range'

    p = np.poly1d(np.polyfit(fbscan[lab]['freq'], np.array(fbscan[lab]['trim']), deg=forder))
    p_deriv = np.polyder(p, m=1)
    print 'lab:', lab, ', VtrimFB dac for 3.2 GSPS from fit:', p(freq), ' derivative, counts/kHz', p_deriv(freq)*1e3

    #fbscan[lab]['polyfit']=p
    fbscan[lab]['updated_trim']=int(p(freq))

    dev.dev.labc.run_mode(0)
    if (fbscan[lab]['updated_trim'] < 10) or (fbscan[lab]['updated_trim'] > 3000):
        print 'fitted VtrimFB value OUT OF RANGE, setting previous value..'
        dev.dev.labc.l4reg(lab, 11, int(fbscan[lab]['current_trim']))   
        fbscan[lab]['updated_trim'] = fbscan[lab]['current_trim']
    else:
        print 'setting VtrimFB to..', fbscan[lab]['updated_trim']
        dev.dev.labc.l4reg(lab, 11, int(fbscan[lab]['updated_trim']))


    if plot:
        import matplotlib.pyplot as plt
        plt.plot(fbscan[lab]['freq'], np.array(fbscan[lab]['trim']),'o')
        plt.plot(fbscan[lab]['freq'], p(np.array(fbscan[lab]['freq'])), '--')
        plt.show()

    time.sleep(2) #let DLL settle

def rms(x):
    return np.sqrt(np.sum(x**2) / float(len(x)))

if __name__=='__main__':
    
    import surf_data
    import json
    dev=surf_data.SurfData()

    #Tin = 4.3000e-9
    #Tin = 7.3000e-9
    #Tin  = 11.30000e-9
    #freq=1./Tin
    freq=230.000e6

    print 'using sine wave frequency', freq*1e-6, 'MHz'

    num_iter  = 13
    num_events= 1500
    rms_target= 3.0 #ps

    lab=0
    current_fb_value = 1295

    trims=[]
    dTcrossings=[]
    fbscan_dict=[]

    init_trims = set_initial(dev, lab)
    trims.append(init_trims)

    '''run scan'''
    _rms=100.
    i=0

    basefilename = '230MHz_tune_run_0718_CH0'
    while (i < (num_iter+1)) and _rms > rms_target:

        if i>0:
            trims.append(tune_dTs(dev, lab, dTcrossings[i-1], trims[i-1]))
        
        if i > 1:
            print 'tuning feedback trim...'
            fbscan = scan_feedback(dev, lab, current_fb_value, sine_freq=freq, sine_amp=200., scan_range=range(1210, 1461, 10))
            tune_feedback(dev, lab, fbscan, freq)
            current_fb_value = fbscan[lab]['updated_trim']
            fbscan_dict.append(fbscan)
        
        savedatfile = basefilename + '_data_iter%d.dat' % i

        crossings = single_run(dev, lab, num_events=num_events, save=True, filename=savedatfile)
        mean_crossings = np.mean(crossings[0], dtype=np.float64) 
        avg_sample_dt = mean_crossings * 1.e12 / freq 
        dTcrossings.append( crossings[0] * 1.e12 / freq)
        _rms=rms(dTcrossings[i])

        print '---------------------------------'
        print 'on iteration..', i, '-- dT RMS [ps]:' , _rms, \
            '-- avg dT [ps]', avg_sample_dt, '-- DLL wrap dT [ps]', dTcrossings[i][0]
        print '---------------------------------'
        i = i+1

    np.savetxt('crossings_'+basefilename+'.dat', np.array(dTcrossings))
    np.savetxt('trims_' + basefilename+'.dat', np.array(trims))

    with open('fbdict_'+basefilename+'.dat', 'w') as outfile:
        json.dump(fbscan_dict, outfile)
