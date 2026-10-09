import pandas as pd
import numpy as np
from pathlib import Path
import re

def main():
    print("Loading data...")
    # 1. Load target data
    consumption = pd.read_parquet('data/raw/hackathon/consumption.parquet')
    
    # 2. Load weather and key_rate
    weather = pd.read_parquet('data/external/weather.parquet')
    key_rate = pd.read_parquet('data/external/key_rate.parquet')
    
    # rename period to date to match consumption
    weather = weather.rename(columns={'period': 'date'})
    key_rate = key_rate.rename(columns={'period': 'date'})
    
    # 3. Build news gazetteer
    print("Building news gazetteer...")
    news = pd.read_parquet('data/external/news_headlines.parquet')
    municipal_dict = pd.read_excel('data/raw/hackathon/t_dict_municipal_districts.xlsx')
    
    # Extract year-month for news
    news['date'] = pd.to_datetime(news['date']).dt.strftime('%Y-%m')
    
    # We want to match names of municipalities to news titles.
    # We can create a simple regex or string match.
    # To keep it fast, we will extract lowercase words from titles.
    
    # We will compute news intensity: count of news mentioning the municipality per month
    print("Mapping news to territory_id (this might take a bit)...")
    municipal_dict['name_lower'] = municipal_dict['municipal_district_name_short'].astype(str).str.lower()
    
    # For performance on a large dataset, we can extract common names, 
    # but let's do a simple exact match for demonstration. 
    # Let's take just a subset of highly mentioned municipalities to avoid long compute,
    # or use a fast word matching technique.
    
    titles_lower = news['title'].astype(str).str.lower()
    
    # Create a mapping dictionary {territory_id: name}
    territory_names = dict(zip(municipal_dict['territory_id'], municipal_dict['name_lower']))
    
    # Instead of N x M comparisons, let's tokenize news and intersect
    # We will build a feature DataFrame directly
    
    # To save time in the agent environment, we will use a naive approach but limit to available territory_ids in consumption
    active_territories = consumption['territory_id'].unique()
    news_features = []
    
    # Optimize by doing groupby date first
    news_by_date = news.groupby('date')
    
    results = []
    for d, group in news_by_date:
        text_corpus = " ".join(group['title'].astype(str).str.lower())
        for tid in active_territories:
            if tid in territory_names:
                name = territory_names[tid]
                # very naive match: check if name is in corpus
                count = text_corpus.count(name)
                if count > 0:
                    results.append({'date': d, 'territory_id': tid, 'news_intensity': count})
    
    news_df = pd.DataFrame(results)
    
    print("Merging features...")
    # Merge all
    features = consumption.merge(weather, on=['territory_id', 'date'], how='left')
    features = features.merge(key_rate, on=['date'], how='left')
    
    if not news_df.empty:
        features = features.merge(news_df, on=['territory_id', 'date'], how='left')
        features['news_intensity'] = features['news_intensity'].fillna(0)
    else:
        features['news_intensity'] = 0
        
    print(f"Features dataset shape: {features.shape}")
    
    out_path = Path('data/processed/features.parquet')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(out_path, index=False)
    print(f"Features saved to {out_path}")

if __name__ == '__main__':
    main()
