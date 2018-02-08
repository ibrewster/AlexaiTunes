#!/bin/bash

echo "Welcome to the Alexa iTunes Control Server installer!"
echo "This installer will set up this software on your machine." 
echo "Depending on what needs to happen, you may be asked for your password"
echo "This install depends on python3.6 or later, which you can download"
echo "and install from https://www.python.org/downloads/"
echo ""
echo "This will make sure you have an install of pip and virtualenv at the"
echo "system level, then install the required modules to run this software"
echo "into a virtualenv within this folder"
echo ""
echo -n "Would you like to continue? [y/n]: "
RUN="maybe"
read RUN
while [ "$RUN" != 'y' ]  && [ "$RUN" != 'n' ] && [ "$RUN" != 'Y' ] && [ "$RUN" != 'N' ]; do
    echo -n "Invalid option. Please enter y or n. Would you like to continue? [y/n]: "
    read RUN
done

if [ "$RUN" != 'Y' ] && [ "$RUN" != 'y' ]; then
    exit 2
fi

#Make sure we are running from the script directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# check for python 3
echo -n "Checking for python3.6 install..."
which python3
if [ $? -ne 0 ]; then
    echo "Failed"
    echo "No python 3.6 install detected. Please download and install python 3.6 or higher from https://www.python.org/downloads/ and try setup again"
    exit 1
fi
echo "OK"

#Make sure the python3 bin directory is in the path
PATH=$PATH:`python3-config --prefix`/bin

echo -n "Checking for XCode command line tools install..."
xcode-select --install 2>/dev/null
if [ $? -eq 0 ]; then
  echo "Failed"
  echo "Installing this package requires the xcode command line tools"
  echo "Please run the install, then try setup again"
  exit 1
fi
echo "OK"

echo -n "Checking for virtualev install..."
virtualenv=`which virtualenv`
if [ $? -ne 0 ]; then
    echo "Failed"
    echo -n "Checking for pip3 install..."
    which pip3
    if [ $? -ne 0 ]; then
        echo "Failed"
        echo -n "Checking for easy_install-3.6...."
	which easy_install-3.6
	if [ $? -ne 0 ]; then
	    echo "Failed"
            echo "Unable to find a valid Python 3 enviroment. Please download and install python 3.6 or higher from https://www.python.org/downloads/ and try setup again"
	    exit 1
	fi
	echo "Installing pip using easy_install..."
	sudo easy_install-3.6 pip
    fi
    echo "Installing virtualenv using pip3"
    sudo pip3 install virtualenv
    virtualenv=`which virtualenv`
fi

echo "OK"
# Set up a virtualenv
echo "Creating virtualenv"
$virtualenv --python=python3 env
echo "activating virtualenv..."
source env/bin/activate
echo "Installing libpytunes in virtualenv"
cd install
/usr/bin/unzip libpytunes.zip
cd libpytunes-master
python3 setup.py install
cd ../
rm -r libpytunes-master
cd ../
echo "`which python`"
echo "Installing other dependancies..."
pip3 install -r install/requirements.txt

echo -n "Setting paths..."
sed -i .dist "2s+.*+app_path = $DIR+" iTunesControl.ini
echo -e "[iTunes]\nxmllocation = /Users/`whoami`/Music/iTunes/iTunes Music Library.xml" > ControlServerConfig.ini
echo "OK"
echo -n "Creating log directory..."
sudo mkdir -p /var/log/iTunesControl
sudo chmod 777 /var/log/iTunesControl
sudo chmod 777 /var/run
echo "OK"
echo "Installation complete. Starting server..."
env/bin/uwsgi iTunesControl.ini
echo "Server started."
echo ""
echo "Your install of the Alexa iTunes Control server is now ready to accept commands."
echo "Please open a browser window and navigate to http://localhost:4380 to set up"
echo "your iTunes library path (if different than default) and register this server"
echo "with your Alexa account using the user ID provided by your Alexa"
echo ""
echo "If you have not yet been given a user ID, please say 'Alexa, open iTunes' and "
echo "Alexa will send a card to your phone with the required information"
open http://localhost:4380
