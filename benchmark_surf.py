import time

class benchmarker:
    def __init__(self, dev):
        self.dev = dev

    def time_dma_only(self, nloops):
        total_loops = nloops
        # constant time setup
        self.dev.write(0x40000, 0x20000)
        self.dev.write(0x40004, 0)
        self.dev.write(0x40008, 511)
        start_time = time.time()
        while nloops:
            nloops = nloops-1
            self.dev.write(0x4000C, 1)
            val = self.dev.read(0x4000C)
            while not (val & 0x4):
                val = self.dev.read(0x4000C)
        end_time = time.time()
        total_bytes = 2048*total_loops
        total_time = end_time - start_time
        throughput = (total_bytes/total_time)
        print "total time: ", total_time, " throughput: ", throughput, " bytes/sec (", throughput/(1024.*1024.), " MB/s)"

    def time_dma_and_trigger(self, nloops):
        total_loops = nloops
        # constant time setup
        self.dev.write(0x40000, 0x20000)
        self.dev.write(0x40004, 0)
        self.dev.write(0x40008, 511)
        start_time = time.time()
        while nloops:
            nloops = nloops-1
            self.dev.labc.force_trigger()
            val = self.dev.labc.check_fifo(True)
            while (val & 0x1):
                val = self.dev.labc.check_fifo(True)
            self.dev.write(0x4000C, 1)
            val = self.dev.read(0x4000C)
            while not (val & 0x4):
                val = self.dev.read(0x4000C)
        end_time = time.time()
        total_bytes = 2048*total_loops
        total_time = end_time - start_time
        throughput = (total_bytes/total_time)
        print "total time: ", total_time, " throughput: ", throughput, " bytes/sec (", throughput/(1024.*1024.), " MB/s)"

        
    # benchmark doing a DMA and copying the data to a Python object (no processing)
    def time_dma_and_copy(self, nloops):
        total_data = bytearray(nloops*2048)
        # constant time setup
        self.dev.write(0x40000, 0x20000)
        self.dev.write(0x40004, 0)
        self.dev.write(0x40008, 511)
        start_time = time.time()
        ptr=0
        while nloops:
            nloops = nloops-1
            self.dev.write(0x4000C, 1)
            val = self.dev.read(0x4000C)
            while not (val & 0x4):
                val = self.dev.read(0x4000C)
            total_data[ptr:ptr+2048] = self.dev.dma_read(2048)
            ptr = ptr + 2048
            
        end_time = time.time()
        total_bytes = len(total_data)
        total_time = end_time - start_time
        throughput = (total_bytes/total_time)
        print "total time: ", total_time, " throughput: ", throughput, " bytes/sec (", throughput/(1024.*1024.), " MB/s)"        

    # benchmark doing a DMA and copying the data to a Python object (no processing)
    def time_trigger_and_copy(self, nloops):
        total_data = bytearray(nloops*2048)
        # constant time setup
        self.dev.write(0x40000, 0x20000)
        self.dev.write(0x40004, 0)
        self.dev.write(0x40008, 511)
        start_time = time.time()
        ptr=0
        while nloops:
            nloops = nloops-1
            self.dev.labc.force_trigger()
            val = self.dev.labc.check_fifo(True)
            while (val & 0x1):
                val = self.dev.labc.check_fifo(True)            
            self.dev.write(0x4000C, 1)
            val = self.dev.read(0x4000C)
            while not (val & 0x4):
                val = self.dev.read(0x4000C)
            total_data[ptr:ptr+2048] = self.dev.dma_read(2048)
            ptr = ptr + 2048
            
        end_time = time.time()
        total_bytes = len(total_data)
        total_time = end_time - start_time
        throughput = (total_bytes/total_time)
        print "total time: ", total_time, " throughput: ", throughput, " bytes/sec (", throughput/(1024.*1024.), " MB/s)"        
        return total_data
        
    def time_event(self, nloops):
        total_loops = nloops
        start_time = time.time()
        while nloops:
            nloops = nloops-1
            self.dev.labc.force_trigger()
            dat = self.dev.dma_lab(0)
        end_time = time.time()
        total_bytes = 2048*total_loops
        total_time = end_time - start_time
        throughput = (total_bytes/total_time)
        print "total time: ", total_time, " throughput: ", throughput, " bytes/sec (", throughput/(1024.*1024.), " MB/s)"


        
