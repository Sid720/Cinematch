import streamlit as st
import pickle
import pandas as pd
import requests
import concurrent.futures
from PIL import Image
from io import BytesIO
import time
import json
import os
import bz2
import re
from difflib import SequenceMatcher

WATCHLIST_FILE = "persistent_watchlist.json"
TMDB_API_KEY = "8265bd1679663a7ea12ac168da84d2e8"


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
    movies_dict = pickle.load(open("movie_dict.pkl", "rb"))
    movies_df = pd.DataFrame(movies_dict)

    with bz2.BZ2File("similarity.pbz2", "rb") as f:
        similarity_matrix = pickle.load(f)

    return movies_df, similarity_matrix


@st.cache_data(show_spinner=False)
def fetch_movie_tmdb_data(movie_id):
    url = f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={TMDB_API_KEY}&append_to_response=videos,credits"
    try:
        response = requests.get(url, timeout=8)
        return response.json()
    except:
        return {}


@st.cache_data(show_spinner=False)
def fetch_poster(movie_id):
    try:
        data = fetch_movie_tmdb_data(movie_id)
        poster_path = data.get("poster_path")
        if poster_path:
            return "https://image.tmdb.org/t/p/w500/" + poster_path
        return "https://via.placeholder.com/500x750?text=No+Poster"
    except:
        return "https://via.placeholder.com/500x750?text=No+Poster"


@st.cache_data(show_spinner=False)
def fetch_backdrop(movie_id):
    try:
        data = fetch_movie_tmdb_data(movie_id)
        backdrop_path = data.get("backdrop_path")
        if backdrop_path:
            return "https://image.tmdb.org/t/p/original/" + backdrop_path
        return fetch_poster(movie_id)
    except:
        return fetch_poster(movie_id)


@st.cache_data(show_spinner=False)
def get_movie_info(movie_id):
    try:
        data = fetch_movie_tmdb_data(movie_id)

        trailer = next(
            (
                f"https://www.youtube.com/watch?v={video['key']}"
                for video in data.get("videos", {}).get("results", [])
                if video.get("type") == "Trailer" and video.get("site") == "YouTube"
            ),
            None
        )

        genres = [genre.get("name", "") for genre in data.get("genres", []) if genre.get("name")]
        runtime = int(data.get("runtime", 0) or 0)
        countries = [country.get("name", "") for country in data.get("production_countries", []) if country.get("name")]
        languages = [language.get("english_name", "") for language in data.get("spoken_languages", []) if language.get("english_name")]
        cast_list = [person.get("name", "") for person in data.get("credits", {}).get("cast", [])[:4] if person.get("name")]
        crew = data.get("credits", {}).get("crew", [])

        director = next((person.get("name") for person in crew if person.get("job") == "Director"), "N/A")
        writers = [person.get("name", "") for person in crew if person.get("job") in ["Writer", "Screenplay", "Story"]][:3]

        return {
            "overview": data.get("overview", "No overview available."),
            "rating": float(data.get("vote_average", 0) or 0),
            "date": data.get("release_date", "N/A"),
            "trailer": trailer,
            "genres": genres,
            "genres_text": ", ".join(genres) if genres else "N/A",
            "runtime": runtime,
            "countries": countries,
            "countries_text": ", ".join(countries[:3]) if countries else "N/A",
            "languages": languages,
            "languages_text": ", ".join(languages[:3]) if languages else "N/A",
            "cast": cast_list,
            "cast_text": ", ".join(cast_list) if cast_list else "N/A",
            "director": director,
            "writers": writers,
            "writers_text": ", ".join(writers) if writers else "N/A",
            "tagline": data.get("tagline", ""),
            "status": data.get("status", "Released"),
            "popularity": round(float(data.get("popularity", 0) or 0), 1)
        }
    except:
        return {
            "overview": "No overview available.",
            "rating": 0.0,
            "date": "N/A",
            "trailer": None,
            "genres": [],
            "genres_text": "N/A",
            "runtime": 0,
            "countries": [],
            "countries_text": "N/A",
            "languages": [],
            "languages_text": "N/A",
            "cast": [],
            "cast_text": "N/A",
            "director": "N/A",
            "writers": [],
            "writers_text": "N/A",
            "tagline": "",
            "status": "N/A",
            "popularity": 0.0
        }


def normalize_text(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def get_movie_id_from_title(title):
    try:
        return int(movies[movies["title"] == title].movie_id.values[0])
    except:
        return int(movies["movie_id"].iloc[0])


def extract_year_from_date(date_value):
    if not date_value or str(date_value) == "N/A":
        return "N/A"
    return str(date_value)[:4]


def estimate_quality(rating):
    if rating >= 7.5:
        return "HD"
    if rating >= 6:
        return "WEB-DL"
    return "CAM"


def get_match_reason(movie1_title, movie2_title):
    try:
        tags1 = set(movies[movies["title"] == movie1_title]["tags"].values[0].split())
        tags2 = set(movies[movies["title"] == movie2_title]["tags"].values[0].split())
        common = [word.capitalize() for word in list(tags1.intersection(tags2)) if len(word) > 3]
        return f"Matches on: {', '.join(common[:2])}" if common else "Similar thematic style"
    except:
        return "Recommended for you"


def fetch_all_posters(movie_ids):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        return list(executor.map(fetch_poster, movie_ids))


def recommend(movie_title):
    index = movies[movies["title"] == movie_title].index[0]
    distances = sorted(list(enumerate(similarity[index])), reverse=True, key=lambda x: x[1])
    top_matches = distances[1:101]

    rec_data = movies.iloc[[i[0] for i in top_matches]]
    names = rec_data["title"].tolist()
    ids = rec_data["movie_id"].tolist()
    scores = [int(i[1] * 100) for i in top_matches]

    return names, fetch_all_posters(ids), scores


def search_movies(query):
    if not query.strip():
        return []

    query_clean = normalize_text(query)
    titles = movies["title"].tolist()

    exact_matches = [title for title in titles if normalize_text(title) == query_clean]
    starts_with_matches = [title for title in titles if normalize_text(title).startswith(query_clean) and title not in exact_matches]
    partial_matches = [title for title in titles if query_clean in normalize_text(title) and title not in exact_matches and title not in starts_with_matches]

    fuzzy_matches = []
    if not exact_matches and not starts_with_matches:
        scored = []
        for title in titles:
            ratio = SequenceMatcher(None, query_clean, normalize_text(title)).ratio()
            if ratio > 0.45:
                scored.append((title, ratio))
        scored = sorted(scored, key=lambda x: x[1], reverse=True)
        fuzzy_matches = [item[0] for item in scored[:8]]

    final_results = exact_matches + starts_with_matches + partial_matches[:8] + fuzzy_matches
    final_results = list(dict.fromkeys(final_results))
    return final_results[:8]


def set_selected_movie(title):
    st.session_state.selected_movie = title
    st.session_state.search_query = title
    st.session_state.search_results = [title]
    st.session_state.items_to_show = 12


def get_genre_tag_list():
    return [
        "Action", "Adventure", "Comedy", "Drama",
        "Fantasy", "Thriller", "Sci-Fi", "Romance",
        "Animation", "Crime", "Family", "Mystery"
    ]


def match_year_bucket(date_value, bucket):
    year_text = extract_year_from_date(date_value)
    if not year_text.isdigit():
        return False

    year_num = int(year_text)

    if bucket == "2020s":
        return 2020 <= year_num <= 2029
    if bucket == "2010s":
        return 2010 <= year_num <= 2019
    if bucket == "2000s":
        return 2000 <= year_num <= 2009
    if bucket == "1990s":
        return 1990 <= year_num <= 1999
    if bucket == "1980s":
        return 1980 <= year_num <= 1989

    return False


st.set_page_config(page_title="CineMatch", layout="wide")

movies, similarity = load_data()

if "selected_movie" not in st.session_state:
    st.session_state.selected_movie = movies["title"].iloc[0]
if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()
if "items_to_show" not in st.session_state:
    st.session_state.items_to_show = 12
if "search_query" not in st.session_state:
    st.session_state.search_query = ""
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "rec_names" not in st.session_state:
    st.session_state.rec_names = []
if "rec_posters" not in st.session_state:
    st.session_state.rec_posters = []
if "rec_scores" not in st.session_state:
    st.session_state.rec_scores = []
if "genre_filter" not in st.session_state:
    st.session_state.genre_filter = "All"
if "language_filter" not in st.session_state:
    st.session_state.language_filter = "All"
if "year_filter" not in st.session_state:
    st.session_state.year_filter = "All"
if "browse_mode" not in st.session_state:
    st.session_state.browse_mode = "All"
if "sort_by" not in st.session_state:
    st.session_state.sort_by = "Similarity"
if "sort_order" not in st.session_state:
    st.session_state.sort_order = "Descending"

m_id_current = get_movie_id_from_title(st.session_state.selected_movie)
current_poster = fetch_poster(m_id_current)
current_backdrop = fetch_backdrop(m_id_current)
current_info = get_movie_info(m_id_current)

st.markdown(
    f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700;800&display=swap');

    #MainMenu {{
        visibility: hidden;
    }}

    header {{
        visibility: hidden;
        height: 0px;
    }}

    footer {{
        visibility: hidden;
    }}

    [data-testid="stToolbar"] {{
        display: none !important;
    }}

    [data-testid="stDecoration"] {{
        display: none !important;
    }}

    [data-testid="collapsedControl"] {{
        display: none !important;
    }}

    [data-testid="stStatusWidget"] {{
        display: none !important;
    }}

    .stAppDeployButton {{
        display: none !important;
    }}

    html, body, [class*="css"] {{
        font-family: 'Outfit', sans-serif;
    }}

    .stApp {{
        background:
            linear-gradient(rgba(7, 11, 18, 0.90), rgba(7, 11, 18, 0.96)),
            url('{current_backdrop}');
        background-size: cover;
        background-position: center top;
        background-attachment: fixed;
    }}

    .block-container {{
        max-width: 1320px !important;
        padding-top: 2rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        padding-bottom: 1rem !important;
    }}

    .title-main {{
        color: #f8fafc;
        font-size: 1.85rem;
        font-weight: 800;
        line-height: 1;
        margin-bottom: 0.15rem;
    }}

    .title-sub {{
        color: #9eb0c2;
        font-size: 0.92rem;
        margin-bottom: 0;
    }}

    .hero-title {{
        color: white;
        font-size: 2.2rem;
        font-weight: 800;
        line-height: 1.05;
        margin-bottom: 0.35rem;
    }}

    .hero-sub {{
        color: #e9d8df;
        font-size: 0.96rem;
        margin-bottom: 0.75rem;
    }}

    .crumb {{
        display: inline-block;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(255,255,255,0.08);
        color: #dbe5ef;
        font-size: 0.82rem;
        margin-bottom: 0.7rem;
    }}

    .pill {{
        display: inline-block;
        padding: 6px 10px;
        border-radius: 999px;
        background: rgba(255,255,255,0.08);
        color: white;
        font-size: 0.81rem;
        font-weight: 600;
        margin-right: 7px;
        margin-bottom: 7px;
    }}

    .overview-box {{
        background: rgba(255,255,255,0.05);
        color: #dae4ee;
        border-radius: 14px;
        padding: 14px;
        line-height: 1.58;
        font-size: 0.94rem;
    }}

    .metric-box {{
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 14px;
        padding: 12px;
        text-align: center;
        min-height: 84px;
    }}

    .metric-label {{
        color: #9eb0c2;
        font-size: 0.72rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 700;
        margin-bottom: 6px;
    }}

    .metric-value {{
        color: #f8fafc;
        font-size: 0.95rem;
        font-weight: 700;
        line-height: 1.35;
    }}

    .small-title {{
        color: #f8fafc;
        font-size: 1rem;
        font-weight: 800;
        margin-bottom: 0.65rem;
    }}

    .search-result {{
        background: rgba(255,255,255,0.05);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 10px 12px;
        color: #f8fafc;
    }}

    .match-tag {{
        display: inline-block;
        padding: 5px 9px;
        border-radius: 999px;
        background: linear-gradient(135deg, #ff8a65, #ff6b57);
        color: white;
        font-size: 10px;
        font-weight: 700;
        margin-top: 7px;
        margin-bottom: 7px;
    }}

    .note-text {{
        color: #9eb0c2;
        font-size: 0.9rem;
    }}

    .footer-note {{
        text-align: center;
        color: #9eb0c2;
        margin-top: 10px;
        font-size: 0.88rem;
    }}

    div.stButton > button:first-child {{
        width: 100%;
        border-radius: 10px;
        border: none;
        background: linear-gradient(135deg, #ff8a65, #ff6b57);
        color: white;
        font-weight: 700;
        padding: 0.62rem 0.85rem;
        font-size: 0.9rem;
    }}

    div[data-baseweb="input"] > div,
    div[data-baseweb="select"] > div {{
        border-radius: 12px !important;
        border: 1px solid rgba(255,255,255,0.08) !important;
        background: rgba(255,255,255,0.05) !important;
    }}

    .stTextInput label, .stSelectbox label {{
        color: #f8fafc !important;
        font-weight: 700 !important;
    }}

    .stTextInput input {{
        color: #f8fafc !important;
    }}
    </style>
    """,
    unsafe_allow_html=True,
)

header_left, header_right = st.columns([6, 1], gap="medium")

with header_left:
    st.markdown('<div class="title-main">CineMatch</div>', unsafe_allow_html=True)
    st.markdown('<div class="title-sub">Find your next favorite movie instantly</div>', unsafe_allow_html=True)

with header_right:
    st.empty()

st.write("")

search_left, search_right = st.columns([5, 1], gap="medium")

with search_left:
    st.markdown("##### Search for Any Movie Title")
    search_value = st.text_input(
        "",
        value=st.session_state.search_query,
        placeholder="Type a movie name like Avatar, Batman, Interstellar...",
        label_visibility="collapsed"
    )

with search_right:
    st.markdown("##### &nbsp;", unsafe_allow_html=True)
    search_clicked = st.button("Search", use_container_width=True)

if search_value != st.session_state.search_query:
    st.session_state.search_query = search_value
    st.session_state.search_results = search_movies(search_value) if search_value.strip() else []

if search_clicked:
    matched_titles = search_movies(search_value)
    st.session_state.search_results = matched_titles
    if matched_titles:
        set_selected_movie(matched_titles[0])
        st.rerun()
    else:
        st.warning("No matching movie found in your dataset.")

if st.session_state.search_results and st.session_state.search_query.strip():
    st.markdown('<div class="note-text">Matching Results</div>', unsafe_allow_html=True)
    for idx, movie_name in enumerate(st.session_state.search_results[:4]):
        row_cols = st.columns([5, 1], gap="medium")
        with row_cols[0]:
            st.markdown(f'<div class="search-result">{movie_name}</div>', unsafe_allow_html=True)
        with row_cols[1]:
            if st.button("Open", key=f"search_{idx}", use_container_width=True):
                set_selected_movie(movie_name)
                st.rerun()

st.write("")

main_left, main_right = st.columns([4.5, 1.2], gap="large")

with main_left:
    hero_cols = st.columns([1.02, 1.9], gap="large")

    with hero_cols[0]:
        st.image(current_poster, use_container_width=True)

    with hero_cols[1]:
        st.markdown(f'<div class="crumb">Home / Movie / {st.session_state.selected_movie}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="hero-title">{st.session_state.selected_movie}</div>', unsafe_allow_html=True)

        if current_info["tagline"]:
            st.markdown(f'<div class="hero-sub">{current_info["tagline"]}</div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="hero-sub">Curated details for your selected movie.</div>', unsafe_allow_html=True)

        st.markdown(
            f"""
            <span class="pill">⭐ {current_info['rating']:.1f}/10</span>
            <span class="pill">📅 {current_info['date']}</span>
            <span class="pill">🎞 {estimate_quality(current_info['rating'])}</span>
            <span class="pill">⏱ {current_info['runtime']} min</span>
            <span class="pill">📌 {current_info['status']}</span>
            """,
            unsafe_allow_html=True
        )

        st.markdown(f'<div class="overview-box">{current_info["overview"]}</div>', unsafe_allow_html=True)

    st.write("")

    action_cols = st.columns([1.1, 1.1, 1.1, 1.5], gap="medium")

    with action_cols[0]:
        if st.button("Discover Similar", use_container_width=True):
            ph = st.empty()
            progress_holder = st.empty()
            progress_bar = progress_holder.progress(0)
            phrases = ["Searching...", "Matching genres...", "Analyzing themes...", "Loading results..."]

            for p in range(100):
                time.sleep(0.01)
                progress_bar.progress(p + 1)
                ph.markdown(f'<div class="note-text">{phrases[min(p // 25, 3)]}</div>', unsafe_allow_html=True)

            ph.empty()
            progress_holder.empty()

            with st.spinner("Curating your list..."):
                st.session_state.rec_names, st.session_state.rec_posters, st.session_state.rec_scores = recommend(st.session_state.selected_movie)
                st.session_state.items_to_show = 12

    with action_cols[1]:
        if current_info["trailer"]:
            st.link_button("Watch Trailer", current_info["trailer"], use_container_width=True)
        else:
            st.button("No Trailer", disabled=True, use_container_width=True)

    with action_cols[2]:
        if st.button("Add To Watchlist", use_container_width=True):
            if st.session_state.selected_movie not in st.session_state.watchlist:
                st.session_state.watchlist.append(st.session_state.selected_movie)
                save_watchlist(st.session_state.watchlist)
                st.toast("Saved to watchlist")
                st.rerun()
            else:
                st.warning("Already in watchlist")

    with action_cols[3]:
        choice = st.selectbox(
            "Jump to another title",
            movies["title"].values,
            index=list(movies["title"].values).index(st.session_state.selected_movie)
        )
        if choice != st.session_state.selected_movie:
            set_selected_movie(choice)
            st.rerun()

    st.write("")

    info_cols_1 = st.columns(3, gap="medium")
    with info_cols_1[0]:
        st.markdown(f'<div class="metric-box"><div class="metric-label">Genres</div><div class="metric-value">{current_info["genres_text"]}</div></div>', unsafe_allow_html=True)
    with info_cols_1[1]:
        st.markdown(f'<div class="metric-box"><div class="metric-label">Director</div><div class="metric-value">{current_info["director"]}</div></div>', unsafe_allow_html=True)
    with info_cols_1[2]:
        st.markdown(f'<div class="metric-box"><div class="metric-label">Cast</div><div class="metric-value">{current_info["cast_text"]}</div></div>', unsafe_allow_html=True)

    st.write("")

    info_cols_2 = st.columns(3, gap="medium")
    with info_cols_2[0]:
        st.markdown(f'<div class="metric-box"><div class="metric-label">Writers</div><div class="metric-value">{current_info["writers_text"]}</div></div>', unsafe_allow_html=True)
    with info_cols_2[1]:
        st.markdown(f'<div class="metric-box"><div class="metric-label">Countries</div><div class="metric-value">{current_info["countries_text"]}</div></div>', unsafe_allow_html=True)
    with info_cols_2[2]:
        st.markdown(f'<div class="metric-box"><div class="metric-label">Languages</div><div class="metric-value">{current_info["languages_text"]}</div></div>', unsafe_allow_html=True)

with main_right:
    st.markdown('<div class="small-title">Genre Tags</div>', unsafe_allow_html=True)
    genre_tags = get_genre_tag_list()
    tag_cols = st.columns(2, gap="small")

    for idx, tag in enumerate(genre_tags):
        with tag_cols[idx % 2]:
            if st.button(tag, key=f"tag_{tag}", use_container_width=True):
                st.session_state.genre_filter = tag
                st.rerun()

    if st.button("Clear Genre", use_container_width=True):
        st.session_state.genre_filter = "All"
        st.rerun()

    st.write("")

    st.markdown('<div class="small-title">Watchlist</div>', unsafe_allow_html=True)
    if st.session_state.watchlist:
        for movie_name in st.session_state.watchlist[:5]:
            row_cols = st.columns([4, 1], gap="small")
            with row_cols[0]:
                if st.button(movie_name, key=f"watch_{movie_name}", use_container_width=True):
                    set_selected_movie(movie_name)
                    st.rerun()
            with row_cols[1]:
                if st.button("❌", key=f"remove_{movie_name}", use_container_width=True):
                    st.session_state.watchlist.remove(movie_name)
                    save_watchlist(st.session_state.watchlist)
                    st.rerun()
    else:
        st.markdown('<div class="note-text">Your watchlist is empty.</div>', unsafe_allow_html=True)

st.write("")
st.markdown('<div class="small-title">Recommended For You</div>', unsafe_allow_html=True)

filter_cols = st.columns(6, gap="small")
with filter_cols[0]:
    st.selectbox("Browse", ["All", "Movies", "Top Picks", "Watchlist"], key="browse_mode")
with filter_cols[1]:
    st.selectbox("Genre", ["All", "Action", "Adventure", "Comedy", "Drama", "Fantasy", "Sci-Fi", "Thriller", "Crime", "Family", "Mystery", "Romance"], key="genre_filter")
with filter_cols[2]:
    st.selectbox("Year", ["All", "2020s", "2010s", "2000s", "1990s", "1980s"], key="year_filter")
with filter_cols[3]:
    st.selectbox("Language", ["All", "English", "Spanish", "French", "Hindi", "Korean"], key="language_filter")
with filter_cols[4]:
    st.selectbox("Sort By", ["Similarity", "IMDb", "Popularity", "Title"], key="sort_by")
with filter_cols[5]:
    st.selectbox("Sort", ["Descending", "Ascending"], key="sort_order")

st.write("")

if st.session_state.get("rec_names"):
    names = st.session_state.rec_names
    posters = st.session_state.rec_posters
    scores = st.session_state.rec_scores
    limit = st.session_state.items_to_show

    filtered_indices = list(range(len(names)))

    if st.session_state.browse_mode == "Watchlist":
        filtered_indices = [idx for idx in filtered_indices if names[idx] in st.session_state.watchlist]
    elif st.session_state.browse_mode == "Top Picks":
        filtered_indices = [idx for idx in filtered_indices if scores[idx] >= 70]

    if st.session_state.genre_filter != "All":
        temp_indices = []
        for idx in filtered_indices:
            candidate_title = names[idx]
            candidate_id = get_movie_id_from_title(candidate_title)
            candidate_info = get_movie_info(candidate_id)
            candidate_genres = [genre.lower() for genre in candidate_info["genres"]]
            if st.session_state.genre_filter.lower() in candidate_genres:
                temp_indices.append(idx)
        filtered_indices = temp_indices

    if st.session_state.language_filter != "All":
        temp_indices = []
        for idx in filtered_indices:
            candidate_title = names[idx]
            candidate_id = get_movie_id_from_title(candidate_title)
            candidate_info = get_movie_info(candidate_id)
            candidate_languages = [language.lower() for language in candidate_info["languages"]]
            if st.session_state.language_filter.lower() in candidate_languages:
                temp_indices.append(idx)
        filtered_indices = temp_indices

    if st.session_state.year_filter != "All":
        temp_indices = []
        for idx in filtered_indices:
            candidate_title = names[idx]
            candidate_id = get_movie_id_from_title(candidate_title)
            candidate_info = get_movie_info(candidate_id)
            if match_year_bucket(candidate_info["date"], st.session_state.year_filter):
                temp_indices.append(idx)
        filtered_indices = temp_indices

    if st.session_state.sort_by == "Title":
        filtered_indices = sorted(filtered_indices, key=lambda idx: names[idx], reverse=(st.session_state.sort_order == "Descending"))
    elif st.session_state.sort_by == "IMDb":
        filtered_indices = sorted(
            filtered_indices,
            key=lambda idx: get_movie_info(get_movie_id_from_title(names[idx]))["rating"],
            reverse=(st.session_state.sort_order == "Descending")
        )
    elif st.session_state.sort_by == "Popularity":
        filtered_indices = sorted(
            filtered_indices,
            key=lambda idx: get_movie_info(get_movie_id_from_title(names[idx]))["popularity"],
            reverse=(st.session_state.sort_order == "Descending")
        )
    else:
        filtered_indices = sorted(filtered_indices, key=lambda idx: scores[idx], reverse=(st.session_state.sort_order == "Descending"))

    visible_indices = filtered_indices[:limit]

    if visible_indices:
        for i in range(0, len(visible_indices), 4):
            rec_cols = st.columns(4, gap="medium")
            for j, col in enumerate(rec_cols):
                block_idx = i + j
                if block_idx < len(visible_indices):
                    idx = visible_indices[block_idx]
                    candidate_title = names[idx]
                    candidate_id = get_movie_id_from_title(candidate_title)
                    candidate_info = get_movie_info(candidate_id)
                    reason = get_match_reason(st.session_state.selected_movie, candidate_title)

                    with col:
                        st.image(posters[idx], use_container_width=True)
                        st.markdown(f'<div class="match-tag">{scores[idx]}% Match • {reason}</div>', unsafe_allow_html=True)
                        st.markdown(f"**{candidate_title}**")
                        st.caption(f"{estimate_quality(candidate_info['rating'])} • {candidate_info['rating']:.1f} • {extract_year_from_date(candidate_info['date'])}")
                        if st.button(f"View {candidate_title}", key=f"rec_{idx}", use_container_width=True):
                            set_selected_movie(candidate_title)
                            st.session_state.rec_names = []
                            st.session_state.rec_posters = []
                            st.session_state.rec_scores = []
                            st.rerun()
    else:
        st.warning("No recommendations matched the current filters. Change Genre, Language, or Year and try again.")

    if limit < len(filtered_indices):
        if st.button("Load More Recommendations", use_container_width=True):
            st.session_state.items_to_show += 12
            st.rerun()
else:
    st.info("Search or select a movie first, then click 'Discover Similar' to view recommendations.")

st.markdown('<div class="footer-note">CineMatch • Cleaner, simpler, and focused on movie recommendation functionality.</div>', unsafe_allow_html=True)
