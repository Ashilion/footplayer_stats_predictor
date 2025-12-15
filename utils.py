import pandas as pd
import requests
from bs4 import BeautifulSoup
import json

"""------------------- Custom Headers and Table Attributes ------------------------------"""

custom_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://fbref.com/en/matches/01d155b4/Southampton-Arsenal-May-25-2025-Premier-League", # The URL itself
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Cache-Control": "max-age=0",
    # Modern browser headers
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1"
}

table_attrs = {"class": "stats_table"}

"""------------------- Team Match Logs Extraction Function -----------------------------------"""

def get_team_match_logs(team_code, team_name, season="2024-2025"):
    url = f"https://fbref.com/en/squads/{team_code}/{season}/matchlogs/all_comps/schedule/{team_name}-Scores-and-Fixtures-All-Competitions"

    try:
        response = requests.get(url, headers=custom_headers)
        response.raise_for_status() 
        print("Request successful, parsing HTML...")
        soup = BeautifulSoup(response.content, 'html.parser')
        table = soup.find('table', attrs=table_attrs)
    
        if table:
            rows = []
            for tr in table.find_all('tr')[1:]:
                cells = tr.find_all(['td', 'th'])
                row_data = {}
                for i, cell in enumerate(cells):
                    if i == 0:
                        text = cell.get_text(strip=True)
                        link = cell.find('a')
                        link_href = link['href'] if link else None
                        
                    
                        row_data[f'date'] = text
                        row_data[f'match_link'] = link_href

                if row_data:
                    rows.append(row_data)

            df = pd.DataFrame(rows)
            print("Table with links extracted:")
            return df
        else:
            print("Table not found in the HTML content.")
    except requests.exceptions.HTTPError as e:
        print(f"HTTP Error occurred: {e}. The server is still blocking the request.")
    except Exception as e:
        print(f"An error occurred: {e}")


def stat_player_match(url):
    if 'fbref.com' not in url:
        url = f"https://fbref.com{url}"
    response = requests.get(url, headers=custom_headers)
    response.raise_for_status() 
    print("Request successful, parsing HTML...")
    soup = BeautifulSoup(response.content, 'html.parser')
    stat_containers = soup.find_all('div', id=lambda x: x and x.startswith('all_player_stats'))

    dfs = []

    for i, container in enumerate(stat_containers):
        table = container.find('table', class_='stats_table')
        
        if table:
            try:
                df = pd.read_html(str(table))[0]
                df = table_transformation(df)
                dfs.append(df)
                print(f"✅ DataFrame pour team number {i+1} extrait et nettoyé.")
                print(df.head())
                print("---")
            except Exception as e:
                print(f"Erreur lors de l'extraction ou du nettoyage du tableau {i+1} : {e}")
        else:
            print(f"Aucune table 'stats_table' trouvée dans le conteneur {i+1}.")

    return dfs[0] if len(dfs) > 0 else None, dfs[1] if len(dfs) > 1 else None


def get_all_season_match(season="2024-2025"):
    #only premier league for now 
    set_match = set()
    #TODO : get the appropriate teams.json based on season
    teams = load_teams_from_json("teams.json")
    for team in teams:
        df_team_matches = get_team_match_logs(team['code'], team['name'], season=season)
        if df_team_matches is not None:
            for link in df_team_matches['match_link'].dropna().unique():
                set_match.add(link)
    return list(set_match)
    

"""------------------- DataFrame Transformation Function --------------------------------"""
    
def table_transformation(df):
    df_transformed = df.copy()
    
    # 1. Create new column names by merging the two levels
    new_columns = []
    for col in df_transformed.columns:
        if 'Unnamed' in col[0]:
            new_columns.append(col[1])
        else:
            new_columns.append(f"{col[0]}_{col[1]}")
    
    
    df_transformed.columns = new_columns    
    df_transformed.columns = df_transformed.columns.str.replace(' ', '_').str.replace('%', 'Pct')
    
    return df_transformed

def load_teams_from_json(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        loaded_teams = json.load(f)
    print("Loaded teams from JSON:", loaded_teams)
    return loaded_teams