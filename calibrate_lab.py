import sys
sys.path.append("/home/anita/astroparticlelab")
import afg3252
import surf_daq
import numpy as np
import matplotlib.pyplot as plt

cal=[dict() for x in range(12)]

#
# These were determined from a run of tuneLoop which just
# found the starting points (pass 'None' as 'trims'). They're
# specific to the SURFv5 prototype.
#

cal[0]['start_point'] = 2225
cal[0]['start_fb'] = 1195
cal[1]['start_point'] = 2300
cal[1]['start_fb'] = 1200
cal[2]['start_point'] = 2225
cal[2]['start_fb'] = 1215
cal[3]['start_point'] = 2200
cal[3]['start_fb'] = 1200
cal[4]['start_point'] = 2225
cal[4]['start_fb'] = 1135
cal[5]['start_point'] = 2225
cal[5]['start_fb'] = 1160
cal[6]['start_point'] = 2175
cal[6]['start_fb'] = 1225
cal[7]['start_point'] = 2200
cal[7]['start_fb'] = 1205
cal[8]['start_point'] = 2225
cal[8]['start_fb'] = 1190
cal[9]['start_point'] = 2250
cal[9]['start_fb'] = 1190
cal[10]['start_point'] = 2250
cal[10]['start_fb'] = 1180
cal[11]['start_point'] = 2225
cal[11]['start_fb'] = 1200

if len(sys.argv) < 2:
    print "Need a lab number to calibrate."
    quit()
    
lab = int(sys.argv[1])

filename = "proto_cal" + str(lab) + ".npz"

afg = afg3252.AFG3252()
afg.set_output(0)
daq = surf_daq.LabDaq(lab)
#daq.stopAcq()
#daq.dev.labc.l4reg(10, 388, 56)
#daq.dev.labc.l4reg(10, 389, 87)
#daq.startAcq()
#daq.pedestalRun()


afg.recall()
afg.set_output(1)
trims = np.full(128, cal[lab]['start_point'])
trims[0]=0
trims[127]=500
fb = cal[lab]['start_fb']
print "starting at %d with trimfb %d" % (trims[1], fb)
trimHistory = np.empty((12,128))
newtrims, newfb = surf_daq.tuneLoop(daq,10,trims=trims, fb=fb, trimHistory=trimHistory, afg=afg)
surf_daq.update_trims_one(daq, lab, newtrims.astype('int'), newfb)
newtrim, newfb = surf_daq.tuneOutliers(daq, 10, newtrims, newfb, 40000)
times = daq.getTimes()
print "std: %f seam %f" % (np.std(times[0:127]), times[127])
for i in xrange(len(newtrim)):
    print "trim[%d]=%d" % (i, newtrim[i])
print "vtrimfb = %d" % newfb

np.savez_compressed(filename, trim=newtrim, vtrimfb=newfb)
