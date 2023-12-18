import numpy as np

def buildDataset(dat, count):
    npdat = np.frombuffer(dat, dtype='uint16')
    dataset = {}
    dataset['data'] = npdat
    dataset['count'] = np.array(count)
    return dataset

def loadDataset(filename):
    file = np.load(filename)
    if not 'count' in file or not 'data' in file:
        print ("error, file doesn't have count and data")
        return None
    return file

def saveDataset(dataset, filename):
    if not 'count' in dataset or not 'data' in dataset:
        print ("error, dataset doesn't even have count and data")
        return
    count = dataset['count']
    data = dataset['data']
    # sooo many possibilities
    if not 'headers' in dataset:
        # must be raw
        np.savez_compressed(filename, count=count, data=data)
        return

    headers = dataset['headers']
    if not 'windows' in dataset:
        # must be stripped/subtracted
        np.savez_compressed(filename,
                            count=count,
                            data=data,
                            headers=headers)
        return
    windows = dataset['windows']
    if not 'times' in dataset:
        # not timed
        np.savez_compressed(filename,
                            count=count,
                            data=data,
                            headers=headers,
                            windows=windows)
        return
    times = dataset['times']
    np.savez_compressed(filename,
                        count=count,
                        data=data,
                        headers=headers,
                        windows=windows,
                        times=times)
    
