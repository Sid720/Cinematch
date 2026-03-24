import pandas as pd
import numpy as np
import ast
import pickle
import bz2
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity


MOVIES_FILE = 'tmdb_5000_movies.csv'
CREDITS_FILE = 'tmdb_5000_credits.csv'
MOVIE_DICT_FILE = 'movie_dict.pkl'
SIMILARITY_FILE = 'similarity.pbz2'


def safe_literal_eval(value):
    try:
        return ast.literal_eval(value)
    except:
        return []


def convert(obj):
    items = safe_literal_eval(obj)
    names = []

    for item in items:
        if isinstance(item, dict) and 'name' in item:
            names.append(item['name'])

    return names


def fetch_director(obj):
    items = safe_literal_eval(obj)

    for item in items:
        if isinstance(item, dict) and item.get('job') == 'Director':
            return [item.get('name', '')]

    return []


def fetch_top_cast(obj, limit=3):
    items = safe_literal_eval(obj)
    cast_names = []

    for item in items[:limit]:
        if isinstance(item, dict) and 'name' in item:
            cast_names.append(item['name'])

    return cast_names


def clean_token_list(tokens):
    cleaned_tokens = []

    for token in tokens:
        if isinstance(token, str):
            cleaned_tokens.append(token.replace(" ", ""))

    return cleaned_tokens


def load_and_merge_data():
    movies = pd.read_csv(MOVIES_FILE)
    credits = pd.read_csv(CREDITS_FILE)

    merged = movies.merge(credits, on='title')

    merged = merged[
        ['movie_id', 'title', 'overview', 'genres', 'keywords', 'cast', 'crew']
    ]

    merged.dropna(inplace=True)
    merged.drop_duplicates(subset=['title'], inplace=True)

    return merged


def preprocess_movies(movies):
    movies['genres'] = movies['genres'].apply(convert)
    movies['keywords'] = movies['keywords'].apply(convert)
    movies['cast'] = movies['cast'].apply(fetch_top_cast)
    movies['crew'] = movies['crew'].apply(fetch_director)
    movies['overview'] = movies['overview'].apply(lambda x: x.split() if isinstance(x, str) else [])

    for col in ['genres', 'keywords', 'cast', 'crew']:
        movies[col] = movies[col].apply(clean_token_list)

    movies['tags'] = (
        movies['overview']
        + movies['genres']
        + movies['keywords']
        + movies['cast']
        + movies['crew']
    )

    new_df = movies[['movie_id', 'title', 'tags']].copy()
    new_df['tags'] = new_df['tags'].apply(lambda x: " ".join(x).lower())

    return new_df


def build_similarity_matrix(tag_series):
    cv = CountVectorizer(max_features=5000, stop_words='english')
    vectors = cv.fit_transform(tag_series).toarray()
    similarity = cosine_similarity(vectors).astype(np.float32)

    return similarity


def save_outputs(movie_df, similarity_matrix):
    with open(MOVIE_DICT_FILE, 'wb') as f:
        pickle.dump(movie_df.to_dict(), f)

    with bz2.BZ2File(SIMILARITY_FILE, 'w') as f:
        pickle.dump(similarity_matrix, f)


def main():
    movies = load_and_merge_data()
    processed_movies = preprocess_movies(movies)
    similarity_matrix = build_similarity_matrix(processed_movies['tags'])
    save_outputs(processed_movies, similarity_matrix)

    print("Success: Compressed files (movie_dict.pkl and similarity.pbz2) generated.")


if __name__ == "__main__":
    main()
