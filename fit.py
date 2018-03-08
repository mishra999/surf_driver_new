import numpy as np
from scipy.optimize import curve_fit
import matplotlib.pyplot as plt

def my_sin( x, a,b,c):
    return a*np.sin(x*b+c)

def fit_sin( data, amp, freq, phase, plot=True):
    x=np.arange(len(data))
    y=my_sin(x, amp, freq, phase)
    popt, pfit = curve_fit(my_sin, x, data, p0=[amp, freq, phase])
                           #sigma=(np.zeros(len(x))+0.1))

    #smooth_x=np.linspace(0,len(data), len(data)*10)

    if plot:
        print popt
        plt.plot(x, data, 'o')
        plt.plot(my_sin(x, *popt))
        plt.show()

    return popt
                 
