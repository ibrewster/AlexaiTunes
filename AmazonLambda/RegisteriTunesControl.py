import psycopg2

class herokudb:
    def __init__(self):
        self.dbconn = None

    def _get_cursor(self):
        self.dbconn = psycopg2.connect("dbname=<my_db> host=<my_db_host> port=5432 user=<my_db_user> password=<my_db_password> sslmode=require")

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
    user=event.get('userid')
    endpoint=event.get('endpointurl')
    if user is None or endpoint is None:
        result={
            'success':False,
            'error':'Missing user or endpoint',
            'user':user,
            'endpoint':endpoint,
            'event':event
        }
        return result

    SQL = "UPDATE users SET endpoint=%s WHERE id=%s"
    with herokudb() as cursor:
        cursor.execute(SQL, (endpoint, user))
        updated = cursor.rowcount
        cursor.connection.commit()

    result={
        "success":True if updated > 0 else False,
        'error': 'Unable to update endpoint - user ID not found',
        'endpoint':endpoint,
        'user':user
    }
    return result
