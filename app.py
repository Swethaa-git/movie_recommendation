from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from werkzeug.security import check_password_hash, generate_password_hash
import pickle
import pandas as pd
import requests
import os
import sqlite3

# Initialize Flask app
app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Replace with your actual secret key

def init_db():
    conn = sqlite3.connect('users.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL)''')
    conn.commit()
    conn.close()

init_db()

# Sample movies DataFrame (for demonstration; ensure your actual data matches this structure)
movies_df = pd.DataFrame({
    'id': [1, 2, 3, 4],
    'title': ['Superman', 'Stargate', 'Tron', 'Dune'],
    'genre': ['Action', 'Sci-Fi', 'Sci-Fi', 'Adventure'],
    'platforms': ['Netflix', 'Hulu', 'Prime Video', 'Disney+'],
    'description': [
        'A superhero film about Superman.',
        'A sci-fi film about interstellar travel.',
        'A sci-fi film set in a digital world.',
        'An adventure film set in a desert world.'
    ],
    'year': [1978, 1994, 1982, 1984]
})

# Define the image directory after app initialization
IMAGE_DIR = os.path.join(app.root_path, 'static', 'images')
if not os.path.exists(IMAGE_DIR):
    os.makedirs(IMAGE_DIR)

# OMDB API configuration
api_key = 'd4c7f5d3'  # Replace with your actual API key
base_url = 'http://www.omdbapi.com/'

# Load data (ensure these pickle files exist and are correctly formatted)
with open('movies_list.pkl', 'rb') as f:
    movies = pickle.load(f)
with open('similarity.pkl', 'rb') as f:
    similarity = pickle.load(f)
with open('user_profiles.pkl', 'rb') as f:
    user_profiles = pickle.load(f)

# User ratings
user_ratings = pd.DataFrame(columns=['user_id', 'movie_id', 'rating'])

def fetch_movie_image_from_omdb(title, movie_id):
    """Fetch movie poster from OMDb for a given title and save it using movie_id."""
    search_url = f"{base_url}?t={title}&apikey={api_key}"
    try:
        response = requests.get(search_url)
        if response.status_code != 200:
            print(f"Error: Unable to fetch movie data for {title} (Status Code: {response.status_code})")
            return None
        
        response_data = response.json()

        if 'Poster' in response_data and response_data['Poster'] != 'N/A':
            image_url = response_data['Poster']
            image_data = requests.get(image_url).content

            # Save the image
            image_filename = f'{movie_id}.jpg'
            image_path = os.path.join(IMAGE_DIR, image_filename)
            with open(image_path, 'wb') as f:
                f.write(image_data)
            print(f"Saved poster for '{title}' to {image_path}")
            return f'/static/images/{image_filename}'
        else:
            print(f"No poster available for '{title}'")
            return None
    except requests.RequestException as e:
        print(f"Error: Failed to connect to OMDb API for '{title}'. Exception: {e}")
        return None

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('recommend_movies'))
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        # Fetch user from the database
        conn = sqlite3.connect('users.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = c.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            session['user'] = username  # Consistent session key
            flash('Login successful!', 'success')
            return redirect(url_for('recommend_movies'))
        else:
            flash('Incorrect username or password.', 'danger')
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        # Hash the password before storing
        hashed_password = generate_password_hash(password)
        
        # Insert the new user into the database
        try:
            conn = sqlite3.connect('users.db')
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            conn.commit()
            conn.close()
            
            session['user'] = username
            flash('Signup successful! You are now logged in.', 'success')
            return redirect(url_for('recommend_movies'))
        except sqlite3.IntegrityError:
            flash('Username already exists. Please choose a different one.', 'danger')
            return redirect(url_for('signup'))
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    flash('Logged out successfully.', 'success')  # Correctly flash the message
    return redirect(url_for('login'))

@app.route('/recommend_movies', methods=['GET', 'POST'])
def recommend_movies():
    if 'user' not in session:
        flash('Please log in to access recommendations.', 'warning')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        movie_name = request.form['movie_name'].strip().lower()
        
        # Check if the movie exists in the dataset
        if movie_name not in movies['title_x'].str.lower().values:
            flash('Movie not found. Please try another title.', 'danger')
            return jsonify({'status': 'Movie not found'}), 404
        
        # Find the movie index
        index = movies[movies['title_x'].str.lower() == movie_name].index[0]
        distances = sorted(list(enumerate(similarity[index])), reverse=True, key=lambda x: x[1])
        
        # Prepare the recommended movies data
        recommended_movies = []
        for i in distances[1:6]:  # Skip the first, as it's the same movie
            movie_data = movies.iloc[i[0]]
            movie_title = movie_data['title_x']
            movie_id = movie_data['id']
            
            # Check if image exists
            image_filename = f'{movie_id}.jpg'
            image_path = os.path.join(IMAGE_DIR, image_filename)
            if not os.path.exists(image_path):
                # Try to fetch the image from OMDb
                image_url = fetch_movie_image_from_omdb(movie_title, movie_id)
                if not image_url:
                    # Use default image if not found
                    image_url = '/static/images/default.jpg'
            else:
                image_url = f'/static/images/{image_filename}'
            
            # Append the movie details, including image path, to the recommendation list
            recommended_movies.append({
                'title': movie_title,
                'id': movie_id,
                'genre': movie_data['genre'],
                'platforms': movie_data['platforms'],
                'image_url': image_url  # Path to the image
            })
        print("Recommended Movies:")
        for movie in recommended_movies:
            print(movie) 

        # Flash success message
        flash('Movies recommended successfully!', 'success')

        # Return the recommendations as JSON
        return jsonify(recommended_movies)
    
    return render_template('recommend_movies.html')

@app.route('/movie/<int:movie_id>', methods=['GET'])
def movie_detail(movie_id):
    # Fetch the movie from the DataFrame
    movie_data = movies_df.loc[movies_df['id'] == movie_id]
    
    # Debugging statements
    print("Requested movie ID:", movie_id)
    print("Available movie IDs in DataFrame:", movies_df['id'].tolist())
    print("Fetched movie data:", movie_data)
    
    if movie_data.empty:
        flash('Movie not found.', 'danger')
        return redirect(url_for('recommend_movies'))
    
    # Get the first row from the DataFrame
    movie_info = movie_data.iloc[0]
    
    title = movie_info['title']
    genre = movie_info['genre']
    platforms = movie_info['platforms']
    description = movie_info['description']
    year = movie_info['year']
    
    # Use movie_id for image filename to maintain consistency
    image_filename = f'{movie_id}.jpg'
    image_path = os.path.join(IMAGE_DIR, image_filename)
    if not os.path.exists(image_path):
        # Try to fetch the image from OMDb
        image_url = fetch_movie_image_from_omdb(title, movie_id)
        if not image_url:
            # Use default image if not found
            image_url = '/static/images/default.jpg'
    else:
        image_url = f'/static/images/{image_filename}'
    
    return render_template('movie_detail.html', 
                           title=title, 
                           genre=genre, 
                           platforms=platforms, 
                           description=description, 
                           year=year, 
                           image_url=image_url)

@app.route('/rate_movie', methods=['POST'])
def rate_movie():
    if 'user' not in session:
        flash('Please log in to rate movies.', 'warning')
        return redirect(url_for('login'))
    
    data = request.get_json()  # Corrected to call the method
    if not data:
        return jsonify({'status': 'No data provided'}), 400
    
    movie_title = data.get('movie_title')
    rating = data.get('rating')

    if not movie_title or not rating:
        return jsonify({'status': 'Invalid data'}), 400
    
    try:
        rating = float(rating)
        if rating < 1 or rating > 5:
            raise ValueError
    except ValueError:
        return jsonify({'status': 'Rating must be a number between 1 and 5'}), 400
    
    # Find the movie by title
    movie = movies[movies['title_x'] == movie_title]
    if movie.empty:
        return jsonify({'status': 'Movie not found'}), 404
    movie_id = movie.iloc[0]['id']
    
    # Update user ratings
    user_ratings.loc[len(user_ratings)] = [session['user'], movie_id, rating]
    
    # Update the user's profile
    if session['user'] not in user_profiles:
        user_profiles[session['user']] = {'rated_movies': {}}
    
    user_profiles[session['user']]['rated_movies'][movie_id] = rating
    
    # Save the updated profiles
    with open('user_profiles.pkl', 'wb') as f:
        pickle.dump(user_profiles, f)
    
    flash('Movie rated successfully!', 'success')
    return jsonify({'status': 'success'})

@app.route('/profile')
def profile():
    if 'user' in session:
        user = session['user']
        user_profile = user_profiles.get(user, {'rated_movies': {}})
        print(f"User: {user}")
        print(f"User Profile: {user_profile}")
        print(f"Movies DataFrame Columns: {movies.columns}")
        return render_template('profile.html', user=user, profile=user_profile, movies=movies)
    else:
        flash('Please log in to view your profile.', 'warning')
        return redirect(url_for('login'))

@app.route('/recommend', methods=['POST'])
def recommend():
    print("Entered /recommend route")
    
    # Check if form data is present
    if 'movie_name' not in request.form:
        print("No 'movie_name' in request.form")
        flash('No movie name provided.', 'danger')
        return jsonify({'status': 'No movie name provided'}), 400
    
    movie_name = request.form['movie_name'].strip().lower()
    print(f"Received movie_name: {movie_name}")
    
    # Check if the movie exists in the dataset
    if movie_name not in movies['title_x'].str.lower().values:
        print(f"Movie '{movie_name}' not found in dataset")
        flash('Movie not found. Please try another title.', 'danger')
        return jsonify({'status': 'Movie not found'}), 404
    
    # Find the movie index
    index = movies[movies['title_x'].str.lower() == movie_name].index[0]
    distances = sorted(list(enumerate(similarity[index])), reverse=True, key=lambda x: x[1])
    
    # Prepare the recommended movies data
    recommended_movies = []
    for i in distances[1:6]:  # Skip the first, as it's the same movie
        movie_data = movies.iloc[i[0]]
        movie_title = movie_data['title_x']
        movie_id = movie_data['id']
        
        # Check if image exists
        image_filename = f'{movie_id}.jpg'
        image_path = os.path.join(IMAGE_DIR, image_filename)
        if not os.path.exists(image_path):
            # Try to fetch the image from OMDb
            image_url = fetch_movie_image_from_omdb(movie_title, movie_id)
            if not image_url:
                # Use default image if not found
                image_url = '/static/images/default.jpg'
                print(f"Using default image for '{movie_title}'")
        else:
            image_url = f'/static/images/{image_filename}'
            print(f"Found image for '{movie_title}': {image_url}")
        
        # Append the movie details, including image path, to the recommendation list
        recommended_movies.append({
            'title': movie_title,
            'genre': movie_data['genre'],
            'platforms': movie_data['platforms'],
            'image_url': image_url  # Path to the image
        })
    
    print("Recommended Movies:", recommended_movies)
    flash('Movies recommended successfully!', 'success')
    # Return the recommendations as JSON
    return jsonify(recommended_movies)

if __name__ == '__main__':
    app.run(debug=True)