
import pandas as pd
import numpy as np


def calc_std(p_series, row, nlag):
    if row.name < nlag - 1:
        return np.nan

    return p_series[row.name-nlag+1:row.name+1].std()


def std(df, col_name, nlag=0):
    if nlag == 0:
        nlag = df.shape[0]

    std = df.apply(lambda row: calc_std(df[col_name], row, nlag), axis=1)
    return std
