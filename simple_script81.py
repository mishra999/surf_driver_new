import surf_daq
import time
import sys, os
import read_tesrpattern
from anita_python import ocpci
sys.path.insert(0, '/home/surfuser/surfv5_anita_python/anita_python')
ocpci.set_backend(ocpci.ocpci_vfio)
tp = read_tesrpattern.read_testpattern(lab=3)



