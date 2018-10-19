import numpy as np

def zeroCrossings(dataset):
    # We need to reshape the dataset: it's count x 12 x 1024 currently.
    # Unlike the single-LAB case we can't collapse this as easily.
    # We need it to be count x 12 x 8 x 128.
    # Then we need to transpose it to 12 x 128 x 8 x count
    cells = np.reshape(dataset['data'], (dataset['count'], 12, 8, 128)).transpose(1, 3, 2, 0)
    # cells[0][0] is now an 8 x count array, of length 128.
    # the indexing is now lab, sample, window, count
    cellIsNegative = np.less_equal(cells, 0)
    cellIsPositive = np.greater(cells, 0)
    # shift the positive condition to the left one along the sample axis (cellIsPositive[0][0] now corresponds to cell 1)
    cellIsPositive = np.roll(cellIsPositive, -1, axis=1)
    # detect rising edge
    risingEdge = np.logical_and(cellIsPositive,cellIsNegative)
    # now average all rising along axis 2 and 3 (window and count)
    zeroCrossingFraction = np.mean(risingEdge, axis=(2,3))
    # this is now a 12 x 128 array
    
    # Again, have to redo this for the seams.
    cells = np.reshape(dataset['data'], (dataset['count'], 12, 1024)).transpose(1, 2, 0)
    # Strip out the seams (127, 255, 383, 511, 639, 767, 895)
    beforeSeam = cells[:, 127:1023:128]
    # ... and after seam (128, 256, 384, 512, 640, 768, 896)
    afterSeam = cells[:, 128::128]
    # these are now 12x7xcount arrays
    
    beforeSeamNegative = np.less_equal(beforeSeam, 0)
    afterSeamPositive = np.greater(afterSeam, 0)
    seamRising = np.logical_and(beforeSeamNegative, afterSeamPositive)
    # and average over sample, count axes
    seamEdgeFraction = np.mean(seamRising, axis=(1,2))
    # seamEdgeFraction is now 12 long, we need to insert it into the fraction array
    zeroCrossingFraction.transpose()[127] = seamEdgeFraction

    return zeroCrossingFraction
    
def zeroCrossingsLab(dataset):
    # Reshape into arrays of 128, and then transpose. So each row
    # is now the same sample, iterated over all the dataset.
    # e.g. cell[0] is an array of all of the samples of cell[0]
    cells = np.reshape(dataset['data'], (dataset['count']*8, 128)).transpose()
    # is the cell negative?
    cellIsNegative = cells <= 0
    # is the cell positive?
    cellIsPositive = cells > 0
    # shift the positive condition to the left one
    # (so cellIsPositive[0] is cell 1)
    cellIsPositive = np.roll(cellIsPositive, -1, axis=0)
    # detect rising edge
    risingEdge = cellIsPositive*cellIsNegative
    # average all rising edges
    zeroCrossingFraction = np.mean(risingEdge, axis=1)

    # We have to redo this for the seams, because the previous method
    # rolled the cells along the window boundary.
    # We *might* be able to all do this in one, but skip it.
    cells = np.reshape(dataset['data'], (dataset['count'],1024)).transpose()
    # So now we strip out the seams, and only the seams
    # Numpy's slicing does this for us.
    # Start at 127, stop before 1023.
    beforeSeam = cells[127:1023:128]
    # Start at 128, no need to stop (1024 is past bounds)
    afterSeam = cells[128::128]

    beforeSeamNegative = beforeSeam <= 0
    afterSeamPositive = afterSeam > 0

    seamRising = beforeSeamNegative * afterSeamPositive
    seamEdgeFraction = np.mean(seamRising)
    zeroCrossingFraction[127] = seamEdgeFraction
    
    return zeroCrossingFraction

