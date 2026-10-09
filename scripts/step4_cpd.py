import pandas as pd
import numpy as np

def cusum_detect(residuals, threshold=2.0, drift=0.5):
    """
    Simple CUSUM for structural change detection.
    """
    S_hi = np.zeros(len(residuals) + 1)
    S_lo = np.zeros(len(residuals) + 1)
    alarms = []
    
    for i, res in enumerate(residuals):
        S_hi[i+1] = max(0, S_hi[i] + res - drift)
        S_lo[i+1] = max(0, S_lo[i] - res - drift)
        
        if S_hi[i+1] > threshold or S_lo[i+1] > threshold:
            alarms.append(i)
            # Reset after alarm
            S_hi[i+1] = 0
            S_lo[i+1] = 0
            
    return alarms

def main():
    print("Loading features.parquet...")
    df = pd.read_parquet('data/processed/features.parquet')
    
    print("Simulating CUSUM CPD on residuals with News Prior...")
    np.random.seed(42)
    
    # Take one time series as an example
    sample_tid = df['territory_id'].unique()[0]
    sample_df = df[df['territory_id'] == sample_tid].sort_values('date')
    
    # Suppose we have residuals from a model (e.g. naive forecast residuals)
    values = sample_df['value'].values
    residuals = values[1:] - values[:-1] # naive residuals
    # Standardize
    residuals = (residuals - np.mean(residuals)) / (np.std(residuals) + 1e-9)
    
    # News prior: if news_intensity > 0, we lower the threshold for CUSUM
    news = sample_df['news_intensity'].values[1:]
    
    base_threshold = 3.0
    drift = 0.5
    
    S_hi = np.zeros(len(residuals) + 1)
    S_lo = np.zeros(len(residuals) + 1)
    alarms = []
    
    for i, (res, news_val) in enumerate(zip(residuals, news)):
        # Dynamic threshold based on news prior
        # E.g., if there's news, reduce threshold by 1.0 (more sensitive)
        current_threshold = base_threshold - (1.0 if news_val > 0 else 0.0)
        
        S_hi[i+1] = max(0, S_hi[i] + res - drift)
        S_lo[i+1] = max(0, S_lo[i] - res - drift)
        
        if S_hi[i+1] > current_threshold or S_lo[i+1] > current_threshold:
            alarms.append((i, sample_df['date'].iloc[i+1]))
            S_hi[i+1] = 0
            S_lo[i+1] = 0
            
    print(f"Detected {len(alarms)} structural shocks for Territory {sample_tid}.")
    for idx, date in alarms:
        print(f" - Shock detected at {date}")
        
    print("Step 4 complete: CUSUM with news prior demonstrated.")

if __name__ == '__main__':
    main()
