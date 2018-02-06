from time import sleep
from threading import Thread
from libpytunes import Library
import flask
import signal
import uwsgi
import subprocess
import configparser
import requests

_itunes_library = None

itunes_library = lambda:_itunes_library

#Load the config (if any)
config = configparser.ConfigParser()
config.read('ControlServerConfig.ini')

#make sure it is initalized properly
if not 'iTunes' in config:
  config['iTunes'] = {}

if not 'Alexa' in config:
  config['Alexa'] = {}

# and save for good measure
with open('ControlServerConfig.ini', 'w') as configfile:
  config.write(configfile)

# Open a tunnel for external access
ngrok=subprocess.Popen(['./ngrok','http','4380'],stdout=subprocess.DEVNULL)

#Get the public URL
def get_tun_url():
  tuninfo=requests.get('http://localhost:4040/api/tunnels/command_line')
  if tuninfo.status_code != 200:
    return None
  pub_url = tuninfo.json()['public_url']
  return pub_url

def get_iTunes_lib():
  global _itunes_library
  # Read in the libary location
  lib_loc = config["iTunes"].get("xmllocation",
                                 "~/Music/iTunes/iTunes Library.xml")
  "/Media/iTunes/iTunes Library.xml"
  try:
    _itunes_library = Library(lib_loc)
  except FileNotFoundError:
    print(f"Unable to load iTunes library: File ({lib_loc}) not found.")
    _itunes_library = None

def update_itunes_library():
  while True:
    get_iTunes_lib()
    # Wait 5 minutes, then run again.
    sleep(300)

def shutdown(*args, **kwargs):
  print("Killing ngrok process")
  ngrok.kill()

update_thread = Thread(target=update_itunes_library, daemon=True)
update_thread.start()
uwsgi.atexit = shutdown

app = flask.Flask(__name__)

def register_public():
  pub_url = get_tun_url()
  print(f"Registering tunnel URL of {pub_url}/alexa")
  if pub_url is None:
    return

  pub_url += '/alexa'

  # See if we have a user ID
  user_id = config['Alexa'].get('userid')
  if user_id is None:
    return

  api_key = "NMyRWLYVIyP5GNKIlNVa5VmJRLEomed8T10QS1hg"
  URL = "https://pvtiqtwqc8.execute-api.us-east-1.amazonaws.com/prod/RegisterAlexaTunes"
  reg_result = requests.post(URL,
                               json={'userid': user_id,
                                     'endpointurl': pub_url,},
                               headers={'x-api-key': api_key,})

  print(f"Registered URL {pub_url} to user {user_id} with result {reg_result.text}")
  return reg_result

#give the tunnel 3 seconds to establish before checking
sleep(3)
register_public()

from . import main
from . import control