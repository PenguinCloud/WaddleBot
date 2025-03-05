# WaddleBot Twitch Authenticator

This authenticator contains the redirect endpoint to activate a user through a given activation key.

# Basic Setup

## 1. Python local testing

To test the API without it being in a container, do the following:

1. Ensure that you have python installed on your local machine, preferably v3.12. 
Download link: (https://www.python.org/downloads/)
To check if its installed correctly, run the following command in the terminal:

`py --version`

If its installed correctly, you will see this output:

`Python 3.12.3`

2. Install the python virtual environment in the root folder of the project by typing:

`py -m venv ./venv`

3. Activate the virtual environment by running:

`venv\scripts\activate.bat`

4. Install the requirements of the script by running:

`pip install -r requirements.txt`

5. Ensure the following environmental variables are available:

`
GATEWAY_ACTIVATE_URL
`

6. Run the app by running the following command while having the virtual env active:

`py app.py`