import surf_daq, surf, surf_board, time

dev = surf_board.do()
dev.labc.reset_fifo()
dev.labc.testpattern_mode(0)
dev.labc.readout_testpattern_mode(0)
dev.labc.repeat_count(0)
dev.extTrig(0)
dev.set_vped(2500)
dev.labc.run_mode(1)
dev.labc.force_trigger()
# watch in chipscope to see if data is being written into FIFOs
# a 1-second sleep is long enough
time.sleep(1)
dev.labc.run_mode(0)
print("FIFO status:", hex(int(dev.labc.check_fifo(True))))