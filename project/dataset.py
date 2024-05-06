import os
import torch
import numpy as np
import netCDF4 as nc
from torch.utils.data import Dataset, DataLoader
from datetime import datetime
# Ignore warnings
import warnings
warnings.filterwarnings("ignore")

class DownscalingDataset(Dataset):
    """Face Landmarks dataset."""

    def __init__(self, low_res_data, high_res_data, low_var_name=None, high_var_name=None, indices=None):
        """
        Args:
            root_dir (string): Directory with all the images.
            low_res_path (string): Path to the low resolution data.
            high_res_path (string): Path to the high resolution data.
            indices (array) : indices of the subset (train, val, test)
        """
        if indices is not None:
            self.low_res_data = low_res_data[indices]
            self.high_res_data = high_res_data[indices]
        else:
            self.low_res_data = low_res_data
            self.high_res_data = high_res_data

        self.low_var_name = low_var_name
        self.high_var_name = high_var_name
        # self.transform = transform

        if len(self.low_res_data) != len(self.high_res_data):
            raise ValueError("Low res and high res data must have the same length")


    def __len__(self):
        return len(self.low_res_data)

    def get_var_name(self):
        if self.low_var_name is None or self.high_var_name is None:
            warnings.warn("Some variable names are not set")
        print("Low res variable name: ", self.low_var_name)
        print("High res variable name: ", self.high_var_name)

    def __getitem__(self, idx):
        if torch.is_tensor(idx):
            idx = idx.tolist()

        low_res = np.array(self.low_res_data[idx])
        high_res = self.high_res_data[idx]
        
        # if self.transform:
            # high_res = self.transform(high_res)
            

        sample = {'low_res': low_res, 'high_res': high_res}

        return sample

def spliting_indices(n, val_pct=0.15, test_pct=0.15):
    n_val = int(val_pct * n)
    n_test = int(test_pct * n)
    n_train = n - n_val - n_test
    indices = np.random.permutation(n)
    return indices[:n_train], indices[n_train:n_train + n_val], indices[n_train + n_val:]
    
    
def merge_out_data(start_year, end_year):
    high_res_data = None
    high_res_dt = None
    for year in range(start_year, end_year+1):
        if high_res_data is None:
            high_res_data = np.load('download/cerra/si10-' + str(year) + '.npy')
            high_res_dt = np.load('download/cerra/datetime_' + str(year) + '.npy')
        else:
            tmp = np.load('download/cerra/si10-' + str(year) + '.npy')
            high_res_data = np.concatenate((high_res_data, tmp), axis=0)
            tmp_dt = np.load('download/cerra/datetime_' + str(year) + '.npy')
            high_res_dt = np.concatenate((high_res_dt, tmp_dt), axis=0)
   
    return high_res_data, high_res_dt
    

def make_clean_data(in_vars, start_year, end_year):
    if start_year < 2010 or end_year > 2020:
        print("year must be greater than 2010 and less than 2020")
        return
    
    out_data, out_date = merge_out_data(2010, 2020)
    in_data = None
    for in_var in in_vars:   
        in_path = 'download/era5/'+in_var+'-2010_2020.nc'
        tmp_data = nc.Dataset(in_path)
        tmp_data = np.expand_dims(tmp_data[in_var][:], axis=3)
        if in_data is None:
            in_data = tmp_data
        else:
            in_data = np.concatenate((in_data, tmp_data), axis=3)
    #filter data in fonction of start_year and end_year
    low_hour = datetime(start_year, 1, 1, 1).timestamp()
    high_hour = datetime(end_year, 1, 1, 1).timestamp()
    low_index = np.where(out_date == low_hour)[0][0]
    high_index = np.where(out_date == high_hour)[0][0]
    print(low_index, high_index)
    return in_data[low_index:high_index], out_data[low_index:high_index]


if __name__ == "__main__":
    in_data, out_data = make_clean_data(['u10'], 2010, 2019)
#     in_data = np.squeeze(in_data, axis=3)
    dataset = DownscalingDataset(in_data, out_data, low_var_name='u10', high_var_name='si10')
    dataset.get_var_name()
    print(len(dataset))
    print(dataset[0]["low_res"].shape)
    print(dataset[0]["high_res"].shape)
    
    

