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

echo -n "Please enter the directory into which you would like to install this program [/Applications/iTunesControl]:"
read INSTALL_DIR
if [ -z $INSTALL_DIR ]; then
    INSTALL_DIR="/Applications/iTunesControl"
fi

DIR=$INSTALL_DIR
echo "Creating install directory $DIR..."
sudo mkdir -p $DIR
if [ $? -ne 0 ]; then
    echo "**********ERROR********"
    echo "Unable to create install directory"
    exit 3
else
    sudo chown `whoami` $DIR
    echo "OK"
fi

cd "$DIR"

# check for python 3
echo -n "Checking for python3.6 install..."
which python3
if [ $? -ne 0 ]; then
    echo "Failed"
    echo ""
    echo "No python 3.6 install detected. I can install it for you using Homebrew"
    echo "(https://brew.sh) if desired, or you can manually download it from"
    echo "https://www.python.org/downloads/ and install it yourself."
    echo -n "Would you like me to attempt an automatic install? [y/n]:"
    
    RUN="maybe"
    read RUN
    while [ "$RUN" != 'y' ]  && [ "$RUN" != 'n' ] && [ "$RUN" != 'Y' ] && [ "$RUN" != 'N' ]; do
        echo "Invalid option. Please enter y or n." 
        echo -n "Would you like to attempt automatic install? [y/n]: "
        read RUN
    done

    if [ "$RUN" != 'Y' ] && [ "$RUN" != 'y' ]; then
        echo "*************ERROR****************"
        echo "No python 3.6 install detected. Please download and install python 3.6 or higher"
        echo "from https://www.python.org/downloads/ and try setup again"
        exit 1
    fi
    
    echo -n "Checking for brew install..."
    which brew
    if [ $? -ne 0 ]; then
        #run homebrew installer
        /usr/bin/ruby -e "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/master/install)"
    else
        echo "OK"
    fi
    
    echo "Installing python 3 via homebrew..."
    brew install python3
    echo -n "Checking for python3.6 install..."
    which python3
    if [ $? -ne 0 ]; then
        echo "****************ERROR*********************"
        echo "Unable to find python3 after brew install." 
        echo "Automatic install attempt apparently failed. "
        echo "Please download and install python 3.6 or higher"
        echo "from https://www.python.org/downloads/ and try setup again"
        exit 1
    fi
else
    echo "OK"
fi


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

echo -n "Cloning repository to $DIR..."
git clone https://github.com/ibrewster/AlexaiTunes.git $DIR

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
# Set the path to the application in the uwsgi ini file
sed -i .dist "2s+.*+app_path = $DIR+" iTunesControl.ini
# Set the default path to the iTunes music library XML file
echo -e "[iTunes]\nxmllocation = /Users/`whoami`/Music/iTunes/iTunes Music Library.xml" > ControlServerConfig.ini
# Write and place the launchd script
sed "s+{{DIR}}+$DIR+g" install/com.brewstersoft.alexaitunescontrol.plist > ~/Library/LaunchAgents/com.brewstersoft.alexaitunescontrol.plist
echo "OK"
if [ ! -f "/Users/`whoami`/Music/iTunes/iTunes Music Library.xml" ]; then
    echo "***********************WARNING************************"
    echo "* iTunes music library xml file not detected. Please *"
    echo "* make sure to check the \"Share iTunes Library XML   *"
    echo "* with other applications\" option is checked in the *"
    echo "* iTunes advanced preferences, and that the path to  *"
    echo "* the xml file is set correctly in the Alexa iTunes  *"
    echo "* control server setup window.                       *"
    echo "******************************************************"
fi
echo -n "Creating log directory..."
sudo mkdir -p /var/log/iTunesControl
sudo chmod 777 /var/log/iTunesControl
sudo chmod 777 /var/run
echo "OK"
echo "Installation complete. Starting server..."
#env/bin/uwsgi iTunesControl.ini
launchctl load ~/Library/LaunchAgents/com.brewstersoft.alexaitunescontrol.plist
echo "Server started."
echo ""
echo "Your install of the Alexa iTunes Control server is now ready to accept commands."
echo "Please open a browser window and navigate to http://localhost:4380 to set up"
echo "your iTunes library path (if different than default) and register this server"
echo "with your Alexa account using the user ID provided by your Alexa"
echo ""
echo "If you have not yet been given a user ID, please say 'Alexa, open My Computer' and "
echo "Alexa will send a card to your phone with the required information"
open http://localhost:4380
