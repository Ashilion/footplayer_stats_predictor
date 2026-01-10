import pandas as pd
import glob
import os
import hopsworks
from dotenv import load_dotenv

def load_and_merge_csvs(folder_path):
    """Reads all CSVs in a folder, cleans headers, and merges them."""
    all_files = glob.glob(os.path.join(folder_path, "*.csv"))
    li = []
    
    for filename in all_files:
        if 'leicester' in filename.lower():
            continue
            
        match_id = os.path.basename(filename).split('.')[0]
        # Skip the first row to get clean headers as per your original logic
        df = pd.read_csv(filename, skiprows=1)
        
        df['match_id'] = match_id
        # Filter out summary rows
        df = df[df['Player'].str.contains('Players') == False]
        li.append(df)
        
    full_dataset = pd.concat(li, axis=0, ignore_index=True)
    return full_dataset

def clean_and_format_columns(df):
    """Handles renaming, lowercase conversion, and special character replacement."""
    # Identify team column (second-to-last)
    second_to_last_col = df.columns[-2]
    df = df.rename(columns={second_to_last_col: 'team', '#': 'player_number'})

    # Standardize column names for Hopsworks Feature Store compatibility
    df.columns = (df.columns
                  .str.lower()
                  .str.replace('%', '_perc', regex=False)
                  .str.replace('.', '_', regex=False))
    return df

def add_rolling_features(df, window_size=6):
    """Calculates rolling averages per player, shifted to avoid data leakage."""
    # Ensure sorting for time-series integrity
    df = df.sort_values(['player', 'age', 'match_id'])
    
    numeric_cols = df.select_dtypes(include=['float64', 'int64']).columns.tolist()
    
    for col in numeric_cols:
        # Calculate rolling mean shifted by 1 (previous matches only)
        rolling_series = (df.groupby('player')[col]
                          .transform(lambda x: x.rolling(window=window_size, min_periods=1).mean().shift(1)))
        
        df[f'rolling_avg_{col}'] = rolling_series.fillna(0)
    
    # Handle remaining NAs in the whole dataframe
    string_cols = df.select_dtypes(include=['object']).columns
    df[numeric_cols] = df[numeric_cols].fillna(0)
    df[string_cols] = df[string_cols].fillna('undef')
    
    return df

def upload_to_hopsworks(df, project_name, fg_name, version=1):
    """Logs into Hopsworks and inserts the dataframe into a Feature Group."""
    load_dotenv()
    api_key = os.getenv("HOPSWORKS_API_KEY")
    
    project = hopsworks.login(
        project=project_name, 
        api_key_value=api_key,
        host="eu-west.cloud.hopsworks.ai"
    )
    
    fs = project.get_feature_store()
    
    fg = fs.get_or_create_feature_group(
        name=fg_name,
        version=version,
        primary_key=["player", "match_id"],
        online_enabled=True,
        description="Player statistics with rolling averages"
    )
    
    fg.insert(df, write_options={"wait_for_job": True})
    return fg


   