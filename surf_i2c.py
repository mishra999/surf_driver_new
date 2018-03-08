from anita_python import i2c
from anita_python.bf import *
import numpy as np
import time

'''
06-2016
Written to clean up the main surf.py module;
moved all i2c bus overhead to this module: surf_i2c.py
Includes functions to manage SURF dac, ioexpander, and RFP ADCs
'''

class SURFi2c:
    '''
    base map of the i2c cores in the fpga:
    '''
    i2c_map = {'DAC'        : 0x00,
               'RFP_0'      : 0x20,
               'RFP_1'      : 0x40,
               'RFP_2'      : 0x60,
               'RFP_3'      : 0x80}
 
    #data rate of rfp ADC in samples-per-second
    adc_rate ={'8'          : 0x0,
               '16'         : 0x1,
               '32'         : 0x2,
               '64'         : 0x3,
               '128'        : 0x4,
               '250'        : 0x5,
               '475'        : 0x6,
               '860'        : 0x7}
    #input mux select 
    adc_mux = {'p2n3'       : 3,
               'p1n3'       : 2,
               'p0n3'       : 1,
               'p0n1'       : 0}
    #full scale range (volts)           
    adc_fsr = {'6.14'       : 0,
               '4.09'       : 1,
               '2.04'       : 2,
               '1.02'       : 3,
               '0.51'       : 4,
               '0.25'       : 5}
               
    def __init__(self, dev, base):
        self.dac = i2c.I2C(dev, base + self.i2c_map['DAC'], 0x60)
	self.ioexpander = i2c.I2C(dev, base + self.i2c_map['DAC'], 0x20)
        '''
        12 RFP circuits on 4 i2c buses. Slave address set by ADDR pin connection:
        GND: 1001000
        VDD: 1001001
        SDA: 1001010 (not used)
        SCL: 1001011 
        '''
        self.rfp = []
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_0'], 0x49) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_0'], 0x48) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_0'], 0x4B) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_1'], 0x49) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_1'], 0x48) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_1'], 0x4B) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_2'], 0x49) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_2'], 0x48) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_2'], 0x4B) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_3'], 0x49) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_3'], 0x48) )
        self.rfp.append(i2c.I2C(dev, base + self.i2c_map['RFP_3'], 0x4B) ) 

    def wait(self, seconds=0.5):
        time.sleep(seconds)
        
    def set_vped(self, value, eeprom=False):
        val=bf(value)
        if eeprom:
            dac_bytes=[0x5E, (0x8<<4) | (val[11:8]), val[7:0]]
        else:
            dac_bytes=[0x46, (0x8<<4) | (val[11:8]), val[7:0]]
        self.dac.write_seq(dac_bytes)
        if eeprom:
            self.wait()
        self.wait(0.1)

    def set_rfp_vped(self, value=[0x9C4, 0x578, 0x578], eeprom=False):
        val0=bf(value[0])
        val1=bf(value[1])
        val2=bf(value[2])
        dac_bytes=[]
        if eeprom:
            dac_bytes.append([0x58, (0x8<<4) | (val0[11:8]), val0[7:0]])
            dac_bytes.append([0x5A, (0x8<<4) | (val1[11:8]), val1[7:0]])
            dac_bytes.append([0x5C, (0x8<<4) | (val2[11:8]), val2[7:0]])
        else:
            dac_bytes.append([0x40, (0x8<<4) | (val0[11:8]), val0[7:0]])
            dac_bytes.append([0x42, (0x8<<4) | (val1[11:8]), val1[7:0]])
            dac_bytes.append([0x44, (0x8<<4) | (val2[11:8]), val2[7:0]])   
        for i in range(0, len(dac_bytes)):
            self.dac.write_seq(dac_bytes[i])
            if eeprom:
                self.wait() #time delay required to write to eeprom! (can be better handled, surely)
            self.wait(0.1)
            
    def read_dac(self):
        self.dac.start(read_mode=True)
        dac_bytes=self.dac.read_seq(24)
        print "Reading from MCP4728..."
        print "DAC channel A (RFP_VPED_0):  register is set to 0x{0:x}, EEPROM is set to 0x{0:x}".format(
            (dac_bytes[1] & 0xF) << 8 | dac_bytes[2], (dac_bytes[4] & 0xF) << 8 | dac_bytes[5] ) 
        print "DAC channel B (RFP_VPED_1):  register is set to 0x{0:x}, EEPROM is set to 0x{0:x}".format(
            (dac_bytes[7] & 0xF) << 8 | dac_bytes[8], (dac_bytes[10] & 0xF) << 8 | dac_bytes[11] ) 
        print "DAC channel C (RFP_VPED_2):  register is set to 0x{0:x}, EEPROM is set to 0x{0:x}".format(
            (dac_bytes[13] & 0xF) << 8 | dac_bytes[14], (dac_bytes[16] & 0xF) << 8 | dac_bytes[17] )
        print "DAC channel D (VPED)      :  register is set to 0x{0:x}, EEPROM is set to 0x{0:x}".format(
            (dac_bytes[19] & 0xF) << 8 | dac_bytes[20], (dac_bytes[22] & 0xF) << 8 | dac_bytes[23] ) 

    def read_rfp(self, pointer_reg, lab):
        self.rfp[lab].write_seq([pointer_reg])
        rfp_register = self.rfp[lab].read_seq(2)
        return bf((rfp_register[0] << 8) | rfp_register[1])

    def rfp_conversion(self, lab):
        if not self.read_rfp(0x1, lab)[15]:
            return True
        else:
            return False
   
    def config_rfp(self, continuous_mode=True, data_rate=2, input_mux=3, pga_gain=2,
                   thresh_lo=0x8000, thresh_hi=0x7FFF):
        rfp_config_register=0x1
        rfp_lothresh_register=0x2
        rfp_hithresh_register=0x3

        config_hi = (input_mux & 0x7) << 4 | (pga_gain & 0x7) << 1 | (not continuous_mode) | 0x00
        config_lo = (data_rate & 0x7) << 5 | 0x00
        #set threshold register values to enable continuous mode:
        #hi-thresh MSB = '1', lo-thresh MSB = '0'
        if continuous_mode:
            thresh_lo = thresh_lo & (0<<16) 
            thresh_hi = thresh_hi | 0x8000

        #configure all rfp channels similarly:
        for i in range(0, 12):
            self.rfp[i].write_seq([rfp_config_register, config_hi, config_lo])
            self.wait(0.01)
            #verify write (NOTE: top bit different for read/write in config reguster, so not compared!)
            ########  ( the top bit 15: indicates a `conversion in process' if [0] or not if [1] )
            if self.read_rfp(rfp_config_register, i)[14:0] != bf((config_hi << 8) | config_lo)[14:0]:
                print 'rfp %i error: write/read mismatch to config register' % i

            self.rfp[i].write_seq([rfp_lothresh_register, bf(thresh_lo)[15:8], bf(thresh_lo)[7:0]])
            self.wait(0.01)
            if self.read_rfp(rfp_lothresh_register, i)[15:0] != bf(thresh_lo)[15:0]:
                print 'rfp %i error: write/read mismatch to low-thresh register' % i

            self.rfp[i].write_seq([rfp_hithresh_register, bf(thresh_hi)[15:8], bf(thresh_hi)[7:0]])
            self.wait(0.01)
            if self.read_rfp(rfp_hithresh_register, i)[15:0] != bf(thresh_hi)[15:0]:
                print 'rfp %i error: write/read mismatch to hi-thresh register' % i

    def config_ioexpander(self, latch_inputs=True):
        config=[]
        if latch_inputs:
            config.append([0x44, 0xFF]) #input latch register 0
            config.append([0x45, 0xFF]) #input latch register 1
        else:
            config.append([0x44, 0x00]) #input latch register 0
            config.append([0x45, 0x00]) #input latch register 1
            
        config.append([0x46, 0xFF])     #PU/PD enable register 0
        config.append([0x47, 0xFF])     #PU/PD enable register 1
        config.append([0x48, 0xFF])     #PU/PD selection register 0
        config.append([0x49, 0xFF])     #PU/PD selection register 1
        config.append([0x4A, 0x00])     #interrupt mask 0
        config.append([0x4B, 0x00])     #interrupt mask 1

        for i in range(0, len(config)):
            self.ioexpander.write_seq(config[i])
            self.wait(0.05)
            
    def default_config(self):
        self.config_ioexpander()
        self.config_rfp()

    def run_rfp(self, lab, run_time=5.0, plot=False):
        
        my_rfp = []
        my_rfp.append(RFPdata(lab))
            
        self.ioexpander.read_seq(2)  #do an initial read to clear any interrupts
        start = time.time()
        
        while( (time.time()-start) < run_time):
            self.ioexpander.write_seq([0x4D])        #address the interupt status register, port 1
            interrupt = self.ioexpander.read_seq(2)  #read 2 bytes (upper and lower ports)
            interrupt_time = time.time() - start
            interrupt_status_register = bf(((interrupt[0] & 0x0F) << 8) | (interrupt[1] & 0xFF))

            if interrupt_status_register[11-lab] == 1:
                my_rfp[0].data.append(self.read_rfp(0x0, lab)[15:0])
                my_rfp[0].time.append(interrupt_time)
                self.ioexpander.write_seq([0x01])    
                self.ioexpander.read_seq(2)          #reading input register clears the interrupt

        self.ioexpander.read_seq(2)

        #convert from 2's complement:
        for j in range(0, len(my_rfp[0].data)):
            if my_rfp[0].data[j] > 0x7FFF:
                my_rfp[0].data[j] = my_rfp[0].data[j] - (1 << 16)
                    
        if plot:
            import matplotlib.pyplot as plt
            plt.ion()
            plt.plot(my_rfp[0].time, my_rfp[0].data, 'o-')
        
        return my_rfp
         
class RFPdata:
    def __init__(self, channel):
        self.channel = channel
        self.data = []
        self.time = []

        
            
