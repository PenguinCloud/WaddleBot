from flask import Flask, render_template, request
from dotenv import load_dotenv
import os
import requests
import logging

app = Flask(__name__)

# set the logging level
logging.basicConfig(level=logging.INFO)

load_dotenv()

# Load the environment variables

# Check if the gateway activate url is set
if not os.getenv('GATEWAY_ACTIVATE_URL'):
    raise Exception('GATEWAY_ACTIVATE_URL not found in .env file')

# Load the gateway activate url
gateway_activate_url = os.getenv('GATEWAY_ACTIVATE_URL')

# Function to activate a gateway through a given activation key
def activate_gateway(activation_key: str) -> dict:
    try:
        # Send a request to the gateway activate url
        response = requests.post(gateway_activate_url, json={'activation_key': activation_key})

        # Get the response as json
        response = response.json()

        # Print the response
        logging.info("Response:")
        logging.info(response)

        # Check if the request was successful
        if 'status' in response and response['status'] != 200:
            msg = "Failed to activate gateway."
            if 'msg' in response:
                msg = response['msg']

            return {'error': msg}

        # Return the response
        return response
    except Exception as e:
        # Log the exception
        logging.error(e)

        # Return an error message
        return {'error': 'Failed to activate gateway'}

@app.route('/')
def authenticate():
    try:
        # Get the activation key from the request, as the state param
        activation_key = request.args.get('state')

        # Print all the request parameters
        logging.info(request.args)

        # Check if the activation key is not set
        if not activation_key:
            return render_template('activate_failed.html')
        
        # Activate the gateway
        response = activate_gateway(activation_key)

        # Check if there was an error
        if 'error' in response:
            return render_template('activate_failed.html')
        
        # Return the response
        return render_template('activate_success.html')
    except Exception as e:
        # Log the exception
        logging.error(e)

        # Return an error message
        return render_template('activate_failed.html')

if __name__ == '__main__':
   app.run(debug=True, host='0.0.0.0', port=17563)