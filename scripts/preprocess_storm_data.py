import pandas as pd
import numpy as np
import json
import math
import os

def preprocess():
    csv_path = "E:/Space_Weather_pre/datasets/raw/omni_2024-01-01_to_2026-07-01.csv"
    out_dir = "E:/Space_Weather_pre/datasets/processed"
    out_path = os.path.join(out_dir, "storm_data_interpolated.json")
    
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"Reading OMNI raw dataset from: {csv_path}")
    df = pd.read_csv(csv_path)
    
    # Filter for May 10-11, 2024 extreme solar storm (48 hours)
    mask = df['timestamp'].str.startswith('2024-05-10') | df['timestamp'].str.startswith('2024-05-11')
    storm_df = df[mask].reset_index(drop=True)
    
    if len(storm_df) == 0:
        print("Error: Could not find storm sequence in raw OMNI data.")
        return False
        
    # Interpolate hourly storm data to 250 animation frames
    frames = np.linspace(0, len(storm_df) - 1, 250)
    interpolated_data = []
    
    for f in range(250):
        idx_float = frames[f]
        idx_lower = int(math.floor(idx_float))
        idx_upper = min(int(math.ceil(idx_float)), len(storm_df) - 1)
        weight = idx_float - idx_lower
        
        row_lower = storm_df.iloc[idx_lower]
        row_upper = storm_df.iloc[idx_upper]
        
        interpolated_row = {}
        for col in ['VELOCITY', 'DENSITY', 'DYNAMIC_PRESSURE', 'BZ_GSE', 'KP', 'DST']:
            val = row_lower[col] * (1 - weight) + row_upper[col] * weight
            if math.isnan(val):
                val = 0.0
            interpolated_row[col] = float(val)
            
        timestamp_str = str(row_lower['timestamp'])
        try:
            date_part = timestamp_str.split(" ")[0].split("-")[1] + "-" + timestamp_str.split(" ")[0].split("-")[2]
            time_part = timestamp_str.split(" ")[1][:5]
            interpolated_row['timestamp'] = f"{date_part} {time_part}"
        except:
            interpolated_row['timestamp'] = timestamp_str[:16]
            
        interpolated_data.append(interpolated_row)
        
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(interpolated_data, f, indent=2)
        
    print(f"Successfully preprocessed and written 250 frames of storm data to: {out_path}")
    return True

if __name__ == "__main__":
    preprocess()
