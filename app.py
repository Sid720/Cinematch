import streamlit as st
import pickle
import pandas as pd
import requests
import math
import concurrent.futures
from PIL import Image
from io import BytesIO
import time
import json
import os
import bz2

WATCHLIST_FILE = "persistent_watchlist.json"

def load_watchlist():
    if os.path.exists(WATCHLIST_FILE):
        try:
            with open(WATCHLIST_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_watchlist(watchlist):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(watchlist, f)

@st.cache_data
def load_data():
    movies_dict = pickle.load(open('movie_dict.pkl', 'rb'))
    movies_df = pd.DataFrame(movies_dict)
    
    with bz2.BZ2File('similarity.pbz2', 'rb') as f:
        similarity_matrix = pickle.load(f)
        
    return movies_df, similarity_matrix

st.set_page_config(page_title="CineMatch", layout="wide", initial_sidebar_state="expanded")

movies, similarity = load_data()

def get_accent_color(poster_url):
    try:
        response = requests.get(poster_url, timeout=5)
        img = Image.open(BytesIO(response.content))
        img = img.resize((1, 1))
        color = img.getpixel((0, 0))
        return f'rgb({color[0]}, {color[1]}, {color[2]})'
    except:
        return "#ff4b1f"

def fetch_poster(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key=8265bd1679663a7ea12ac168da84d2e8"
    try:
        data = requests.get(url, timeout=5).json()
        path = data.get('poster_path')
        return "https://image.tmdb.org/t/p/w500/" + path if path else "https://via.placeholder.com/500x750?text=No+Poster"
    except:
        return "https://via.placeholder.com/500x750?text=No+Poster"

def get_movie_info(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key=8265bd1679663a7ea12ac168da84d2e8&append_to_response=videos"
    try:
        data = requests.get(url, timeout=5).json()
        trailer = next((f"https://www.youtube.com/watch?v={v['key']}" for v in data.get('videos', {}).get('results', []) if v['type'] == 'Trailer'), None)
        return data.get('overview', 'N/A'), data.get('vote_average', 0), data.get('release_date', 'N/A'), trailer
    except:
        return "Error", 0, "N/A", None

def get_match_reason(movie1_title, movie2_title):
    try:
        tags1 = set(movies[movies['title'] == movie1_title]['tags'].values[0].split())
        tags2 = set(movies[movies['title'] == movie2_title]['tags'].values[0].split())
        common = [w.capitalize() for w in list(tags1.intersection(tags2)) if len(w) > 3]
        return f"Matches on: {', '.join(common[:3])}" if common else "Similar thematic style"
    except:
        return "Recommended for you"

def fetch_all_posters(movie_ids):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        return list(executor.map(fetch_poster, movie_ids))

def recommend(movie_title):
    index = movies[movies['title'] == movie_title].index[0]
    distances = sorted(list(enumerate(similarity[index])), reverse=True, key=lambda x: x[1])
    top_matches = distances[1:101]
    
    rec_data = movies.iloc[[i[0] for i in top_matches]]
    names = rec_data['title'].tolist()
    ids = rec_data['movie_id'].tolist()
    scores = [int(i[1] * 100) for i in top_matches] 
    
    return names, fetch_all_posters(ids), scores


if 'selected_movie' not in st.session_state:
    st.session_state.selected_movie = movies['title'].iloc[0]
if 'watchlist' not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if 'items_to_show' not in st.session_state:
    st.session_state.items_to_show = 12

m_id_current = movies[movies['title'] == st.session_state.selected_movie].movie_id.values[0]
current_poster = fetch_poster(m_id_current)
dynamic_accent = get_accent_color(current_poster)


st.markdown(f"""
    <style>
    .stApp {{
        background: radial-gradient(circle at top right, {dynamic_accent}33, #0f0c29 60%), linear-gradient(135deg, #0f0c29, #24243e);
        font-family: 'Inter', sans-serif;
    }}
    div.stButton > button:first-child {{
        background: {dynamic_accent}; color: white; border: none; border-radius: 12px; font-weight: 700;
        box-shadow: 0 4px 15px {dynamic_accent}44; transition: 0.3s; width: 100%;
    }}
    div.stButton > button:hover {{ transform: translateY(-2px); filter: brightness(1.2); }}
    [data-testid="stSidebar"] {{ background-color: rgba(10, 10, 10, 0.8) !important; backdrop-filter: blur(10px); }}
    .match-tag {{ color: {dynamic_accent}; font-size: 11px; font-weight: bold; margin-bottom: 2px; }}
    </style>
    """, unsafe_allow_html=True)


with st.sidebar:
    st.title("📌 Watchlist")
    if st.session_state.watchlist:
        for m in st.session_state.watchlist:
            col_a, col_b = st.columns([4, 1])
            if col_a.button(f"🎬 {m}", key=f"wl_{m}"):
                st.session_state.selected_movie = m
                st.rerun()
            if col_b.button("❌", key=f"del_{m}"):
                st.session_state.watchlist.remove(m)
                save_watchlist(st.session_state.watchlist)
                st.rerun()
        
        watchlist_text = "\n".join(st.session_state.watchlist)
        st.download_button("📂 Export List", watchlist_text, file_name="watchlist.txt")
    else:
        st.caption("Your list is empty. Add movies you want to save!")
    
    st.write("---")
    st.header("Now Viewing")
    overview, rating, date, trailer = get_movie_info(m_id_current)
    st.image(current_poster, use_container_width=True)
    st.subheader(st.session_state.selected_movie)
    st.write(f"⭐ {rating:.1f}/10 | 📅 {date}")
    
    if st.button(" Add to Watchlist"):
        if st.session_state.selected_movie not in st.session_state.watchlist:
            st.session_state.watchlist.append(st.session_state.selected_movie)
            save_watchlist(st.session_state.watchlist)
            st.toast("Saved permanently!")
            st.rerun()
        else:
            st.warning("Already in watchlist!")
    
    st.info(overview)
    if trailer:
        st.link_button("📺 Watch Trailer", trailer)

st.title('🎬 CineMatch ')

choice = st.selectbox("Search for a movie:", movies['title'].values, index=list(movies['title'].values).index(st.session_state.selected_movie))
if choice != st.session_state.selected_movie:
    st.session_state.selected_movie = choice
    st.rerun()

if st.button('Discover Similar Movies'):
    ph = st.empty()
    bar = st.empty()
    p_bar = bar.progress(0)
    phrases = ["Searching...", "Matching genres...", "Analyzing themes...", "Loading results..."]
    for p in range(100):
        time.sleep(0.01)
        p_bar.progress(p + 1)
        ph.markdown(f"<p style='text-align:center;'><i>{phrases[min(p//25, 3)]}</i></p>", unsafe_allow_html=True)
    ph.empty()
    bar.empty()
    
    with st.spinner('Curating your list...'):
        st.session_state.rec_names, st.session_state.rec_posters, st.session_state.rec_scores = recommend(st.session_state.selected_movie)
        st.session_state.items_to_show = 12

# Recommendations display 
if st.session_state.get('rec_names'):
    names, posters, scores = st.session_state.rec_names, st.session_state.rec_posters, st.session_state.rec_scores
    limit = st.session_state.items_to_show
    
    def select_movie(title):
        st.session_state.selected_movie = title
        st.session_state.rec_names = []
        st.session_state.items_to_show = 12

    for i in range(0, limit, 4):
        cols = st.columns(4)
        for j, col in enumerate(cols):
            idx = i + j
            if idx < len(names):
                with col:
                    st.image(posters[idx], use_container_width=True)
                    reason = get_match_reason(st.session_state.selected_movie, names[idx])
                    st.markdown(f"<div class='match-tag'>{scores[idx]}% Match • {reason}</div>", unsafe_allow_html=True)
                    st.button(f"View: {names[idx]}", key=f"btn_{idx}", on_click=select_movie, args=(names[idx],))
    
    if limit < len(names):
        if st.button("🔽 Load More Recommendations", use_container_width=True):
            st.session_state.items_to_show += 12
            st.rerun()