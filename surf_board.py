# fix the backend first
from anita_python import ocpci
ocpci.set_backend(ocpci.ocpci_vfio)

import surf
import sys

sys.path.insert(0, '/home/anita/astroparticlelab/')

def do():
    dev=surf.SURF()
    print 'identify:'
    dev.identify()
    print 'path:', dev.path
    dev.labc.run_mode(0)
    # set the event size (FIFO empty = (event_size/2)-1)
    dev.labc.set_fifo_empty(511)
    dev.labc.reset_fifo()
    dev.labc.reset_ramp()    
    dev.i2c.default_config()
    dev.clock(dev.internalClock)
    dev.labc.default()
    dev.labc.dll(15, mode=True)
    dev.set_phase(2)
    dev.labc.automatch_phab(15)
    dev.status()
    dev.dma_init(0, 1024*1024)
    return dev
