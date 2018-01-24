import flask
import subprocess
import ujson

from . import app
from libpytunes import Library



@app.route("/", methods=["POST"])
def index():
    request = ujson.loads(request.data)
    request_type = request['request'].get('type', 'unknown')
    print(f"Received request of type {request_type}")

    response_data = {
        "version": "1.0",
        "sessionAttribtutes": {},
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": "OK",
            },
        },
    }

    response_string = ujson.dumps(response_data)
    response = flask.Response(response_string,
                              content_type="application/json;charset=UTF-8")
    return response

def run_script(script):
    proc = subprocess.Popen(['osascript', '-'],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            universal_newlines=True)

    stdout_output = proc.communicate(script)[0]
    return stdout_output

@app.route('/play/playlist/<playlist>')
def play_playlist(playlist):
    l = Library("/Media/iTunes/iTunes Library.xml")
    playlists=l.getPlaylistNames()

    if playlist not in playlists:
        return "Not Found"

    script = f"""tell application "iTunes" to play playlist "{playlist}" """

    result = run_script(script)
    return result

@app.route('/play/song/<song_title>')
def play_song(song_title):
    script = f"""tell application "iTunes" to play track "{song_title}" """

    try:
        run_script(script)
    except:
        return f"Unable to find song {song_title}"

    script = """tell application "iTunes"
        set track_artist to the artist of the current track
        log track_artist
    end tell
    """
    result = run_script(script)
    return f"Playing {song_title} by {result}"

@app.route('/play/song/<song_title>/<artist>')
def play_song_artist(song_title, artist):
    script = f"""tell application "iTunes"
        set search_results to (every file track of playlist "Library" whose name contains "{song_title}" and artist contains "{artist}")
	play item 1 of search_results
end tell
    """

    try:
        run_script(script)
    except:
        return f"Unable to find {song_title} by {artist}"

    script = """tell application "iTunes"
        set track_artist to the artist of the current track
        log track_artist
    end tell
    """
    result = run_script(script)
    return f"Playing {song_title} by {result}"


@app.route("/stop")
def stop_playback():
    script = """tell application "iTunes" to pause"""
    run_script(script)
    return "OK"

@app.route("/play")
def start_playback():
    script = """tell application "iTunes" to play"""

    run_script(script)
    return "OK"

@app.route("/play/next")
def next_track():
    script = """tell application "iTunes" to play next track """

    run_script(script)
    return "OK"

@app.route("/play/previous")
def previous_track():
    script = """tell application "iTunes" to play previous track """

    run_script(script)
    return "OK"
