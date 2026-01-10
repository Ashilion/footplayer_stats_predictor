import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.model_selection import train_test_split
from sklearn.metrics import root_mean_squared_error, r2_score
import os
import joblib
import hopsworks
from hsml.schema import Schema
from hsml.model_schema import ModelSchema
from dotenv import load_dotenv


# --- Configuration ---
POSITIONS = ['FW', 'MF', 'DF']
TARGET_COL = 'gls' # Raw goals in your new columns
TEAM_COL = 'team'
MATCH_COL = 'match_id'

def preprocess_targets(df):
    """Calculates goals scored per team per match."""
    match_goals = df.groupby([MATCH_COL, TEAM_COL])[TARGET_COL].sum().reset_index()
    match_goals.rename(columns={TARGET_COL: 'Goals_Scored'}, inplace=True)
    return match_goals

def create_match_features(df, positions):
    """Aggregates player rolling metrics by position and team."""
    rolling_cols = [col for col in df.columns if col.startswith('rolling_avg_')]
    numeric_rolling = df[rolling_cols].select_dtypes(include=[np.number]).columns.tolist()
    
    df_filtered = df[df['pos'].isin(positions)].copy()
    
    agg_features = []
    for pos in positions:
        pos_df = df_filtered[df_filtered['pos'] == pos]
        
        # 2. Group by and mean (numeric_only=True is a safety net)
        pos_agg = pos_df.groupby(['match_id', 'team'])[numeric_rolling].mean(numeric_only=True).reset_index()
        
        rename_dict = {col: f'{pos}_{col}' for col in numeric_rolling}
        pos_agg.rename(columns=rename_dict, inplace=True)
        agg_features.append(pos_agg)

    team_match_df = agg_features[0]
    for next_df in agg_features[1:]:
        team_match_df = pd.merge(team_match_df, next_df, on=['match_id', 'team'], how='outer')
        
    return team_match_df

def pivot_to_match_level(team_match_df):
    """Transforms team-level rows into a single row per match (Team A vs Team B)."""
    # Logic to split teams per match
    match_groups = team_match_df.groupby(MATCH_COL)
    
    rows = []
    for match_id, group in match_groups:
        if len(group) < 2: continue # Skip if only one team's data is available
        
        # Sort to ensure consistent TeamA/TeamB assignment
        group = group.sort_values(by=TEAM_COL)
        team_a_data = group.iloc[0].drop(TEAM_COL)
        team_b_data = group.iloc[1].drop(TEAM_COL)
        
        # Prefix columns
        team_a_data = team_a_data.add_prefix('TeamA_')
        team_b_data = team_b_data.add_prefix('TeamB_')
        
        # Combine
        combined = pd.concat([team_a_data, team_b_data])
        combined[MATCH_COL] = match_id
        rows.append(combined)
        
    match_df = pd.DataFrame(rows)
    if 'TeamA_Goals_Scored' in match_df.columns and 'TeamB_Goals_Scored' in match_df.columns:
        match_df['Total_Match_Goals'] = match_df['TeamA_Goals_Scored'] + match_df['TeamB_Goals_Scored']
    return match_df

def create_classification_target(df):
    # Calculate goal difference
    # TeamA_Goals_Scored - TeamB_Goals_Scored
    df['diff'] = df['TeamA_Goals_Scored'] - df['TeamB_Goals_Scored']
    
    # Define conditions
    conditions = [
        (df['diff'] > 0),  # Team A Wins
        (df['diff'] == 0), # Draw
        (df['diff'] < 0)   # Team B Wins
    ]
    choices = [0, 1, 2] # Classes
    
    df['Result'] = np.select(conditions, choices)
    return df

def add_difference_features(X):
    """Calculates the delta between Team A and Team B features, skipping strings."""

    numeric_X = X.select_dtypes(include=[np.number])
    team_a_cols = [col for col in numeric_X.columns if col.startswith('TeamA_')]
    
    for col in team_a_cols:
        team_b_col = col.replace('TeamA_', 'TeamB_')
        if team_b_col in X.columns:
            diff_col = col.replace('TeamA_', 'Diff_')
            # Perform subtraction only on the confirmed numeric pair
            X[diff_col] = X[col] - X[team_b_col]
    return X




def upload_model_to_hopsworks(model, X_train, y_train, metrics, project_name, model_name, version=1):
    """Saves the model locally, creates a schema, and uploads to Hopsworks Model Registry."""
    load_dotenv()
    api_key = os.getenv("HOPSWORKS_API_KEY")
    
    # 1. Login to Hopsworks
    project = hopsworks.login(
        project=project_name, 
        api_key_value=api_key,
        host="eu-west.cloud.hopsworks.ai"
    )
    
    # 2. Get Model Registry
    mr = project.get_model_registry()

    # 3. Save model locally first (temporary)
    model_dir = "football_model"
    if not os.path.exists(model_dir):
        os.mkdir(model_dir)
    
    # Save the model object
    joblib.dump(model, f"{model_dir}/model.pkl")

    # 4. Define Input/Output Schemas (Good practice for deployment)
    input_schema = Schema(X_train.values)
    output_schema = Schema(y_train.values)
    model_schema = ModelSchema(input_schema, output_schema)

    # 5. Create the Model in Registry
    hw_model = mr.python.create_model(
        name=model_name,
        version=version,
        metrics=metrics, # Pass your precision/RMSE dict here
        model_schema=model_schema,
        description="XGBoost MultiOutput Regressor for Team Goals"
    )

    # 6. Upload the directory
    hw_model.save(model_dir)
    
    print(f"Model {model_name} version {version} uploaded successfully.")
    return hw_model


def prepare_match_data(df, positions, target_cols):
    """
    Cleans, merges, and splits data into Features (X) and Targets (Y).
    """
    # 1. Feature & Target Generation
    goals_df = preprocess_targets(df)

    features_df = create_match_features(df, positions)
    # 2. Merge and Pivot
    combined_df = pd.merge(features_df, goals_df, on=[MATCH_COL, TEAM_COL], how='left')
    final_df = pivot_to_match_level(combined_df)
    
    # 3. Handle specific engineering (Differences, etc.)
    # We create 'Result' and 'diff' here if needed for specific logic, 
    # but they will be dropped from X later.
    if 'Result' not in final_df.columns and len(target_cols) > 0:
        final_df = create_classification_target(final_df)
    # 4. Define columns to exclude from Features
    leaky_cols = [
        'Total_Match_Goals', 'diff', 'Result',
        'TeamB_match_id', 'TeamA_match_id',
        'TeamB_FW_rolling_avg_player_number', 'TeamA_FW_rolling_avg_player_number',
        'TeamA_Goals_Scored', 'TeamB_Goals_Scored'
    ]
    # Add the targets to the drop list so X doesn't contain the answer
    cols_to_drop = list(set(leaky_cols + [MATCH_COL]))
    
    # 5. Split X and Y
    Y = final_df[target_cols]
    X = final_df.drop(columns=[c for c in cols_to_drop if c in final_df.columns])
    # 6. Final Cleaning
    X = add_difference_features(X)
    X = X.apply(pd.to_numeric, errors='coerce').fillna(0)
    
    return X, Y