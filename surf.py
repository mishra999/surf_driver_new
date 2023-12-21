# import the base controls
from anita_python import ocpci, spi, picoblaze
# import the bitfield class without a name, it's too useful
from anita_python.bf import *

import struct
import sys
import time
import numpy as np
import surf_calibrations
import surf_i2c

class LAB4_Controller:
	map = { 'CONTROL'			: 0x00000,
			'SHIFTPRESCALE'		        : 0x00004,
	'RDOUTPRESCALE'		        : 0x00008,
	'WILKDELAY'			: 0x0000C,
	'WILKMAX'			: 0x00010,
	'TPCTRL'			: 0x00014,
	'L4REG'				: 0x00018,
			'PHASECMD'                      : 0x00020,
			'PHASEARG'                      : 0x00024,
			'PHASERES'                      : 0x00028,
			'PHASEZERO'                     : 0x0002C,
			'PHASEPB'                       : 0x0003C,
	'TRIGGER'			: 0x00054,
			'READOUT'                       : 0x00058,
			'READOUTEMPTY'                  : 0x0005C,
			'pb'				: 0x0007C,
			}
	amon = { 'Vbs'                      : 0,
				'Vbias'                    : 1,
				'Vbias2'                   : 2,
				'CMPbias'                  : 3,
				'VadjP'                    : 4,
				'Qbias'                    : 5,
				'ISEL'                     : 6,
				'VtrimT'                   : 7,
				'VadjN'                    : 8,
				}
	tmon = {'A1'                        : 0,
			'B1'                        : 1,
			'A2'                        : 2,
			'B2'                        : 3,
			'SSPout'                    : 68,
			'SSTout'                    : 100,
			'PHASE'                     : 4,
			'PHAB'                      : 5,
			'SSPin'                     : 6,
			'WR_STRB'                   : 7,
			}
                
	def __init__(self, dev, base):                             
		self.dev = dev
		self.base = base
		self.pb = picoblaze.PicoBlaze(self, self.map['pb'])
		self.phasepb = picoblaze.PicoBlaze(self,self.map['PHASEPB'])

	def automatch_phab(self, lab, match=1):
		labs = []
		if lab == 15:
			labs = range(12) #it was 12 earlier
		else:
			labs = [lab]
		# Find our start point.
		sync_edge = self.scan_edge(12, 1) # earlier scan_edge(12, 1)
		print ("Found sync edge: %d" % sync_edge)
		for i in labs:
			# Find our PHAB sampling point.
			self.set_tmon(i, self.tmon['WR_STRB'])
			wr_edge = self.scan_edge(i, 1, sync_edge)
			print ("Found WR_STRB edge on LAB%d: %d" % (i, wr_edge))
			self.set_tmon(i, self.tmon['PHAB'])
			phab = self.scan_value(i, wr_edge) & 0x01
			while phab != match:
				print ("LAB%d wrong PHAB phase, resetting." % i)
				self.clr_phase(i)
				phab = self.scan_value(i, wr_edge) & 0x01

	def autotune_vadjp(self, lab, initial=2700):
			self.set_tmon(lab, self.tmon['SSPin'])
			rising=self.scan_edge(lab, 1, 0)
			falling=self.scan_edge(lab, 0, rising+100)
			width=falling-rising
			if width < 0:
					print ("Width less than 0, do something.")
					return
			vadjp=initial
			delta=20
			self.l4reg(lab, 8, vadjp)
			self.set_tmon(lab, self.tmon['SSPout'])
			rising=self.scan_edge(lab, 1, 0)
			falling=self.scan_edge(lab, 0, rising+100)
			trial=falling-rising
			if trial < 0:
					print ("Trial width less than 0, do something.")
					return
			oldtrial=trial
			while abs(trial-width) > 2:
					if trial < width:
							if oldtrial > width:
									delta=delta/2
									if delta < 1:
											delta = 1
							vadjp += delta
					else:
							if oldtrial < width:
									delta=delta/2
									if delta < 1:
											delta = 1
							vadjp -= delta
					oldtrial = trial
					self.l4reg(lab, 8, vadjp)
					rising=self.scan_edge(lab, 1, 0)
					falling=self.scan_edge(lab, 0, rising+100)
					trial=falling-rising
					print ("Trial: vadjp %d width %f target %f" % ( vadjp, trial, width))
			return vadjp
                
	def autotune_vadjn(self, lab):
		self.set_tmon(lab, self.tmon['A1'])
		vadjn = 1640
		delta = 20            
		self.l4reg(lab, 3, vadjn)            
		width = self.scan_width(lab, 64)
		oldwidth = width
		print ("Trial: vadjn %d width %f" % ( vadjn, width))
		while abs(width-840) > 0.5:
			if (width < 840):
				if (oldwidth > 840):
					delta = delta/2
					if delta < 1:
						delta = 1
				vadjn -= delta
			else:
				if (oldwidth < 840):
					delta = delta/2
					if delta < 1:
						delta = 1
				vadjn += delta
			oldwidth = width
			self.l4reg(lab, 3, vadjn)
			width = self.scan_width(lab, 64)
			print ("Trial: vadjn %d width %f" % ( vadjn, width))
		return vadjn            
                
	def scan_free(self):
		self.write(self.map['PHASECMD'], 0x01)
		
	def scan_width(self, lab, trials=1):
		self.write(self.map['PHASEARG'], lab)
		res = 0
		for i in range(trials):
			self.write(self.map['PHASECMD'], 0x02)
			val = self.read(self.map['PHASECMD'])
			while val != 0x00:
				val = self.read(self.map['PHASECMD'])
			res += self.read(self.map['PHASERES'])                
		return res/(trials*1.0)

	def scan_value(self,lab,position):
		if position > 4479:
			print ("Position must be 0-4479.")
			return None
		val = bf(0)                
		val[15:0] = position
		val[19:16] = lab
		self.write(self.map['PHASEARG'], int(val))
		self.write(self.map['PHASECMD'], 0x03)
		res = self.read(self.map['PHASECMD'])
		while res != 0x00:
			res = self.read(self.map['PHASECMD'])
		return self.read(self.map['PHASERES'])
        
	def scan_edge(self,lab, pos=0, start=0):
		val = bf(0)
		val[15:0] = start
		val[24] = pos
		val[19:16] = lab
		self.write(self.map['PHASEARG'], int(val))
		self.write(self.map['PHASECMD'], int(0x04))
		ret=self.read(self.map['PHASECMD'])
		# print("scan_edge, ret = ",ret)
		while ret != 0x00:
			ret = self.read(self.map['PHASECMD'])
		return self.read(self.map['PHASERES'])
	
	def set_amon(self, lab, value):
		self.l4reg(lab, 12, value)

	def set_tmon(self, lab, value):
		self.l4reg(lab, 396, value)
		
	def clr_phase(self, lab):
		self.l4reg(lab, 396, self.tmon['PHAB']+128)
		self.l4reg(lab, 396, self.tmon['PHAB'])

	def start(self):
		ctrl = bf(self.read(self.map['CONTROL']))
		while not ctrl[2]:
			ctrl[1] = 1
			self.write(self.map['CONTROL'], int(ctrl))
			ctrl = bf(self.read(self.map['CONTROL']))

	def stop(self):
		ctrl = bf(self.read(self.map['CONTROL']))
		while ctrl[2]:
			ctrl[1] = 0
			self.write(self.map['CONTROL'], int(ctrl))
			ctrl = bf(self.read(self.map['CONTROL']))

	def repeat_count(self, cnt=0):
		ctrl = bf(self.read(self.map['TRIGGER']))
		ctrl[25:24] = cnt
		ctrl[31] = 1
		self.write(self.map['TRIGGER'], int(ctrl))



	'''
	send software trigger
	'''
	# def force_trigger(self):
	# 	ctrl = bf(self.read(self.map['TRIGGER']))
	# 	# print('force trigger cntl ctrl[1], ctrl[18:16]',ctrl[1], ctrl[18:16])
	# 	# ctrl[0] = 1 #force trigger clear
	# 	ctrl[1] = 1 #force trigger bit
	# 	ctrl[18:16] = 5 #post_trigger value
	# 	ctrl[23] = 1
	# 	self.write(self.map['TRIGGER'], int(ctrl))
	# 	ctrl = bf(self.read(self.map['TRIGGER']))
	# 	print('force trigger cntl written ctrl[1], ctrl[18:16]',ctrl[1], ctrl[18:16])
	def force_trigger(self):
		self.write(self.map['TRIGGER'], 2)

	'''
	clear all registers on LAB
	'''
	def reg_clr(self):
		ctrl = bf(self.read(self.map['CONTROL']))
		if ctrl[1]:
			print ('cannot issue REG_CLR: LAB4 in run mode')
			return 1
		else:
			self.write(0, 0xFFF0000)
			self.write(0, 0)
			return 0
	'''
	reset FIFO on FPGA, which holds LAB4 data
	'''
	def reset_fifo(self, force=False, reset_readout=True):
		ctrl = bf(self.read(self.map['CONTROL']))
		if ctrl[1] and not force:
			print ('cannot reset FIFO: LAB4 in run mode')
			return 1
		else:
			if reset_readout:
					self.run_mode(0)
			rdout = bf(self.read(self.map['READOUT']))
			rdout[1] = 1
			rdout[2] = reset_readout
			self.write(self.map['READOUT'], int(rdout)) 
			return 0
	'''
	reset Wilkinson ramp controller
	'''
	def reset_ramp(self):
			ctrl = bf(self.read(self.map['CONTROL']))
			ctrl[8] = 1
			self.write(self.map['CONTROL'], int(ctrl))
        
	'''
	enables LAB run mode (sample+digitize+readout)
	'''    
	def run_mode(self, enable=True):
		# print("run_mode: read cntl",self.read(self.map['CONTROL']))
		ctrl = bf(self.read(self.map['CONTROL']))
		# print("run_mode, ctrl from bf=",int(ctrl))
		if enable:
			ctrl[1] = 1
			self.write(self.map['CONTROL'], int(ctrl))
		else:
			ctrl[1] = 0
			self.write(self.map['CONTROL'], int(ctrl))
		ctrl = bf(self.read(self.map['CONTROL']))
		# print('CONTROL reg after enable/disable:', int(ctrl))
	'''
	enable serial test-pattern data on output
	'''
	def testpattern_mode(self, enable=True):     #when enabled, SELany bit is 0
		rdout = bf(self.read(self.map['READOUT']))
		if enable:
			rdout[4] = 0 
			self.write(self.map['READOUT'], int(rdout))
		else:
			rdout[4] = 1
			self.write(self.map['READOUT'], int(rdout))

	def testpattern(self, lab4, pattern=0xBA6):
		self.l4reg(lab4, 13, pattern)
		return [lab4, pattern]

	'''
	Enable test-pattern data into readout RAM (prints out counter)
	'''
	def readout_testpattern_mode(self, enable=True):
			ctrl = bf(self.read(self.map['CONTROL']))
			if enable:
					ctrl[15] = 1
			else:
					ctrl[15] = 0
			self.write(self.map['CONTROL'], int(ctrl))

	def read(self, addr):
		return self.dev.read(addr + self.base)
    
	def write(self, addr, value):
		self.dev.write(addr + self.base, value)

	def check_fifo(self, check_fifos=False):
			rdout = bf(self.read(self.map['READOUT']))
			'''
			check_mode = 0, check if data available on any fifo (not empty)
			check_mode = 1, check individual readout fifo empties, return 12 bits
			'''
			if check_fifos:
					return rdout[27:16]    
			else:
					return rdout[3]

	def set_fifo_empty(self, threshold):
			self.write(self.map['READOUTEMPTY'], threshold)
                
	def dll(self, lab4, mode=False, sstoutfb=104):
		'''enable/disable dll by setting VanN level'''
		if mode:
				self.run_mode(0)
				self.l4reg(lab4, 386, int(sstoutfb)) #set sstoutfb (should already be set)
				'''turn off internal Vadjn buffer bias'''
				self.l4reg(lab4, 2, 0)      #PCLK-1=2 : VanN
				
				calFbs = surf_calibrations.read_vtrimfb(self.dev.dna())
				if calFbs == None:
						# print ("Using default Vtrimfb of 1300.")
						# self.l4reg(lab4, 11, 1300)
					if lab4 == 15:
						for i in range(12):
							self.l4reg(i,11,1300)
					else:
						self.l4reg(lab4, 11, 1300)
				else:
					print ("Using cal file for Vtrimfb's")
					if lab4 == 15:
							for i in range(12):
								self.l4reg(i,11,calFbs[i])
					else:
						self.l4reg(lab4, 11, calFbs[lab4]) 
		else:
			'''turn on internal Vadjn buffer bias'''
			self.l4reg(lab4, 2, 1024)
                        
	def l4reg(self, lab, addr, value, verbose=False):
		ctrl = bf(self.read(self.map['CONTROL']))
		if ctrl[1]:  #should be checking ctrl[2], which indicates run-mode. but not working 6/9
				print ('LAB4_Controller is running, cannot update registers.' )
				return
		user = bf(self.read(self.map['L4REG']))
		if user[31]:
				print ('LAB4_Controller is still processing a register?' )
				return
		user[11:0] = value
		user[23:12] = addr
		user[27:24] = lab
		user[31] = 1
		if verbose:
			print ('Going to write 0x%X' % user )
		self.write(self.map['L4REG'], int(user))
		while not user[31]:
			user = bf(self.read(self.map['L4REG']))
		user1 = bf(self.read(self.map['L4REG']))	
		# print('L4REF value read is ', int(user1[11:0]))	

	def default(self, lab4=15):
		'''DAC default values'''
		self.l4reg(lab4, 0, 1024)      #PCLK-1=0 : Vboot 
		self.l4reg(lab4, 1, 1024)      #PCLK-1=1 : Vbsx
		self.l4reg(lab4, 2, 1024)      #PCLK-1=2 : VanN
		calNs = surf_calibrations.read_vadjn(self.dev.dna())
		if calNs == None:
			print ("Using default VadjN of 1671.")
			# self.l4reg(lab4, 3, 1671)
			if lab4 == 15:
				for i in range(12):
					self.l4reg(i, 3, 1671)
			else:
				self.l4reg(lab4, 3, 1671)
		else:
			print ("Using cal file for VadjN's")
			if lab4 == 15:
				for i in range(12):
					self.l4reg(i,3,calNs[i])
			else:
				self.l4reg(lab4, 3, calNs[lab4])

		calPs = surf_calibrations.read_vadjp(self.dev.dna())
		if calPs == None:
			print ("Using default VadjP of 2700.")
			if lab4 == 15:
				for i in range(12):
					self.l4reg(i, 8, 2700)
			# self.l4reg(lab4, 8, 2700)
			else:
				self.l4reg(lab4, 8, 2700)
		else:
			print ("Using cal file for VadjP's")
			if lab4 == 15:
				for i in range(12):
					self.l4reg(i,8,calPs[i])
			else:
				self.l4reg(lab4, 8, calPs[lab4])

		self.l4reg(lab4, 4, 1024)      #PCLK-1=4 : Vbs 
		self.l4reg(lab4, 5, 1100)      #PCLK-1=5 : Vbias 
		self.l4reg(lab4, 6, 950)       #PCLK-1=6 : Vbias2 
		self.l4reg(lab4, 7, 1024)      #PCLK-1=7 : CMPbias 
		self.l4reg(lab4, 9, 1000)      #PCLK-1=9 : Qbias 
		#self.l4reg(lab4, 10, 2780)     #PCLK-1=10 : ISEL (gives ~20 us long ramp)
		#self.l4reg(lab4, 10, 2350)     #PCLK-1=10 : ISEL (gives ~5 us long ramp)
		self.l4reg(lab4, 10, 2580)     #PCLK-1=10 : ISEL (gives ~10 us long ramp)

		calFbs = surf_calibrations.read_vtrimfb(self.dev.dna())
		if calFbs == None:
			print ("Using default Vtrimfb of 1350.")
			if lab4 == 15:
				for i in range(12):
					self.l4reg(i, 11, 1350)
				# self.l4reg(lab4, 11, 1350)
			else:
				self.l4reg(lab4, 11, 1350)
		else:
			print ("Using cal file for Vtrimfb's")
			if lab4 == 15:
					for i in range(12):
						self.l4reg(i,11,calFbs[i])
			else:
				self.l4reg(lab4, 11, calFbs[lab4])
								
		self.l4reg(lab4, 16, 0)        #patrick said to add 6/9

		for i in range (0, 128):       #PCLK-1=<256:384> : dTrim DACS
				#self.l4reg(lab4, i+256, 0)
			self.l4reg(lab4, i+256, 1600)

		'''timing register default values'''        
		self.l4reg(lab4, 384, 95)      #PCLK-1=384 : wr_strb_le 
		self.l4reg(lab4, 385, 0)       #PCLK-1=385 : wr_strb_fe 
		#self.l4reg(lab4, 386, 120)     #PCLK-1=386 : sstoutfb
		self.l4reg(lab4, 386, 104)     #PCLK-1=386 : sstoutfb --optimized for lab0 on canoes, to be generalized 
		self.l4reg(lab4, 387, 0)       #PCLK-1=387 : wr_addr_sync 
		self.l4reg(lab4, 388, 55)      #PCLK-1=388 : tmk_s1_le  --was 38
		self.l4reg(lab4, 389, 86)      #PCLK-1=389 : tmk_s1_fe 
		self.l4reg(lab4, 390, 7)       #PCLK-1=390 : tmk_s2_le  --was 110
		self.l4reg(lab4, 391, 32)      #PCLK-1=391 : tmk_s2_fe  --was 20
		self.l4reg(lab4, 392, 35)      #PCLK-1=392 : phase_le -- was 45 6/8
		self.l4reg(lab4, 393, 75)      #PCLK-1=393 : phase_fe -- was 85 6/8
		self.l4reg(lab4, 394, 100)     #PCLK-1=394 : sspin_le --maybe push up to 104 to squeek out extra ABW (was at 92)
		self.l4reg(lab4, 395, 6)       #PCLK-1=395 : sspin_fe

		'''default test pattern'''
		self.l4reg(lab4, 13, 0xBA6)    #PCLK-1=13  : LoadTPG
                
class SURF(ocpci.Device):
	internalClock = 1
	externalClock = 0
	map = { 'IDENT'                     : 0x00000,
			'VERSION'                   : 0x00004,
			'INTCSR'    		: 0x00008,
			'INTMASK'      		: 0x0000C,
			'PPSSEL'       		: 0x00010,
			'RESET'        		: 0x00014,
			'LED'          		: 0x00018,
			'CLKSEL'       		: 0x0001C,      ## this is a clock
			'PLLCTRL'      		: 0x00020,      ## this is a clock, PLL = phase locked loop 
			'SPICS'                     : 0x00024,      ## this is the spiss variable in the firmware doc 
			'PHASESEL'                  : 0x00028,
			'DNA'                       : 0x0002C,
			'SPI_BASE'                  : 0x00030,
			'LAB4_CTRL_BASE'            : 0x10000,
		'LAB4_ROM_BASE'             : 0x20000,      
			'RFP_BASE'                  : 0x30000,
			'DMA_BASE'                  : 0x40000
			}


	def __init__(self, path=ocpci.Device.default_path()):
		super(SURF, self).__init__(path, 1*1024*1024)
		self.spi  = spi.SPI(self, self.map['SPI_BASE'])
		self.labc = LAB4_Controller(self, self.map['LAB4_CTRL_BASE'])
		self.i2c  = surf_i2c.SURFi2c(self, self.map['RFP_BASE'])
		self.vped = 0x9C4
        
	def __repr__(self):
		return "<SURF at %s>" % self.path

	def __str__(self):
		return "SURF (@%s)" % self.path
    
	def spi_cs(self, device, state):
		# We only have 1 SPI device.
		val = bf(self.read(self.map['SPICS']))
		val[device] = state
		self.write(self.map['SPICS'], int(val))
		
	def set_phase(self, phase=0):
		#fix later
		self.write(self.map['PHASESEL'], phase)
		user1 = bf(self.read(self.map['PHASESEL']))	
		print('PHASESEL read is ', int(user1[11:0]))

	def led(self, arg):
		off_led_num = 14                     # initializing this to something while debugging 
		on_led_num = 14
		off_value = 2
		on_value = 2
		self.led_unusedbits = "0000"
		self.led_KEY_list = [1]*12    #array so that we can change values, setting all to one initially
		print ("LED function works!")
		print ("  ")
		if arg == "all off":
			self.led_off()                             # call the function for turning LED's off
		elif arg == "all on":
			self.led_on()                              # call the function for turning LED's on
		elif arg == "release":
			self.led_release()                         # call function for releasing LED (we stop controlling it)
		elif arg == "one off":
			off_led_num = int(input("Enter number of LED you want to turn off: "))
			off_value = 0
			self.led_one(off_led_num,off_value)
		elif arg == "one on":
			on_led_num = int(input("Enter number of LED you want to turn on: "))
			on_value = 1
			self.led_one(on_led_num,on_value)
		else:
			print ("Invalid argument! Your options are all off, all on, release, one off, one on" )


	def list_to_string(self,list):
		return "".join(map(str,list))
				
	def led_one(self,led_num,value):
		led_current = bf(self.read(self.map['LED']))
		led_current_binary = "{0:b}".format(led_current[31:0])                             # string containing current LED configuration in binary
		led_current_binary = "0000" + led_current_binary
		print ("integer value of led_current_binary: " + str(int(led_current_binary,base=2)))
		print( led_num)
		print( value) 
		print ("current LED values in binary: " + led_current_binary )                       # this string misses the first four zeros!
		print (len(led_current_binary))
		print( led_current_binary[0])
		print (led_current_binary[15], led_current_binary[16])
		print( led_current_binary[27] )
		print ("the type of led_current_binary is: %s" % (type(led_current_binary))  )       # check it's a string!
		print (" " )      
		led_current_VALUE = led_current_binary[20:32]                                      # take last part of string to get just VALUES
		led_VALUE_list = list(led_current_VALUE)                                           # turn string into list so we can easily toggle its values
		print ("The length of the array is %d" % (len(led_VALUE_list))	)
		led_VALUE_list[led_num] = value                                                    # change the LED value that user wants to change 
		led_VALUE_string = self.list_to_string(led_VALUE_list)                             # turn list of LED values back into string 
		led_KEY_string = self.list_to_string(self.led_KEY_list)                            # turn list of LED key values to string 
		led_full_string = self.led_unusedbits + led_KEY_string + self.led_unusedbits + led_VALUE_string    # put the different strings together to get full LED configuration
		print ("updated LED values in binary: " + led_full_string)
		self.write(self.map['LED'],int(led_full_string,base=2))                       # write in this new configuration to see the change take place 	
		print ("integer value of led_full_string: " + str(int(led_full_string,base=2)))
		u= bf(self.read(self.map['LED']))
		y= "{0:b}".format(u[31:0])	
		print ("after we change everyting: "+"0000" + y)		
		print (led_num)
		print (value )

	def led_off(self):
		self.write(self.map['LED'],0x0fff0000)
					

	def led_on(self):
		self.write(self.map['LED'],0x0fff0fff)           
			

	def led_release(self):
		self.write(self.map['LED'],0x00000000)  

	def clock(self, source):
		clocksel = bf(self.read(self.map['CLKSEL']))
		pllctrl = bf(self.read(self.map['PLLCTRL']))
		if source == self.internalClock:
			# Enable LAB clock.
			clocksel[1] = 1
			# Use FPGA input.
			clocksel[0] = 0
			# Enable local clock.
			clocksel[2] = 0
			if pllctrl[1]:
				# Switch PLL to internal clock. Need to reset it.
				pllctrl[1] = 0
				pllctrl[0] = 1
				self.write(self.map['PLLCTRL'], int(pllctrl))
				pllctrl[0] = 0
				self.write(self.map['PLLCTRL'], int(pllctrl))
			self.write(self.map['CLKSEL'], int(clocksel))
		elif source == self.externalClock:
			# Enable LAB clock.
			clocksel[1] = 1
			# Use TURF input.
			clocksel[0] = 1
			# Disable local clock
			clocksel[2] = 1
			if not pllctrl[1]:
				# Switch PLL to external clock. Need to reset it.
				pllctrl[1] = 1
				pllctrl[0] = 1
				self.write(self.map['PLLCTRL'], int(pllctrl))
				pllctrl[0] = 0
				self.write(self.map['PLLCTRL'], int(pllctrl))
			self.write(self.map['CLKSEL'], int(clocksel))
			
	def status(self):
		clocksel = bf(self.read(self.map['CLKSEL']))
		pllctrl = bf(self.read(self.map['PLLCTRL']))
		int_status = bf(self.read(self.map['INTCSR']))
		int_mask = bf(self.read(self.map['INTMASK']))
		led = bf(self.read(self.map['LED']))
		labcontrol = bf(self.labc.read(self.labc.map['CONTROL']))
		labreadout = bf(self.labc.read(self.labc.map['READOUT']))
		print ("Clock Status: LAB4 Clock is %s (CLKSEL[1] = %d)" % ("enabled" if clocksel[1] else "not enabled", clocksel[1]))
		print ("            : LAB4 Driving Clock is %s (CLKSEL[0] = %d)" % ("TURF Clock" if clocksel[0] else "FPGA Clock", clocksel[0]))
		print ("            : Local Clock is %s (CLKSEL[2] = %d)" % ("enabled" if not clocksel[2] else "not enabled", clocksel[2]))
		print ("            : FPGA System Clock PLL is %s (PLLCTRL[0] = %d/PLLCTRL[2] = %d)" % ("powered down" if pllctrl[2] else ("running" if not pllctrl[0] else "in reset"), pllctrl[0], pllctrl[2]))
		print ("            : FPGA System Clock is %s (PLLCTRL[1] = %d)" % ("TURF Clock" if pllctrl[1] else "Local Clock", pllctrl[1]))
		print (" Int Status : %8.8x" % (self.read(self.map['INTCSR']) & 0xFFFFFFFF))
		print (" LED        : Internal value %3.3x, Key value %3.3x" % (led[11:0], led[27:16]))
		print (" Full LED   : %8.8x" % (self.read(self.map['LED']) & 0xFFFFFFFF))
		print (" Int Mask   : %8.8x" % (self.read(self.map['INTMASK']) & 0xFFFFFFFF))
		print ("**********************")
		self.i2c.read_dac()
		print ("**********************")
		print( "LAB4 runmode: %s" % ("enabled" if labcontrol[1] else "not enabled"))
		print( "LAB4 testpat: %s" % ("enabled" if not labreadout[4] else "not enabled"))
		print ("LAB4 readout testpat: %s" % ("enabled" if labcontrol[15] else "not enabled")) 
    
	def set_vped(self, value=0x9C4):
		self.i2c.set_vped(value)
		self.vped=value  #update vped value

	def extTrig(self,enable=0):
		ctrl = bf(self.read(self.map['PPSSEL']))
		print('PPSSEL value is', int(ctrl))
		if enable:
			ctrl[16] = 1
			print('ext trig being enabled')
		else:
			ctrl[16] = 0
			print('ext trig being disabled')
		self.write(self.map['PPSSEL'], int(ctrl))

	def read_fifo(self, lab, address=0): 		
		val = bf(self.read(self.map['LAB4_ROM_BASE']+(lab<<11)+address))
		sample0  = val[15:0]
		sample1  = val[31:16]
		return int(sample0), int(sample1)

	# DMA a full board's worth of data.
	def dma_event(self, samples=1024):
		if not self.dma_enabled():
				print ("DMA is not enabled")
				return None
		board_data = []
		for i in range(12):
				labdata=np.zeros(samples, dtype=int)
				board_data.append(labdata)
		ioaddr = self.dma_base()
		# SUPER MEGA SPEED
		# we split up the DMA buffer into two buffers of 8192 bytes (this is the max theoretical to read out from a LAB,
		# even if you can't do it)
		# then we DMA into one half while unpacking the other half.
		for i in range(12):
				self.write(self.map['DMA_BASE'], self.map['LAB4_ROM_BASE']+(i<<11))
				# ping-pong between first 4096 bytes and second 4096 bytes
				# cache line size is 64 bytes, so no cache issues I think
				self.write(self.map['DMA_BASE']+0x4, ioaddr+(8192*(i&1)))
				self.write(self.map['DMA_BASE']+0x8, (samples>>1)-1)
				self.write(self.map['DMA_BASE']+0xC, 1)
				# If we're not loop #0, unpack the previous data
				if i:
						labdata = board_data[i-1]
						# obviously this is a mod 2 operation so can add instead of subtract
						offset = 8192*((i+1)&1)
						for i in range(0, int(samples), 2):                                
								labdata[i+1], labdata[i] = struct.unpack("<HH", self.dma_read(4, offset))
								offset = offset+4
						
				val = bf(self.read(self.map['DMA_BASE']+0xC))
				ntries = 0
				while not val[2]:
						if val[3]:
								print ('DMA error occurred: ', hex(int(val)))
								# issue abort
								self.write(self.map['DMA_BASE']+0xC, 0x10)
								return None
						if ntries > 10000:
								print( 'DMA timeout? : ', hex(int(val)))
								# issue abort
								self.write(self.map['DMA_BASE']+0xC, 0x10)
								return None
						ntries = ntries + 1
						val = bf(self.read(self.map['DMA_BASE']+0xC))
						
		# OK, so now we've DMA'd all of the event data, but we need to unpack the last one
		labdata = board_data[11]
		offset = 8192
		for i in range(0, int(samples), 2):
				labdata[i+1], labdata[i] = struct.unpack("<HH", self.dma_read(4, offset))
				offset = offset + 4
		return board_data                                
        

	# DMA a single lab's worth of data.
	def dma_lab(self, lab, samples=1024):
		# need something here to determine if the backend has DMA enabled and also to check the DMA address, I guess
		if not self.dma_enabled():
				print ("DMA is not enabled.")
				return None
		
		labdata=np.zeros(samples, dtype=int)
		# this is the board's I/O address in the IOMMU
		ioaddr = 0
		# write source address
		self.write(self.map['DMA_BASE'], self.map['LAB4_ROM_BASE']+(lab<<11))
		# write destination address
		self.write(self.map['DMA_BASE']+0x4, self.dma_base())
		# write number of samples minus 1
		self.write(self.map['DMA_BASE']+0x8, (samples>>1)-1)
		# initiate DMA
		self.write(self.map['DMA_BASE']+0xC, 1)
		val = bf(self.read(self.map['DMA_BASE']+0xC))
		ntries = 0
		while not val[2]:
				ntries = ntries + 1
				if val[3]:
						print ('DMA error occurred: ', hex(int(val)))
						# issue abort
						self.write(self.map['DMA_BASE']+0xC, 0x10)
						return None
				if ntries > 10000:
						print ('DMA timeout? : ', hex(int(val)))
						# issue abort
						self.write(self.map['DMA_BASE']+0xC, 0x10)
						return None
				val = bf(self.read(self.map['DMA_BASE']+0xC))
				
		# Note: unpacking means sample0 gets stuck in [31:16], and sample1 gets stuck in [15:0] (first write in most significant bits)
		offset = 0
		for i in range(0, int(samples), 2):
				labdata[i+1], labdata[i] = struct.unpack("<HH", self.dma_read(4, offset))
				offset = offset + 4

		return labdata                

	def pio_lab(self, lab, samples=1024, max_tries=2000):
		labdata = np.zeros(samples, dtype=int)
		
		for i in range(0, int(samples), 2):
				tries=0
				while (self.labc.check_fifo(1) and (1<<lab)):
						if tries > max_tries:
								print ('no data available')
								break
						else:
								tries=tries+1
								time.sleep(0.005)

				labdata[i+1], labdata[i] = self.read_fifo(lab)
		return labdata

	def dma_lab_events(self, lab, nevents, samples=1024, force_trig=False, save=False, filename=''):
		if not self.dma_enabled():
				print ("DMA not enabled")
				return None
		
		# allocate the buffer
		raw_data=bytearray(nevents*samples*2)
		# write source address
		self.write(self.map['DMA_BASE'], self.map['LAB4_ROM_BASE']+(lab<<11))
		# write destination address
		self.write(self.map['DMA_BASE']+0x4, self.dma_base())
		# write number of samples minus 1
		self.write(self.map['DMA_BASE']+0x8, (samples>>1)-1)
		control_addr = self.map['DMA_BASE']+0xC
		ptr = 0
		increment = samples*2
		endptr = ptr + increment

		# buffer check
		buf = (self.labc.read(0) & 0xC0) >> 6        
		while nevents:
				nevents = nevents - 1
				# Force trigger if requested,
				# then wait for the FIFO to fill.
				# Note that we wait until the *entire* FIFO
				# fills, because the current setup is stupid.
				# (Obviously the readout FIFO should be placed
				# inside the 'DMA controller' so you don't
				# double-copy data. But because we want to maintain
				# PIO access for non-VFIO systems, we're being dumb.)
				if force_trig:
						# buffer check
						last_buf = buf
						temp = self.labc.read(0)
						if ((temp&0xC0)>>6) != buf:
								print ("warning: last buf was %d but changed to %d before trigger" % (last_buf, (tmp&0xC0)>>6))
						self.labc.force_trigger()
						max_tries=1000
						val=self.labc.check_fifo(True)
						while val & (1<<lab):
								val = self.labc.check_fifo(True)
								max_tries = max_tries -1
								if not max_tries:
										print ('no data after trigger')
										break
						# buffer check
						buf = (self.labc.read(0) & 0xC0) >> 6
						if buf != ((last_buf+1) & 0x3):
								print( "warning: last buf %d cur buf %d" % (last_buf, buf))
				else:
						# maybe do some weird timeout-y thing here.
						# time-check overhead is only 240 ns, so maybe worth it?
						val=self.labc.check_fifo(True)                
						while val & (1<<lab):
								val = self.labc.check_fifo(True)
				self.write(control_addr, 1)
				# need a timeout here too?
				val = self.read(control_addr)
				if not (val & 0x4):
						val = self.read(control_addr)
				raw_data[ptr:endptr] = self.dma_read(increment)
				ptr = ptr + increment
				endptr = ptr + increment
		if save:
				if len(filename)<=1:
						timestr=time.strftime('%Y%m%d-%H%M%S')
						filename= timestr+'_LAB'+str(lab)+'.dat'
				with open(filename, 'wb') as newFile:
						newFile.write(raw_data)

		return raw_data
        
                        
	def log_lab(self, lab, samples=1024, force_trig=False, save=False, filename=''):
		max_tries=1000
		labs=[]
		if lab==15:
				labs = range(12)
		else:
				labs = [lab]

		if force_trig:
				self.labc.force_trigger()
						
		board_data = []
		tries=0

		while(self.labc.check_fifo()):
				if tries > max_tries:
						print ('no data available')
						return 1
				else:
						print ('no data available, trying again..')
						time.sleep(0.05)
						tries=tries+1
       
		for chan in labs:
				# programmed I/O transfer
				labdata=self.pio_lab(chan, samples)
				# DMA transfer
				# labdata=self.dma_lab(chan, samples)
				board_data.append(labdata )

		#save some data to a flat text file
		if save:
				if len(filename)<=1:
						timestr=time.strftime('%Y%m%d-%H%M%S')
						filename= timestr+'_LAB'+str(lab)+'.dat'
				
				with open(filename, 'w') as filew:
						for j in range(0, samples):
								for i in range(0, len(board_data)):
										filew.write(str(board_data[i][j]))
										filew.write('\t')
								filew.write('\n')
		return board_data

	def scope_lab(self, lab, samples=1024, force_trig=True, frames=1, refresh=0.1):
		import matplotlib.pyplot as plt
		plt.ion()

		x=np.arange(samples)
		for i in range(0, frames):
				fig=plt.figure(1)
				plt.clf()
				plot_data = self.log_lab(lab=lab, samples=samples, force_trig=True)
				#plot_data = np.sin(x+np.random.uniform(0,np.pi))+np.random.normal(0, .1)
				for chan in range(0, len(plot_data)):
						plt.plot(x, np.bitwise_and(plot_data[chan], 0x0FFF), '--', label='LAB{}'.format(chan))
				#plt.legend(numpoints=1, ncol=6, prop={'size':8})
				if i == (frames-1):
						raw_input('press enter to close')
						plt.close(fig)
						plt.ioff()
				else:
						plt.pause(refresh)
                        
                  
	def identify(self):
		ident = bf(self.read(self.map['IDENT']))
		ver = bf(self.read(self.map['VERSION']))
		# print(self.read(self.map['IDENT']))
		# print(self.read(self.map['VERSION']))
		print ("Identification Register: %x (%c%c%c%c)" % (int(ident),ident[31:24],ident[23:16],ident[15:8],ident[7:0]))
		print ("Version Register: %d.%d.%d compiled %d/%d" % (ver[15:12], ver[11:8], ver[7:0], ver[28:24], ver[23:16]))
		print ("Device DNA: %x" % self.dna())
		print ("Device DNA: ", int(self.dna()))

	def dna(self):
		self.write(self.map['DNA'], 0x80000000)
		dnaval=0
		for i in range(57):
			val=self.read(self.map['DNA'])
			dnaval = (dnaval << 1) | val
		return dnaval

        