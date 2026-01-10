import React, { useState, useEffect } from 'react';

const API_BASE_URL = "http://localhost:8000";

// Tactical positions on the pitch
const FORMATION_433 = {
  GK:  { top: '88%', left: '50%' },
  RB:  { top: '70%', left: '85%' },
  RCB: { top: '75%', left: '62%' },
  LCB: { top: '75%', left: '38%' },
  LB:  { top: '70%', left: '15%' },
  RCM: { top: '50%', left: '72%' },
  CDM: { top: '55%', left: '50%' },
  LCM: { top: '50%', left: '28%' },
  RW:  { top: '25%', left: '80%' },
  ST:  { top: '18%', left: '50%' },
  LW:  { top: '25%', left: '20%' },
};

const TEAM_A_DEFAULT = [
  "Alisson", "Virgil van Dijk", "Michael Carrick",
  "Damien Delaney", "Andrew Robertson", "Alexis Mac Allister",
  "Dominik Szoboszlai", "Ryan Gravenberch", "Mohamed Salah",
  "Luis Díaz", "Darwin Núñez"
];

const TEAM_B_DEFAULT = [
  "Ederson", "Malo Gusto", "Manuel Akanji",
  "Kyle Walker", "Josko Gvardiol", "Rodri",
  "Kevin De Bruyne", "Bernardo Silva", "Phil Foden",
  "Jeremy Doku", "Erling Haaland"
];

const FORMATION_ORDER = [
  "GK", "RB", "RCB", "LCB", "LB",
  "RCM", "CDM", "LCM",
  "RW", "ST", "LW"
];

const App = () => {
  const [playersDb, setPlayersDb] = useState([]);
  const [lineups, setLineups] = useState({ teamA: {}, teamB: {} });
  const [activeSlot, setActiveSlot] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [prediction, setPrediction] = useState(null);
  const [loading, setLoading] = useState(false);

  // 1. Load Players from API
  useEffect(() => {
    fetch(`${API_BASE_URL}/players`)
      .then(res => res.json())
      .then(data =>{
        console.log("Players loaded:", data.players);
        setPlayersDb(data.players);
      })
      .catch(err => console.error("Connection to API failed:", err));
  }, []);

  const selectPlayer = (player) => {
    if (!activeSlot) return;
    setLineups(prev => ({
      ...prev,
      [activeSlot.team]: { ...prev[activeSlot.team], [activeSlot.pos]: player }
    }));
    setActiveSlot(null);
    setSearchTerm("");
  };

  const handlePredict = async () => {
    const teamA = Object.values(lineups.teamA).map(p => p.name);
    const teamB = Object.values(lineups.teamB).map(p => p.name);

    if (teamA.length < 11 || teamB.length < 11) {
      alert("Both teams must have 11 players selected!");
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ team_a_players: teamA, team_b_players: teamB }),
      });
      const result = await response.json();
      setPrediction(result);
    } catch (error) {
      alert("Failed to reach prediction engine.");
    } finally {
      setLoading(false);
    }
  };

  const filteredPlayers = playersDb.filter(p => 
    p.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    p.team.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const getLogoUrl = (teamName) => {
    if (!teamName) return "/logos/default.png";
    
    // Convert "Manchester City" to "manchester-city"
    const fileName = teamName.toLowerCase().replace(/\s+/g, '-');
    return `/logos/${fileName}.football-logos.cc.svg`;
  };

  const fillTeamWithDefaults = (teamKey, defaultNames) => {
    const filledTeam = {};

    FORMATION_ORDER.forEach((pos, index) => {
      const playerName = defaultNames[index];
      const playerObj = playersDb.find(p => p.name === playerName);

      if (playerObj) {
        filledTeam[pos] = playerObj;
      }
    });

    setLineups(prev => ({
      ...prev,
      [teamKey]: filledTeam
    }));
  };

  const Pitch = ({ teamId, title, color, sideColor }) => (
    <div className="flex-1 flex flex-col items-center">
      <div className={`px-8 py-2 rounded-t-2xl font-black uppercase tracking-widest ${sideColor} text-white shadow-lg`}>
        {title}
      </div>
      <div className="relative w-full h-[600px] bg-emerald-800 rounded-3xl border-[8px] border-white/10 shadow-2xl overflow-hidden ring-4 ring-black/20">
        {/* Grass Pattern */}
        <div className="absolute inset-0 opacity-10 pointer-events-none" 
             style={{ backgroundImage: 'repeating-linear-gradient(180deg, transparent, transparent 50px, rgba(0,0,0,0.2) 50px, rgba(0,0,0,0.2) 100px)' }}>
        </div>
        
        {/* Pitch Markings */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-48 h-20 border-2 border-white/20 border-t-0"></div>
        <div className="absolute bottom-0 left-1/2 -translate-x-1/2 w-48 h-20 border-2 border-white/20 border-b-0"></div>

        {Object.keys(FORMATION_433).map((pos) => {
          const player = lineups[teamId][pos];
          return (
            <div 
              key={pos}
              style={{ 
                position: 'absolute', top: FORMATION_433[pos].top, left: FORMATION_433[pos].left,
                transform: 'translate(-50%, -50%)'
              }}
              onClick={() => setActiveSlot({ team: teamId, pos })}
              className="flex flex-col items-center cursor-pointer transition-all hover:scale-110 active:scale-95 z-10"
            >
              <div className={`w-14 h-14 rounded-full border-2 flex items-center justify-center shadow-xl transition-colors ${
                player ? `${color} border-yellow-400` : 'bg-gray-900/60 border-white/30 backdrop-blur-md'
              }`}>
                <span className="text-xs font-black uppercase tracking-tighter">
                  {player ? player.name.split(' ').pop().substring(0, 3) : pos}
                </span>
              </div>
              <div className="mt-2 bg-black/80 backdrop-blur-md px-3 py-1 rounded-full border border-white/10 text-[10px] font-bold min-w-[70px] text-center shadow-lg">
                {player ? player.name : <span className="text-gray-500">+ ADD</span>}
                
              </div>

            </div>
          );
        })}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-[#0f172a] text-slate-100 p-8 font-sans">
      <header className="max-w-7xl mx-auto mb-12 flex justify-between items-end">
        <div>
          <h1 className="text-5xl font-black italic tracking-tighter text-transparent bg-clip-text bg-gradient-to-r from-yellow-400 to-orange-500">
            STRAT-X PREDICT
          </h1>
          <div className='flex items-center gap-2'>

          
          <p className="text-slate-400 font-medium">AI-Driven Match Outcome Simulator</p>
          <button
            onClick={() => fillTeamWithDefaults("teamA", TEAM_A_DEFAULT)}
            className="px-6 py-3 rounded-xl bg-blue-600 hover:bg-blue-500 font-bold"
          >
            Fill Home Team
          </button>

          <button
            onClick={() => fillTeamWithDefaults("teamB", TEAM_B_DEFAULT)}
            className="px-6 py-3 rounded-xl bg-red-600 hover:bg-red-500 font-bold"
          >
            Fill Away Team
          </button>
          </div>
        </div>
        {prediction && (
          <div className="bg-white/5 border border-white/10 px-8 py-4 rounded-2xl flex gap-12 backdrop-blur-xl animate-in fade-in zoom-in duration-500">
            <div className="text-center">
              <p className="text-xs text-slate-400 uppercase font-bold mb-1">Home xG</p>
              <p className="text-4xl font-black text-blue-400">{prediction.team_a_expected_goals}</p>
            </div>
            <div className="flex items-center text-2xl font-black text-slate-600">VS</div>
            <div className="text-center">
              <p className="text-xs text-slate-400 uppercase font-bold mb-1">Away xG</p>
              <p className="text-4xl font-black text-red-400">{prediction.team_b_expected_goals}</p>
            </div>
          </div>
        )}
      </header>
      <div className="flex gap-4 mb-8">
      
    </div>

      <main className="max-w-7xl mx-auto flex gap-12">
        <Pitch teamId="teamA" title="Home Lineup" color="bg-blue-600" sideColor="bg-blue-700" />
        <Pitch teamId="teamB" title="Away Lineup" color="bg-red-600" sideColor="bg-red-700" />
      </main>

      {/* MODAL: PLAYER SELECTION */}
      {activeSlot && (
        <div className="fixed inset-0 bg-black/90 backdrop-blur-sm flex items-center justify-center z-50 p-6">
          <div className="bg-slate-800 border border-slate-700 p-8 rounded-[2rem] w-full max-w-lg max-h-[80vh] flex flex-col shadow-2xl">
            <div className="flex justify-between items-start mb-6">
              <div>
                <h3 className="text-2xl font-black uppercase text-yellow-500 tracking-tight">Select {activeSlot.pos}</h3>
                <p className="text-slate-400 text-sm">Pick a player from your historical data</p>
              </div>
              <button onClick={() => setActiveSlot(null)} className="p-2 hover:bg-slate-700 rounded-full transition-colors text-2xl">✕</button>
            </div>

            <div className="relative mb-6">
              <input 
                type="text"
                placeholder="Search player or team..."
                className="w-full bg-slate-900 border border-slate-700 rounded-2xl py-4 px-6 text-white focus:outline-none focus:ring-2 focus:ring-yellow-500/50 transition-all"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                autoFocus
              />
            </div>

            <div className="space-y-3 overflow-y-auto pr-2 custom-scrollbar">
              {filteredPlayers.map(player => (
                <button
                  key={player.name}
                  onClick={() => selectPlayer(player)}
                  className="w-full text-left p-4 rounded-2xl bg-slate-700/30 hover:bg-slate-700 border border-transparent hover:border-yellow-500/50 transition-all flex justify-between items-center group"
                >
                  <div>
                    <div className="font-bold text-lg group-hover:text-yellow-400 transition-colors flex  items-center">
                      {player.name}
                      <img 
                        src={getLogoUrl(player.team)} 
                        alt="" 
                        className="w-8 h-8 object-contain rounded-md p-1 ml-2"
                        onError={(e) => e.target.style.display = 'none'} // Hide if logo not found
                      />
                    </div>
                    <div className="text-xs text-slate-400 font-bold uppercase tracking-widest flex  items-center">
                      
                      {player.team}
                    
                    </div>
                    
                  </div>
                  <div className="flex flex-col items-end">
                    <span className="text-xs font-black bg-slate-900 px-3 py-1 rounded-lg text-yellow-500 border border-white/5">
                      {player.pos}
                    </span>
                    <span className="text-[10px] text-slate-500 mt-1 italic">Age: {player.age}</span>
                  </div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      <div className="fixed bottom-12 left-1/2 -translate-x-1/2 z-40">
        <button 
          onClick={handlePredict}
          disabled={loading}
          className="group relative bg-yellow-500 text-black px-16 py-6 rounded-full font-black text-2xl hover:bg-yellow-400 active:scale-95 disabled:grayscale disabled:cursor-not-allowed transition-all shadow-[0_0_40px_rgba(234,179,8,0.3)]"
        >
          {loading ? (
            <span className="flex items-center gap-3">
              <svg className="animate-spin h-6 w-6 text-black" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
              RUNNING AI...
            </span>
          ) : "PREDICT OUTCOME"}
        </button>
      </div>
    </div>
  );
};

export default App;