import flask
import requests
import subprocess
from time import sleep
from . import app, get_tun_url, config, ngrok
from . import itunes_library, register_public, get_iTunes_lib

@app.route("/")
def index():
    if itunes_library() is not None:
        num_tracks = len(itunes_library().songs)
        num_playlists = len(itunes_library().getPlaylistNames())
    else:
        num_tracks = "Unknown"
        num_playlists = "Unknown"

    args = {
        'numtracks': num_tracks,
        'numplaylists': num_playlists,
        'xmlloc': config["iTunes"].get("xmllocation",
                                 "~/Music/iTunes/iTunes Music Library.xml"),
        'userid': config["Alexa"].get("UserID", ''),
    }
    return flask.render_template("setup.html", **args)

@app.route("/setngrok", methods=["POST"])
def set_ngrok():
    ngrok_token = flask.request.form.get('authtoken')
    if ngrok_token is None:
        return flask.jsonify({'success': False, 'error': 'No Token Provided',})

    # Register token with ngrok
    try:
        subprocess.check_call(['./ngrok', 'authtoken', ngrok_token])
    except subprocess.CalledProcessError:
        return flask.jsonify({'success': False, 'error': 'Unable to register with ngrok',})

    #restart the ngrok tunnel
    global ngrok
    ngrok.terminate()
    ngrok.communicate()  #wait for process to finish
    ngrok=subprocess.Popen(['./ngrok','http','4380'],stdout=subprocess.DEVNULL)

    # Re-register the new ngrok tunnel endpoint
    #give the tunnel 3 seconds to establish before checking
    sleep(3)
    register_public()

    return flask.jsonify({'success': True,})

@app.route("/setitunes", methods=["POST"])
def set_iTunes():
    itunes_lib_path = flask.request.form.get('xmlloc')
    if itunes_lib_path is None:
        return flask.jsonify({'success': False, 'error': 'No Path Provided'})

    #Save the updated variable
    config['iTunes']['xmllocation'] = itunes_lib_path
    with open('ControlServerConfig.ini', 'w') as configfile:
        config.write(configfile)

    get_iTunes_lib()
    if itunes_library() is None:
        return flask.jsonify({"success": False, "error": "Unable to load iTunes Library. Check path and that the file exists",})

    result = {"success": True,
              "tracks": len(itunes_library().songs),
              "playlists": len(itunes_library().getPlaylistNames()),}

    return flask.jsonify(result)

@app.route("/setuserid", methods=["POST"])
def register_endpoint():
    user_id = flask.request.form.get('userid')
    if not user_id:
        return flask.jsonify({'success': False, 'error': 'No User ID provided',})

    endpoint = get_tun_url()
    if not endpoint:
        return flask.jsonify({'success': False,
                              'error': 'Unable to get public URL',})
    # Save the userid to the config
    config['Alexa']['userid'] = user_id
    with open('ControlServerConfig.ini', 'w') as configfile:
        config.write(configfile)

    reg_result = register_public()
    return flask.jsonify(reg_result.json())