import psycopg2
import pickle
import psycopg2
import json
import requests
import hmac
import tempfile

class herokudb:
    def __init__(self):
        self.dbconn = None

    def _get_cursor(self):
        self.dbconn = psycopg2.connect("dbname=<my_db_name> host=<my_postgres_host> port=5432 user=<my_user> password=<my_password> sslmode=require")

        return self.dbconn.cursor()

    def __enter__(self):
        return self._get_cursor()

    def __exit__(self, *args, **kwargs):
        if self.dbconn is not None:
            try:
                self.dbconn.close()
            except:
                print("Unable to close connection")


def lambda_handler(event, context):
    """ Route the incoming request to the proper endpoint based on user
    """

    user_id = event['session']['user']['userId']

    SQL = """INSERT INTO users (id, userid)
    VALUES (%s,%s)
    ON CONFLICT (userid) DO UPDATE
    SET userid=EXCLUDED.userid
    RETURNING endpoint,id"""

    response_data = {
        "version": "1.0",
        "sessionAttribtutes": {},
        "response": {
            "outputSpeech": {
                "type": "PlainText",
                },
            },
    }

    with herokudb() as cursor:
        good_local_id=False #failsafe
        while not good_local_id: 
            # Generate a local ID (may not be used)
            # Use the tempfile module to generate a random string
            local_id=tempfile.mkstemp()[1].split('/')[-1][3:]
            try:
                cursor.execute(SQL, (local_id, user_id, ))
            except IntegrityError: #We will only get this if the local_id conflicts but the user_id does not
                # The ON CONFLICT clause handles the case where the userid conflicts
                continue
            else:
                good_local_id=True
                
        endpoint, local_id = cursor.fetchone()
        print(f"Got endpoint {endpoint} for local id {local_id}")
        cursor.connection.commit()

    if endpoint is None:
        #Prompt the user to register an endpoint
        response_data['response']['outputSpeech']['text'] = """I didn't find an iTunes controller registered for you. I've sent a card to the Alexa app with the information you need to register your controller."""
        response_data['response']['card'] = {
            "type": "Simple",
            "title": "Register Your iTunes Controller",
            "content": f"1) Download the Alexa iTunes controller server from https://github.com/ibrewster/AlexaiTunes/archive/v0.1.zip on the Mac running iTunes and unzip it.\n2) Follow the directions in the README to set up the controller server.\n3) When you get to the configuration screen, enter the following userID:\n\n{local_id}",
        }
    else:
        # forward the request to the users endpoint server
        json_data = json.dumps(event).encode('UTF8')

        #create a signature with the data and a shared secret
        signature = hmac.new(b"<my_shared_secret>", json_data, 'SHA256').hexdigest()

        try:
            result = requests.post(endpoint, data=json_data,
                                   headers={'Signature': signature,})
        except requests.exceptions.ConnectionError:
            response_data['response']['outputSpeech']['text'] = "Unable to connect to iTunes controller. Please make sure the iTunes controller server is running and accessable from the internet."
            return response_data

        if result.status_code != 200:
            response_data['response']['outputSpeech']['text'] = "iTunes is not responding properly."

            # Send a card with the details
            response_data['response']['card'] = {
                "type": "Simple",
                "title": "Communication Error",
                "content": "The iTunes control server registered to your account is not responding properly. Please try restarting your iTunes control server and try your request again.",
            }
        else:
            # If we got a 200 response, then the response should be sutable for Alexa, just pass it back out
            return json.loads(result.text)
            
    print(response_data)
    return response_data

def register_server(event,context):
    print(event)


if __name__ == "__main__":
    lambda_handler({"session": {"application": {"applicationId": "application-1-2-3",},},},
                   None)