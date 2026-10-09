import pandas as pd
import numpy as np
from prophet import Prophet
import sys
from pathlib import Path
import logging

logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

def main():
    print("Reading consumption.parquet...")
    df = pd.read_parquet('data/raw/hackathon/consumption.parquet')
    
    # Take a sample for fast evaluation or do global evaluation.
    # We will sample 10 time series to demonstrate baseline training.
    print(f"Total time series: {df.groupby(['territory_id', 'category']).ngroups}")
    print("Training Prophet baseline on 100 random time series...")
    
    np.random.seed(42)
    territories = df['territory_id'].unique()
    sampled_territories = np.random.choice(territories, size=20, replace=False)
    
    sub_df = df[df['territory_id'].isin(sampled_territories)]
    
    # Split into train/test (last 12 months as test)
    # The dates are YYYY-MM
    dates = sorted(df['date'].unique())
    train_dates = dates[:-12]
    test_dates = dates[-12:]
    
    maes = {1: [], 3: [], 6: [], 12: []}
    
    grouped = sub_df.groupby(['territory_id', 'category'])
    
    count = 0
    for (t, c), group in grouped:
        group = group.sort_values('date')
        
        train = group[group['date'].isin(train_dates)]
        test = group[group['date'].isin(test_dates)]
        
        if len(train) < 5 or len(test) < 12:
            continue
            
        train_p = pd.DataFrame({'ds': pd.to_datetime(train['date'] + '-01'), 'y': train['value']})
        
        m = Prophet(weekly_seasonality=False, daily_seasonality=False)
        m.fit(train_p)
        
        future = m.make_future_dataframe(periods=12, freq='MS', include_history=False)
        forecast = m.predict(future)
        
        y_true = test['value'].values
        y_pred = forecast['yhat'].values
        
        for h in [1, 3, 6, 12]:
            if len(y_true) >= h:
                maes[h].append(np.mean(np.abs(y_true[:h] - y_pred[:h])))
                
        count += 1
        if count >= 100:
            break
            
    print("\n--- Baseline MAE on test set ---")
    for h in [1, 3, 6, 12]:
        print(f"Horizon {h} months: {np.mean(maes[h]):.2f}")

if __name__ == '__main__':
    main()
