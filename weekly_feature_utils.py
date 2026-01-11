import pandas as pd
import time
import hopsworks
import os
from datetime import date
from dotenv import load_dotenv
import re
from features_utils import clean_and_format_columns, add_rolling_features
import utils
# --- SCRAPING FUNCTIONS ---

# Load your team list
loaded_teams = utils.load_teams_from_json("teams.json")
# Create a list of team names ordered by length (descending) 
# This ensures "Manchester United" matches before "Manchester"
TEAM_MAP = {t['name']: t['name'].replace('-', ' ') for t in loaded_teams}
TEAM_SLUGS = sorted(TEAM_MAP.keys(), key=len, reverse=True)

def format_url_to_hopsworks_id(url):
    """
    Correctly parses the URL slug into: Home Team_Away Team_Month Day, Year
    Example URL: /en/matches/94eefc1d/Fulham-Arsenal-October-18-2025-Premier-League
    """
    slug = url.split('/')[-1]

    # 1. Extract the Date using Regex
    # This looks for: Month (Letters) - Day (Digits) - Year (4 Digits)
    date_match = re.search(r'([A-Za-z]+)-(\d{1,2})-(\d{4})', slug)
    if not date_match:
        return slug # Fallback if no date found
    
    month, day, year = date_match.groups()
    formatted_date = f"{month} {day}, {year}"

    # 2. Extract Teams
    # We remove the date and league suffix to isolate the team part of the slug
    # Example: 'Fulham-Arsenal-October-18-2025-Premier-League' -> 'Fulham-Arsenal'
    teams_part = slug.split(month)[0].strip('-')
    
    found_teams = []
    # Loop through our known slugs to find which two are in this part of the URL
    for team_slug in TEAM_SLUGS:
        if team_slug in teams_part:
            # Check if it's the Home or Away team based on position
            pos = teams_part.find(team_slug)
            found_teams.append((pos, TEAM_MAP[team_slug]))
            # Mask the found team so we don't find it twice (e.g. 'Arsenal-Arsenal')
            teams_part = teams_part.replace(team_slug, "X" * len(team_slug), 1)
            
        if len(found_teams) == 2:
            break

    # Sort by position to ensure [Home, Away] order
    found_teams.sort()
    
    if len(found_teams) == 2:
        home_team = found_teams[0][1]
        away_team = found_teams[1][1]
        return f"{home_team}_{away_team}_{formatted_date}"
    
    return slug # Fallback

def get_current_season():
    today = date.today()
    return f"{today.year-1}-{today.year}" if today.month < 8 else f"{today.year}-{today.year+1}"






def upload_to_hopsworks(df, project_name="your_project", fg_name="player_stats"):
    load_dotenv()
    project = hopsworks.login(project=project_name, api_key_value=os.getenv("HOPSWORKS_API_KEY"))
    fs = project.get_feature_store()
    
    fg = fs.get_or_create_feature_group(
        name=fg_name,
        version=1,
        primary_key=["player", "match_id"],
        online_enabled=True
    )
    # Use insert() to append new data to the existing Feature Group
    fg.insert(df, write_options={"wait_for_job": True})

def get_hopsworks_data(project_name, fg_name, version=1):
    """Downloads existing data from Hopsworks Feature Group."""
    load_dotenv()
    project = hopsworks.login(
        project=project_name, 
        api_key_value=os.getenv("HOPSWORKS_API_KEY"),
        host="eu-west.cloud.hopsworks.ai"
        )
    fs = project.get_feature_store()
    
    try:
        fg = fs.get_feature_group(name=fg_name, version=version)
        # Read the entire feature group as a DataFrame
        return fg.read(), fg
    except Exception as e:
        print(f"Could not read Feature Group: {e}")
        return pd.DataFrame(), None

def extract_match_id_from_url(url):
    """
    Extracts the last part of the URL as the ID.
    Example: '/en/matches/94eefc1d/Fulham-Arsenal-October-18-2025-Premier-League' 
    Returns: 'Fulham-Arsenal-October-18-2025-Premier-League'
    """
    return url.split('/')[-1]


