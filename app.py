from flask import Flask, redirect, request, session, url_for, render_template, jsonify
import requests
from urllib.parse import urlencode
import os
import config
from itertools import chain


app = Flask(__name__)
app.secret_key = config.app_secret

auth_query_parameters = {
    "response_type": "code",
    "redirect_uri": "http://127.0.0.1:5000/sprout",
    "scope": "user-read-private user-read-email user-read-recently-played user-top-read playlist-modify-public",
    "client_id": config.client_id
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/login')
def login():
    '''After user clicks login with Spotify, this function handles the redirect to the Spotify website.'''
    url_args = "&".join([f"{key}={val}" for key, val in auth_query_parameters.items()])
    auth_url = f"https://accounts.spotify.com/authorize?{url_args}"
    return redirect(auth_url)

@app.route('/sprout')
def sprout():
    '''After getting user Spotify creds, the function will handle displaying the user's current listening data, and displaying the form to get information about the playlist they would like to create.'''

    auth_token = request.args['code']
    code_payload = {
        "grant_type": "authorization_code",
        "code": str(auth_token),
        "redirect_uri": "http://127.0.0.1:5000/sprout",
        'client_id': config.client_id,
        'client_secret': config.client_secret,
    }
    post_request = requests.post("https://accounts.spotify.com/api/token", data=code_payload)

    # Tokens are Returned to Application
    response_data = post_request.json()
    print(response_data)
    if 'error' in response_data:
        return redirect(url_for('login'))
    access_token = response_data["access_token"]
    refresh_token = response_data["refresh_token"]
    token_type = response_data["token_type"]
    expires_in = response_data["expires_in"]
    session['access_token'] = access_token

    # Use the access token to access Spotify API
    authorization_header = {"Authorization": f"Bearer {access_token}"}

    display_name = requests.get("https://api.spotify.com/v1/me", headers=authorization_header).json()['display_name']

    top_artists = requests.get("https://api.spotify.com/v1/me/top/artists?limit=5", headers=authorization_header)
    top_artists_data = top_artists.json()

    top_tracks = requests.get("https://api.spotify.com/v1/me/top/tracks?limit=5", headers=authorization_header)
    top_tracks_data = top_tracks.json()


    return render_template("sprout.html", top_artists=top_artists_data['items'], top_tracks=top_tracks_data['items'], display_name = display_name)

@app.route('/create', methods=['POST'])
def create_playlist():
    '''Handles the creation of the playlist''' 
    access_token = session.get('access_token', None)
    if not access_token:
        return redirect(url_for('login'))
    
    branch = request.form['branch']
    playlist_name = request.form['playlist_name']
    num_tracks = min(int(request.form['num_tracks']), 30) 


    headers = {'Authorization': f"Bearer {access_token}"}
    user_profile = requests.get("https://api.spotify.com/v1/me", headers=headers).json()

    

    # Depending on the branch chosen, modify the track fetching logic
    if branch == 'genre':
        # Fetch tracks by genre (implement this)
        top_artists = requests.get("https://api.spotify.com/v1/me/top/artists?limit=3", headers=headers)
        top_artists_data = top_artists.json()['items']
        top_artists_genres = [artist['genres'] for artist in top_artists_data]
        top_artists_genres = list(chain.from_iterable(top_artists_genres))
        genres_string = "%2C".join([str(item) for item in top_artists_genres])
        genres_string = genres_string.replace(" ", "+")

        recommendation_req = requests.get(f"https://api.spotify.com/v1/recommendations?limit={num_tracks}&seed_genres={genres_string}", headers=headers)
        print(recommendation_req)
        recommended_tracks = recommendation_req.json()

        #print(recommended_tracks)
    elif branch == 'artist':
        # Fetch tracks by artist (implement this logic)
        top_artists = requests.get("https://api.spotify.com/v1/me/top/artists?limit=3", headers=headers)
        top_artists_data = top_artists.json()['items']
        top_artists_ids = [artist['id'] for artist in top_artists_data]
        ids_string = "%2C".join([str(item) for item in top_artists_ids])
        recommended_tracks = requests.get(f"https://api.spotify.com/v1/recommendations?limit={num_tracks}&seed_artists={ids_string}", headers=headers).json()

    elif branch == 'bpm':
        # Fetch tracks by BPM (implement this logic)
        top_tracks = requests.get("https://api.spotify.com/v1/me/top/tracks?limit=3", headers=headers)
        top_tracks_data = top_tracks.json()['items']
        top_tracks_ids = [track['id'] for track in top_tracks_data]
        ids_string = "%2C".join([str(item) for item in top_tracks_ids])
        track_features_req = requests.get(f"https://api.spotify.com/v1/audio-features?ids={ids_string}", headers=headers)
        track_features= track_features_req.json()
        bpms = [int(track['tempo']) for track in track_features['audio_features']]
        average_bpm = int(sum(bpms) / len(bpms))
        min_bpm = average_bpm - 10
        max_bpm = average_bpm + 10
        print(f"https://api.spotify.com/v1/recommendations?limit={num_tracks}&target_tempo={average_bpm}")
        recommended_req = requests.get(f"https://api.spotify.com/v1/recommendations?limit={num_tracks}&min_tempo={min_bpm}&max_tempo={max_bpm}&seed_tracks={ids_string}", headers=headers)
        print(recommended_req)
        recommended_tracks = recommended_req.json()
    
    track_uris = [track['uri'] for track in recommended_tracks['tracks']]

    # Create the playlist
    playlist = requests.post(
        f"https://api.spotify.com/v1/users/{user_profile['id']}/playlists",
        headers=headers,
        json={'name': playlist_name, 'public': True}
    ).json()
    
    # Add tracks to the playlist
    snapshot_id = requests.post(
        f"https://api.spotify.com/v1/playlists/{playlist['id']}/tracks",
        headers=headers,
        json={'uris': track_uris, "position": 0}
    )

    print(snapshot_id)
    session['playlist_id'] = playlist['id']
    return redirect("http://127.0.0.1:5000/sprouted") 

@app.route('/sprouted')
def sprouted():
    '''After creating the playlist, this function will handle fetching that playlist and displaying its contents in the page.'''    
    
    access_token = session.get('access_token', None)
    if not access_token:
        return redirect(url_for('login'))
    headers = {'Authorization': f"Bearer {access_token}"}
    playlist_id = session['playlist_id']
    playlist_data = requests.get(f"https://api.spotify.com/v1/playlists/{playlist_id}", headers=headers).json()
    playlist_track_ids = [track['track']['id'] for track in playlist_data['tracks']['items']]
    ids_string = "%2C".join([str(item) for item in playlist_track_ids])
    songs = requests.get(f"https://api.spotify.com/v1/tracks?ids={ids_string}", headers=headers).json()

    return render_template("sprouted.html", tracks=songs['tracks'], playlist_id = playlist_id)

   


if __name__ == '__main__':
    app.run(debug=True)