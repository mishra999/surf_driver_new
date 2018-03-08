import surf
import surf_data
import numpy as np
import fit
import time
import sys

nominal_sampling_dt = 312.5 #ps

def initialize(lab_to_scan=[0,11], sstoutfb=104):
    dev=surf.SURF()
    dev.labc.run_mode(0)
    
    lab=range(lab_to_scan[0], lab_to_scan[1]+1)
    for l in lab:
        #dev.labc.dll(l, mode=False)
        #dev.labc.dll(l)
        dev.labc.l4reg(l, 386, int(sstoutfb))
        dev.labc.dll(l, mode=True)
        

def scan_trim_fb(lab_to_scan=[0,11], sine_freq=100., sine_amp=100., dac=[1100,1800]):
    surf=surf_data.SurfData()

    lab= range(lab_to_scan[0], lab_to_scan[1]+1)
    trimscan={}
    for l in lab:
        trimscan[l]={}
        trimscan[l]['trim']=[]
        trimscan[l]['fit_dt']=[]
        trimscan[l]['fit_sigm']=[]
    
    for trim in range(dac[0], dac[1], 20):
        
        surf.dev.labc.run_mode(0)
        for l in lab:
            surf.dev.labc.l4reg(l, 11, int(trim))

        sys.stdout.write('setting trim fb dac to...{:}\r'.format(trim))
        sys.stdout.flush()    
        time.sleep(2.2)
        data=surf.log(15, numevent=4, save=False)

        freq_init_value = 1.e5*2*np.pi*sine_freq / (nominal_sampling_dt*1e12)
        
        for l in lab:
            fit_freq = []
            for i in range(2):
                for j in range(0, 1024, 128):
                    fit_params = fit.fit_sin(data[i][l][j:j+128], sine_amp, freq_init_value, np.pi/2, plot=False)
                    '''try a different initial phase if poorly fitted'''
                    ph=0
                    while((abs(fit_params[0]) < (sine_amp/2.)) and (ph < 4)):
                        #sys.stdout.write('\n')
                        #sys.stdout.write('trying fit again, with different phase...{:} rad\r'.format(np.pi/(ph+1)))
                        #sys.stdout.flush()    
                        fit_params = fit.fit_sin(data[i][l][j:j+128], sine_amp, freq_init_value, (np.pi/(ph+1)), plot=False)
                        ph = ph + 1
                        
                    if abs(fit_params[0]) < (sine_amp/2.):
                        print 'probably a fit error', l, i , j, fit_params
                    else:
                        fit_freq.append(fit_params[1]/(2.*np.pi*sine_freq))

            if len(fit_freq) < 2:
                continue
            
            trimscan[l]['trim'].append(trim)
            trimscan[l]['fit_dt'].append(np.mean(np.array(fit_freq))*1e12)
            trimscan[l]['fit_sigm'].append(np.std(np.array(fit_freq))*1e12)

    sys.stdout.write('\n')
    return trimscan

def fit_scan(trimscan, order=4):
    
    for l in trimscan:
        p = np.poly1d(np.polyfit(trimscan[l]['fit_dt'], np.array(trimscan[l]['trim']), deg=order))
        p_deriv = np.polyder(p, m=1)
        print 'lab:', l, ', trim dac for 3.2 GSPS from fit:', p(nominal_sampling_dt), ' derivative, counts/ps', p_deriv(nominal_sampling_dt)
        trimscan[l]['polyfit']=p

if __name__=='__main__':

    import matplotlib
    import matplotlib.pyplot as plt
    matplotlib.rc('xtick', labelsize=15)
    matplotlib.rc('ytick', labelsize=15)

    sine_amp = 480.0
    sine_freq= 230.00e6
    lab_to_scan=[0,0]
    initialize(lab_to_scan=lab_to_scan)
    trims = scan_trim_fb(lab_to_scan=lab_to_scan, sine_freq=sine_freq, sine_amp=sine_amp) 
    fit_scan(trims)
    
    for i in trims:
        plt.plot(trims[i]['fit_dt'], trims[i]['trim'], 'o', label=str(i))
        plt.plot(trims[i]['fit_dt'], trims[i]['polyfit'](np.array(trims[i]['fit_dt'])), '--')

    plt.legend(numpoints=1, loc='upper left')
    plt.xlabel('Sampling dt, cell 127->128')
    plt.ylabel('Vtrim fb DAC value')
    
    #plt.figure(2)
    #plt.plot(trims[0]['fit_dt'], trims[0]['trim'], 'o')
    #plt.plot(trims[0]['fit_dt'], trims[0]['polyfit'](np.array(trims[0]['fit_dt'])), '--')    
    plt.show()
