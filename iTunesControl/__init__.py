from threading import Timer
from libpytunes import Library
import flask
import signal
import uwsgi

itunes_library = None
iTunes_update_timer = None

def update_iTunes_library():
    global itunes_library
    global iTunes_update_timer
    itunes_library = Library("/Media/iTunes/iTunes Library.xml")

    # Update once a minute (roughly)
    iTunes_update_timer = Timer(60, update_iTunes_library)
    iTunes_update_timer.daemon = True
    iTunes_update_timer.start()

def shutdown(*args, **kwargs):
    iTunes_update_timer.cancel()

app = flask.Flask(__name__)

update_iTunes_library()
uwsgi.atexit = shutdown


from . import main