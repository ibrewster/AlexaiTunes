import flask
import subprocess
import ujson
import requests
import base64
import hashlib
import cryptography
import tempfile
from cryptography import x509
from cryptography.hazmat.backends import default_backend
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta

from . import app, itunes_library
from functools import wraps

intent_handlers = {}

def intent(intents):
    if not isinstance(intents, (list, tuple)):
        raise TypeError("Intents must be of list type")
    def decorator(func):
        for intent in intents:
            intent_handlers[intent] = func
        return func
    return decorator

def create_playlist(criteria):
    script = f"""
tell application "iTunes"
    if (exists playlist "Alexa Selections") then
        delete playlist "Alexa Selections"
    end if
    set name of (make new playlist) to "Alexa Selections"
    set selectedTracks to {criteria}
    repeat with thisTrack in selectedTracks
        duplicate thisTrack to playlist "Alexa Selections"
    end repeat
    play playlist "Alexa Selections"
end tell
        """
    return script

@app.route("/", methods=["POST"])
def index():
    """This function fires off all processing for the alexa request. Since,
    theoretically, any random person could hit this server and mess with our
    iTunes, we verify the request thouroughly. Of course, Amazon requires this as well."""

    ########################
    ## BEGIN REQUEST VERIFICATION
    ########################
    # First, let's pull out the certificate URL to use to verify this request
    Signaturecertchainurl = flask.request.headers.get('Signaturecertchainurl')
    sigchainurl_parts = urlparse(urljoin(Signaturecertchainurl, '.'))

    # Verify the components of the certificate url
    if sigchainurl_parts.scheme != 'https' or \
       sigchainurl_parts.netloc != "s3.amazonaws.com" or \
       not sigchainurl_parts.path.startswith("/echo.api/"):
        flask.abort(400)

    #get and parse out the signing certificate
    cert = requests.get(Signaturecertchainurl).text
    parsed_cert = x509.load_pem_x509_certificate(cert.encode('ASCII'), default_backend())

    # Verify that the certificate is a valid chain
    # We need to put it in quotes to properly process on the command line.
    cert = '"' + cert + '"'
    proc = subprocess.Popen(["/usr/bin/openssl", "verify", "-untrusted"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    response = proc.communicate(cert.encode('ASCII'))[0]
    if proc.returncode != 0:
        flask.abort(404)

    #Make sure certificate is valid
    if parsed_cert.not_valid_before >= datetime.utcnow() or \
       parsed_cert.not_valid_after <= datetime.utcnow():
        flask.abort(400)
    cert_san_extension = parsed_cert.extensions.get_extension_for_oid(x509.OID_SUBJECT_ALTERNATIVE_NAME)
    names = cert_san_extension.value.get_values_for_type(x509.DNSName)
    if 'echo-api.amazon.com' not in names:
        flask.abort(400)

    # Verify that the signature matches the actual content received
    pub_key = parsed_cert.public_key()
    encrypted_sig = base64.decodestring(flask.request.headers.get('Signature').encode('ASCII'))
    try:
        pub_key.verify(encrypted_sig, flask.request.data,
                   cryptography.hazmat.primitives.asymmetric.padding.PKCS1v15(),
                   cryptography.hazmat.primitives.hashes.SHA1())
    except Exception as e:
        print(e)
        flask.abort(400)


    # Ok, content came from Amazon alexa. Yay! Let's continue....
    # Since it is from Alexa, it is a JSON formated dataset
    request = ujson.loads(flask.request.data)

    # Make sure this is coming from *MY* alexa skill
    try:
        if (request['session']['application']['applicationId'] !=
            "amzn1.ask.skill.3173570a-f916-47e2-9882-fe38778580b6"):
            raise ValueError("Invalid Application ID")
    except (KeyError, ValueError):
        flask.abort(400)

    # And, finally, verify the request timestamp is within 150 seconds of now
    try:
        timestamp = request['request']['timestamp']
    except KeyError:
        flask.abort(400)  #invalid request - no timestamp
    timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")

    if abs((timestamp - datetime.utcnow()).total_seconds()) > 150:
        flask.abort(400)

    #########################
    ## END REQUEST VERIFICATION
    #########################

    # Ok, so now we know it came from amazon, from my skill, and isn't just
    # someone resending the same packets over and over again. Let's actually do
    # something with it!
    request_type = request['request'].get('type', 'unknown')

    if request_type == "LaunchRequest":
        result = "OK"
    elif request_type == "IntentRequest":
        intent = request['request'].get('intent', {})
        intent_name = intent.get('name')
        try:
            result = intent_handlers[intent_name](intent)
        except KeyError:
            result = "I don't know how to do that"

    response_data = {
        "version": "1.0",
        "sessionAttribtutes": {},
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                "text": str(result),
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

    #print(f"running script:\n{script}")
    #return "Some Song,Some Artist"

@intent(['PlayPlaylist'])
def play_playlist(intent_data):
    playlist=intent_data.get('slots', {}).get('playlist',{}).get('value')

    if itunes_library:  # if we don't have the library available, we just try it.
        playlists = itunes_library.getPlaylistNames()

        if playlist.lower() != "library" and playlist.lower() not in (list.lower() for list in playlists):
            return f"I can't find any playlists named {playlist}"

    script = f"""tell application "iTunes" to play playlist "{playlist}" """

    result = run_script(script)
    return result

@intent(['PlaySong'])
def play_song(intent_data):
    song_title=intent_data.get('slots', {}).get('title',{}).get('value')
    song_artist=intent_data.get('slots', {}).get('artist',{}).get('value')



    if song_title and song_artist:  # both title and artist
        if not f"{song_title.lower()}, {song_artist.lower()}" in (f"""{s.name.lower()}, {"" if s.artist is None else s.artist.lower()}""" for s in itunes_library.songs.values()):
            return f"I can't find a song named {song_title} by {song_artist}"

        script = create_playlist(f"""{{item 1}} of (every file track of playlist "Library" whose name is "{song_title}" and artist is "{song_artist}") """)
    elif song_title:  # title only, no artist
        # See if we can find the song in the library
        if not song_title.lower() in  (s.name.lower() for s in itunes_library.songs.values()):
            return f"I can't find a song named {song_title}"

        script = create_playlist(f"""{{item 1}} of (every file track of playlist "Library" whose name is "{song_title}") """)
    else:  # No title or artist
        script = """tell application "iTunes" to play"""

    try:
        run_script(script)
    except:
        error = f"Unable to find song {song_title}"
        if song_artist:
            error += f" by {song_artist}"
        return error

    script = """tell application "iTunes"
        set track_artist to the artist of the current track
        set track_title to the title of the current track
        log track_title & "," & track_artist
    end tell
    """
    result = run_script(script)
    song_title, song_artist = result.split(",")
    return f"Playing {song_title} by {song_artist}"

@intent(['PlayAlbum'])
def play_album(intent_data):
    album_name=intent_data.get('slots', {}).get('album',{}).get('value')

    script = create_playlist(f"""every track of playlist "Library" whose album is "{album_name}" """)

    result = run_script(script)
    return f"Playing album {album_name}"

@intent(['AMAZON.StopIntent', 'AMAZON.PauseIntent'])
def stop_playback(_):
    script = """tell application "iTunes" to pause"""
    run_script(script)
    return "OK"

@intent(['AMAZON.NextIntent'])
def next_track(_):
    script = """tell application "iTunes" to play next track """

    run_script(script)
    return "OK"

@intent(['AMAZON.PreviousIntent'])
def previous_track(_):
    script = """tell application "iTunes" to play previous track """

    run_script(script)
    return "OK"
