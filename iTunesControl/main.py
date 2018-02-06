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

import hmac
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta

import re
from num2words import num2words
from fuzzywuzzy import fuzz

from . import app, itunes_library, config, get_iTunes_lib, get_tun_url, register_public

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

def sort_fuzzy(item):
    #Use the fuzzy match value, but weigh ones that have exact title matches higher
    if item[2]:
        return item[1] * 10
    else:
        return item[1]

def normalize_text(text):
    """Replace any numbers in a string with their textual representation.
    Note that this may not be desirable. While "Beethoven's 1st symphony" will
    probably need to be translated to "Beethoven's first symphony" in order to
    match, "Beethoven's Symphony No. 1" quite possibly might not. Use only as
    needed."""
    #Look for odinals (1st, 2nd, 3rd, etc) first
    ordinals = re.findall('((\d+)(st|nd|rd|th))', text)
    for entire_result, num_value, _ in ordinals:
        text = text.replace(entire_result,
                            num2words(int(num_value), ordinal=True))

    #Now look for any "bare" numbers ("love potion number 9", for example)
    numbers = re.findall('\d+', text)
    for num_value in numbers:
        text = text.replace(num_value, num2words(int(num_value)))

    #Do some basic normalization
    text = text.replace("-", ' ').replace("$", 's')

    return text

def create_playlist(criteria):
    script = f"""
tell application "iTunes"
    if (exists playlist "Alexa Selections") then
        delete playlist "Alexa Selections"
    end if
    set name of (make new playlist) to "Alexa Selections"
    set selectedTracks to {criteria}

    -- find highest track number
    set hi_track_count to 0
    repeat with a_track in selectedTracks
            set tk_num to track number of a_track
            if tk_num > hi_track_count then set hi_track_count to tk_num
    end repeat

    --add items to playlist in track order.
    repeat with i from 0 to hi_track_count -- for each number thru hi_track_count...
        repeat with thisTrack in selectedTracks
            if track number of thisTrack is i then
                duplicate thisTrack to playlist "Alexa Selections"
                exit repeat --no need to look at the rest of the items
            end if
        end repeat
    end repeat

    play playlist "Alexa Selections"
end tell
        """
    return script

@app.route("/alexa", methods=["POST"])
def alexa():
    """This function fires off all processing for the alexa request. Since,
    theoretically, any random person could hit this server and mess with our
    iTunes, we verify the request signature."""

    ########################
    ## BEGIN REQUEST VERIFICATION
    ########################
    # First, generate a signature from the data we received using our shared secret.
    my_signature = hmac.new(b"6wQ%8cB!mx_zjqXZBm^+pBWW", flask.request.data,
                            'SHA256').hexdigest().encode('UTF8')


    # Verify that the signature matches the actual content received
    received_sig = flask.request.headers.get('Signature').encode('ASCII')
    if not hmac.compare_digest(received_sig, my_signature):
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
        print("Received invalid request from foreign skill")
        flask.abort(400)

    # And, finally, verify the request timestamp is within 150 seconds of now
    try:
        timestamp = request['request']['timestamp']
    except KeyError:
        print("Received invalid request with no timestamp")
        flask.abort(400)  #invalid request - no timestamp
    timestamp = datetime.strptime(timestamp, "%Y-%m-%dT%H:%M:%SZ")

    if abs((timestamp - datetime.utcnow()).total_seconds()) > 150:
        print("Receieved invalid request with expired timestamp")
        flask.abort(400)

    #########################
    ## END REQUEST VERIFICATION
    #########################

    # Ok, so now we know it came from amazon, from my skill, and isn't just
    # someone resending the same packets over and over again. Let's actually do
    # something with it!
    request_type = request['request'].get('type', 'unknown')

    # Set a default response in case we get something confusing.
    result = "I'm sorry, I don't know how to do that"
    if request_type == "LaunchRequest":
        result = "OK"
    elif request_type == "SessionEndedRequest":
        return None
    elif request_type == "IntentRequest":
        intent = request['request'].get('intent', {})
        intent_name = intent.get('name')
        print(f"Received {intent_name} intent request")

        try:
            result = intent_handlers[intent_name](intent)
        except KeyError as e:
            result = "I don't know how to do that"
    else:
        print(f"Received unknown request type: {request_type}")

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
    print(f"running script:\n{script}")
    #return "Some Song,Some Artist"

    proc = subprocess.Popen(['osascript', '-'],
                            stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT,
                            universal_newlines=True)

    stdout_output = proc.communicate(script)[0]
    return stdout_output

def fuzzy_match(item, options, all_matches=False):
    fuzzy_matches=[]
    requested_normalized=normalize_text(item.lower())

    for option in options:
        normalized_name=normalize_text(option.lower())

        match=fuzz.ratio(normalized_name,requested_normalized)
        if match==100:
            #If we found a perfect match, just return it
            if not all_matches:
                return (option,100)
            else:
                fuzzy_matches.append((option,match))
                continue
        if match>=88:
            fuzzy_matches.append((option,match))
            continue
    else:
        #No exact match found, or all matches wanted
        if not fuzzy_matches:
            #No fuzzy matches either
            return None
        else:
            if all_matches:
                return fuzzy_matches

            # sort the fuzzy matches by closeness, and return the closest
            fuzzy_match=sorted(fuzzy_matches,key=lambda x:x[1]).pop(0)
            return fuzzy_match

@intent(['PlayPlaylist'])
def play_playlist(intent_data):
    requested=intent_data.get('slots', {}).get('playlist',{}).get('value').lower()

    if itunes_library():  # if we don't have the library available, we just try it.
        playlists = itunes_library().getPlaylistNames()

        # A playlist of "Library is valid, though not listed"
        if requested != "library":
            match=fuzzy_match(requested,playlists)
            if match is None:
                return f"I can't find any playlists named {requested}"
            else:
                requested=match[0]

    script = f"""tell application "iTunes" to play playlist "{requested}" """

    result = run_script(script)
    return f"Playing playlist {requested}"

@intent(['PlaySong'])
def play_song(intent_data):
    song_title=intent_data.get('slots', {}).get('title',{}).get('value')
    song_artist=intent_data.get('slots', {}).get('artist',{}).get('value')

    if not song_title:
        # if we don't have a title, treat this as a bare "play" request, even if
        # we have an artist
        script = """tell application "iTunes" to play"""
    else:
        # Find the cannonical name of the track in the library. Gives the FIRST match.

        # this gives a syntax error if I take the space out at the end,
        # so strip it off after the fact.
        script = """{{item 1}} of (every file track of playlist "Library" whose name is "{title}" """.strip()

        song_title = normalize_text(song_title.lower())
        if song_artist:
            song_artist = normalize_text(song_artist.lower())

        # Find a match in the library
        fuzzy_matches = []
        for song in itunes_library().songs.values():
            normalized_name = normalize_text(song.name.lower())

            title_match = fuzz.ratio(normalized_name, song_title)
            # if title_match is less than 89, not close enough to consider
            if  title_match< 89:
                continue  #name of track is different, so move on

            # if title_match is less than 100 but greater than 89, we'll consider it *only* if we don't find an exact match.
            if title_match < 100:
                #save for potential futue consideration
                fuzzy_matches.append((song, title_match, False))
                continue  #and move on

            # If we get here,the title matches exactly.
            # If an artist was provided as well, we need to see if it also matches.
            if song_artist:
                # Artist for this song might be none
                normalized_artist = normalize_text(song.artist.lower()) if song.artist else None
                if not normalized_artist:
                    continue  #this song has no artist listed, so can't match

                artist_match = fuzz.ratio(normalized_artist, song_artist)
                if artist_match < 89:
                    continue
                if artist_match < 100:
                    fuzzy_matches.append((song, artist_match, True))
                    continue

            # if we hit this point, then we have matched both title and (if desired) artist.
            # this is the track we want, so set our search values to the cannonical name/artist and stop looking.
            song_title = song.name
            if song_artist:
                song_artist = song.artist
            break

        else:  # We get here, it means we found no exact match.
            # Take a fuzzy match (if any)
            if fuzzy_matches:
                # Take the "closest" match
                print("*******", fuzzy_matches)
                song = sorted(fuzzy_matches, key=sort_fuzzy)[-1][0]

                # if we hit this point, then we have a fuzzy match and (if desired) artist.
                # this is the track we want, so set our search values to the cannonical name/artist and stop looking.
                song_title = song.name
                if song_artist:
                    song_artist = song.artist

            else:  # We get here, it means we found no match.
                return_str = f"I can't find a song named {song_title}"
                if song_artist:
                    return_str += f" by {song_artist}"
                return return_str

        # We now have the canonical name/artist from the library,
        # so populate the script.
        script = script.format(title=song_title)
        if song_artist:
            script += f""" and artist is "{song_artist}" """
        script = create_playlist(script+")")

    try:
        run_script(script)
    except:
        error = f"Unable to find song {song_title}"
        if song_artist:
            error += f" by {song_artist}"
        return error

    return whats_playing("_")


@intent(['PlayAlbum'])
def play_album(intent_data):
    album_name=intent_data.get('slots', {}).get('album',{}).get('value')
    match=fuzzy_match(album_name,
                      {song.album for song in itunes_library().songs.values() if song.album is not None})
    if match is None:
        return f"I can't find any albums named {album_name}"
    else:
        album_name=match[0]

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

@intent(["QueueSong"])
def queue_song(intent_data):
    return "I'm sorry, but I can't do that yet"

    song_title=intent_data.get('slots', {}).get('title',{}).get('value')
    song_artist=intent_data.get('slots', {}).get('artist',{}).get('value')

    artist_matches=[] #default
    title_matches=fuzzy_match(song_title,
                              (song.name for song in itunes_library().songs.values()),
                              all_matches=True)
    print(title_matches)
    if title_matches and song_artist:
        artist_matches=fuzzy_match(song_artist,
                                  (song.artist for song in itunes_library().songs.values() if song.artist is not None and song.name in (x[0] for x in title_matches)))

    if (not song_artist and not title_matches) or (song_artist and not artist_matches):
        result=f"I can't find any songs named {song_title}"
        if song_artist:
            result+=f" by {song_artist}"
        return result

    if song_artist and artist_matches:
        song=next((song for song in itunes_library().songs.values() if song.name in (title[0] for title in title_matches) and song.artist==artist_matches[0]))

        script="""tell application "iTunes"
	repeat with thisTrack in {{item 1}} of (every file track of playlist "Library" whose name is "{title}" and artist is "{artist}")
		duplicate thisTrack to playlist "Alexa Selections"
	end repeat
        play
end tell
        """
        script=script.format(title=song.name, artist=song.artist)
        result=f"Added {song.name} by {song.artist}"
    else:
        song=next((song for song in itunes_library().songs.values() if song.name in (title[0] for title in title_matches)))

        script="""tell application "iTunes"
            repeat with thisTrack in {{item 1}} of (every file track of playlist "Library" whose name is "{title}")
                    duplicate thisTrack to playlist "Alexa Selections"
            end repeat
            play
    end tell
            """
        script=script.format(title=song.name)
        result=f"Added {song.name}"

    run_script(script)
    return result

@intent(['WhatsPlaying'])
def whats_playing(_):
    #Get the currently playing song/artist from iTunes
    script = """tell application "iTunes"
        set track_artist to the artist of the current track
        set track_title to the name of the current track
        log track_title & "," & track_artist
    end tell
    """
    result = run_script(script)

    song_title = song_artist = None
    try:
        song_title, song_artist = result.strip().split(",")
    except:
        if not song_title:
            song_title = "Unknown Song"
        if not song_artist:
            song_artist = "Unknown Artist"

    return f"Playing {song_title} by {song_artist}"
