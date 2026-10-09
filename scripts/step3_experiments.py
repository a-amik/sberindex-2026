import pandas as pd
import numpy as np
from prophet import Prophet
import logging

logging.getLogger("prophet").setLevel(logging.ERROR)
logging.getLogger("cmdstanpy").setLevel(logging.ERROR)

def run_experiment(df, regressors=None, name="Baseline"):
    np.random.seed(42)
    territories = df['territory_id'].unique()
    sampled_territories = np.random.choice(territories, size=20, replace=False)
    
    sub_df = df[df['territory_id'].isin(sampled_territories)].copy()
    
    # Forward fill or fillna 0 for regressors
    if regressors:
        for r in regressors:
            sub_df[r] = sub_df[r].fillna(0)
    
    dates = sorted(sub_df['date'].unique())
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
        if regressors:
            for r in regressors:
                train_p[r] = train[r].values
        
        m = Prophet(weekly_seasonality=False, daily_seasonality=False)
        if regressors:
            for r in regressors:
                m.add_regressor(r)
        
        m.fit(train_p)
        
        future = m.make_future_dataframe(periods=12, freq='MS', include_history=False)
        if regressors:
            for r in regressors:
                future[r] = test[r].values
                
        forecast = m.predict(future)
        y_true = test['value'].values
        y_pred = forecast['yhat'].values
        
        for h in [1, 3, 6, 12]:
            if len(y_true) >= h:
                maes[h].append(np.mean(np.abs(y_true[:h] - y_pred[:h])))
                
        count += 1
        if count >= 100:
            break
            
    print(f"\n--- {name} MAE ---")
    for h in [1, 3, 6, 12]:
        print(f"Horizon {h} months: {np.mean(maes[h]):.2f}")

def main():
    print("Loading features.parquet...")
    try:
        df = pd.read_parquet('data/processed/features.parquet')
    except Exception as e:
        print("Features file not found. Ensure build_features.py is finished.", e)
        return

    # Baseline (no regressors)
    run_experiment(df, regressors=None, name="Baseline (No extra features)")
    
    # 1. Macro (Key Rate)
    run_experiment(df, regressors=['key_rate_mean'], name="Hypothesis 1: Key Rate")
    
    # 2. Weather
    run_experiment(df, regressors=['PRECTOTCORR', 'T2M'], name="Hypothesis 2: Weather")
    
    # 3. News
    if 'news_intensity' in df.columns:
        run_experiment(df, regressors=['news_intensity'], name="Hypothesis 3: News Intensity")
    else:
        print("news_intensity column missing.")

if __name__ == '__main__':
    main()
