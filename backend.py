import os
import joblib
import pandas as pd
import hopsworks
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pydantic import BaseModel
from typing import List

from training_utils import prepare_match_data 
from features_utils import add_rolling_features

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # These will be read from environment variables or .env file
    hopsworks_api_key: str
    hopsworks_project: str = "player_stat_prediction"
    
    # This tells Pydantic to look for a .env file
    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()

# --- Lifespan Manager ---
# This replaces @app.on_event("startup")
ml_models = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup Logic ---
    print("Connecting to Hopsworks...")
    project = hopsworks.login(
                    api_key_value=settings.hopsworks_api_key, 
                    project=settings.hopsworks_project,
                    host="eu-west.cloud.hopsworks.ai"
    )
    fs = project.get_feature_store()
    
    # Store connections in the lifespan state
    ml_models["fg"] = fs.get_feature_group(name="player_stats_rolling", version=1)
    
    # Load Model
    mr = project.get_model_registry()
    retrieved_model = mr.get_model("xgboost_goals_2teams", version=1)
    model_dir = retrieved_model.download()
    ml_models["model"] = joblib.load(os.path.join(model_dir, "model.pkl"))
    
    print("Model and Feature Store connection established.")
    
    yield
    
    # --- Shutdown Logic ---
    ml_models.clear()
    print("Cleaning up resources...")

app = FastAPI(title="Football Prediction API", lifespan=lifespan)

# Define the origins that are allowed to talk to your API
origins = [
    "http://localhost:5173",  # Your React/Vite dev server
    "http://127.0.0.1:5173",
    "http://localhost:3000",  # Common for Create-React-App
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,           # Allows specific origins
    allow_credentials=True,
    allow_methods=["*"],             # Allows all methods (GET, POST, etc.)
    allow_headers=["*"],             # Allows all headers
)

# --- Pydantic Schemas ---
class MatchRequest(BaseModel):
    team_a_players: List[str]
    team_b_players: List[str]

# --- Endpoints ---

@app.get("/players")
def list_players():
    """Fetches unique players with their last known team and position."""
    fg = ml_models["fg"]
    # We select name, team, and position
    # 'match_id' or 'age' helps us find the most recent record
    df = fg.select(["player", "team", "pos", "age"]).read()
    
    # Sort by age (or match_id) and drop duplicates to get the LATEST info per player
    latest_players = (df.sort_values("age", ascending=False)
                      .drop_duplicates(subset="player")
                      .rename(columns={"player": "name"}))
    
    return {"players": latest_players.to_dict(orient="records")}

@app.post("/predict")
async def predict(request: MatchRequest):
    fg = ml_models["fg"]
    model = ml_models["model"]
    fs = fg.feature_store

    all_players = request.team_a_players + request.team_b_players
    
    # 1. Fetch historical data for these players
    players_str = ", ".join([f"'{p}'" for p in all_players])
    sql_query = f"SELECT * FROM `{fg.name}_{fg.version}` WHERE player IN ({players_str})"

    # Use the feature store's sql method
    try:
        # This bypasses the HSFS filter logic that adds the 'u&'
        historical_df = fs.sql(sql_query)
    except Exception as e:
        print(f"Direct SQL failed, falling back to pandas filter: {e}")
        # ONLY do this as a last resort because it is slow!
        historical_df = fg.read()
        historical_df = historical_df[historical_df['player'].isin(all_players)]

    if historical_df.empty:
        raise HTTPException(status_code=404, detail="No historical data found for these players.")

    # 2. Prepare the "Upcoming Match" rows
    # We create a blank row for each player for the match we are about to predict
    upcoming_match_list = []
    for p in all_players:
        team = "TeamA" if p in request.team_a_players else "TeamB"
        player_data = historical_df[historical_df["player"] == p]
        
        if not player_data.empty:
            # Get the position from their most recent record
            player_pos = player_data["pos"].iloc[0]
        else:
            # Fallback if player history is missing (crucial for API stability)
            player_pos = "FW"

        upcoming_match_list.append({
            "player": p,
            "team": team,
            "match_id": "FUTURE_MATCH",
            "pos": player_pos,
            "age": "99:300"
        })

    upcoming_df = pd.DataFrame(upcoming_match_list)

    # 3. Combine History + Upcoming
    # We only keep the raw columns (not the old rolling ones) to recalculate fresh
    raw_cols = [c for c in historical_df.columns if not c.startswith('rolling_avg_')]
    combined_df = pd.concat([historical_df[raw_cols], upcoming_df], ignore_index=True)

    # 4. Run your existing rolling feature logic
    # This will calculate the average of the PREVIOUS matches and put it in the "FUTURE_MATCH" row
    
    enriched_df = add_rolling_features(combined_df, window_size=6)

    # 5. Extract only the row for the prediction
    inference_data = enriched_df[enriched_df['match_id'] == "FUTURE_MATCH"]

    # 6. Transform to TeamA vs TeamB format
    # Using your existing prepare_match_data/pivot logic
    X, _ = prepare_match_data(
        inference_data, 
        positions=['FW', 'MF', 'DF'], 
        target_cols=[]
    )
    #to match training
    X["match_id"] = "FUTURE_MATCH"
    #convert to numeric
    X = X.apply(pd.to_numeric, errors='coerce')

    if hasattr(model, 'estimators_'):
        expected_features = model.estimators_[0].get_booster().feature_names
    else:
        # Fallback for standard XGBoost models
        expected_features = model.get_booster().feature_names
    X = X[expected_features]

    # 7. Final Prediction
    prediction = model.predict(X)
    
    return {
        "team_a_expected_goals": int(round(float(prediction[0][0]))),
        "team_b_expected_goals": int(round(float(prediction[0][1])))
    }