import asyncio
import logging
import os
import re
import requests
import threading
import time
from asyncio import sleep
from dataclasses import asdict, commandData, contextData, identityData, marketplaceModuleData, messageData, sendMessageData, sessionData
from dotenv import load_dotenv
from pydal import DAL, Field
from pycord import The_Waddler
from redis_cache import RedisCache
from urllib.parse import quote, quote_plus, urlencode


# Set the logging level to INFO
logging.basicConfig(level=logging.INFO)


waddler_token = os.getenv('WADDLER_TOKEN')
waddler_context = os.getenv('PYCORD_GET_COTEXT')
waddler_commands = os.getenv('PYCORD_GET_COMMANDS')
waddler_identity = os.getenv('PYCORD_ADD_IDENTITY')

# Matterbridge API URL to manage messages
matterbridgeURL = os.getenv('MATTERBRIDGE_URL')

# User manager API URL to add users to the database
userManagerURL = os.getenv('USER_MANAGER_URL')

# Marketplace API URL to manage the marketplace
marketplaceURL = os.getenv('MARKETPLACE_URL')

# Community Modules API URL to manage community modules to get the community modules
communityModulesURL = os.getenv('COMMUNITY_MODULES_URL')

# Initial context API URL to set the initial context of new users to the database.
contextURL = os.getenv('CONTEXT_URL')

# Commands API URL to get the commands from the database
commandsURL = os.getenv('COMMANDS_URL')

# Redis parameters
redisHost = os.getenv('REDIS_HOST')
redisPort = os.getenv('REDIS_PORT')

class WaddleBotListener:
    def __init__(self, matterbridgeGetURL: str = None, matterbridgePostURL: str = None, 
                 contextURL: str = None, redisHost: str = None, redisPort: int = 6379, marketplaceURL: str = None, 
                 communityModulesURL: str = None, commandsURL: str = None) -> None:
        # Initialize the variables
        self.matterbridgeGetURL = matterbridgeGetURL
        self.matterbridgePostURL = matterbridgePostURL
        self.marketplaceURL = marketplaceURL
        self.communityModulesURL = communityModulesURL
        self.commandsURL = commandsURL

        self.initialContextURL = f"{contextURL}initialize_user/"
        self.getContextURL = f"{contextURL}get_by_identity_name/"

        # Initialize the Redis Manager
        self.redisManager = RedisCache(redisHost, redisPort)

        
    # Function to listen for messages
    async def listen(self) -> None:
        # TODO: When the Redis cache is implemented, remove the below execution of the add_test_commands function
        # Add the test commands to the Redis cache
        logging.info("Adding test commands to Redis....")
        # self.redisManager.get_all_commands()
        self.redisManager.init_commands(self.commandsURL)

        logging.info("Listening for messages....")

        while True:
            # Check if the matterbridge API is reachable
            resp = None

            try: 
                resp = requests.get(self.matterbridgeGetURL)
            except requests.exceptions.RequestException as e:
                logging.error(e)
                logging.error("An error has occurred while trying to communicate with the API. Retrying in 1 second....")
                await asyncio.sleep(1)
                continue

            

            if resp is not None and resp.ok:
                messageData = resp.json()

                # Check if the message data is not empty
                if len(messageData) > 0:
                    username = None

                    # Create a user if the user does not exist
                    if 'username' in messageData[0]:
                        username = messageData[0]['username']
                        self.add_identity(username)

                    if 'text' in messageData[0] and 'gateway' in messageData[0]:
                        gateway = messageData[0]['gateway']
                        message = messageData[0]['text']
                        channel = messageData[0]['channel']
                        account = messageData[0]['account']

                        if "!" in message and message[0] == "!" or "#" in message and message[0] == "#":
                            # If a command is found in the message, execute the command in its own thread
                            logging.info("Starting thread....")

                            t = threading.Thread(target=self.execute_command_from_message, args=(username, message, channel, gateway, account, messageData), daemon=True).start()
                        else:
                            logging.info("No command tag found in message.")
                    else:
                        logging.error("Error occured while processing the message. Either the 'gateway' or the 'text' attributes are missing.")

                    logging.info("Message processed. Waiting for next message....")
            else:
                logging.error("An error has occurred while trying to communicate with the API.")


            await asyncio.sleep(1)

    # Function that executes the command from the message
    def execute_command_from_message(self, username: str, message: str, channel: str, gateway: str, account: str, messageData: messageData) -> None:
        # Seperate the command from the message as the first item in the list
        msgCommands = message.split(" ")

        mainCommand = msgCommands[0]

        # If the command "timeout" is in the commandlist, run a timeout. Ensure that the timeout command is 
        # written as "timeout:<time in seconds>". There should be no spaces between the colon and the time.
        matching = [s for s in msgCommands if "timeout" in s]
        if len(matching) > 0:
            timeoutTime = 0
            timeoutValues = matching[0].split(":")

            logging.info(f"Timeout values: {timeoutValues}")

            if len(timeoutValues) > 1 and timeoutValues[1] != "":
                timeoutTime = timeoutValues[1]

                logging.info(f"Timeout command found. Timeout time: {timeoutTime} seconds.")

                asyncio.sleep(int(timeoutTime))

                logging.info("Timeout completed. Executing the command....")
            else:
                # If the timeout time is not specified, set the timeout time to 0 and send a message to the user, stating
                # that the timeout time was not specified correctly.
                self.send_bot_message(gateway, 'The timeout time was not specified correctly. Please specify the timeout time in seconds. Example: "!command timeout:5"', account)

                return
            # After the timeout, remove the timeout command from the message
            message = message.replace(matching[0], "")

        # Get the context data of the user
        context_data = self.get_context_data(username, gateway, account)
        if context_data is None:
            return
        
        # Get the command list from the message
        commands = self.get_commands(message)

        # Process the command
        cmdResult = self.process_command(commands, context_data, message, username, channel, account, messageData)

        self.send_bot_message(gateway, cmdResult, account) 

    # Function to get the context of the user
    def get_context_data(self, username, gateway, account):
        context_data = self.get_context(username)
        if context_data is None:
            self.send_bot_message(gateway, "An error has occurred while trying to get the context data of the user.", account)
            return None
        return context_data

    # Function to process the command
    def process_command(self, commands, context_data, message, username, channel, account, messageData):
        main_command = commands[0]
        if main_command == "!help":
            return self.display_help()

        module = self.lookup_command(commands, username)
        if module is None:
            return "The command could not be found. Ensure that the command is typed correctly."

        return self.execute_command(
            username=username,
            contextData=context_data,
            message=message,
            commandData=module,
            moduleId=module['module_id'],
            moduleTypeName=module['module_type_name'],
            sessionData=messageData[0]['session_data'],
            priv_list=messageData[0]['priv_list']
        )

    # Function to lookup the command in the Redis cache
    def lookup_command(self, commands, username):
        command_name = self.redisManager.get_command(commands[0])
        if command_name is None:
            command_name = " ".join(commands)

        module = self.get_marketplace_module_by_name(command_name, username)
        if module is None or ('status' in module and module['status'] != 200):
            return None

        aliased_commands = self.get_aliased_command(module, commands)
        return self.get_command_properties(aliased_commands, module)

    # Function to get the command from the message
    def get_commands(self, message: str) -> list:
        logging.info("Getting the command from the message....")

        commands = []

        # Remove all strings from the message that fall between the [ ] brackets or the < > brackets
        message = re.sub(r'\[.*?\]', '', message)
        message = re.sub(r'\<.*?\>', '', message)

        # Get the first word from the message
        commands = message.split(" ")

        # Remove all strings from the list that fall between the [ ] brackets or the < > brackets
        commands = [x for x in commands if "[" not in x and "]" not in x and "<" not in x and ">" not in x]

        filteredCommands = []
        if len(commands) > 0:
            for command in commands:
                if command != "":
                    filteredCommands.append(command)

        logging.info(f"The command list is:")
        logging.info(filteredCommands)

        return filteredCommands
    
    # Function to get the aliased command from a marketplace module and return a list of commands,
    # seperated by a space. Returns a list of the old commands if the aliased command is not found.
    def get_aliased_command(self, module: marketplaceModuleData, commands) -> list:
        if not module or not hasattr(module, 'aliased_command'):
            logging.warning("Invalid module or missing 'aliased_command'")
            return commands
        logging.info("Getting the aliased command....")

        aliasedCommand = commands

        # Get the aliased command from the module
        if module is not None and 'aliased_command' in module:
            aliasedCommand = module['aliased_command'].split(" ")

        return aliasedCommand
    
    # Function to get the command parameters from the message, that fall between the < > brackets
    def get_message_params(self, message: str) -> list:
        logging.info("Getting the command parameters from the message....")

        # Get the command parameters from the message
        params = re.findall(r'\<(.*?)\>', message)

        return params
    
    # Function to get the payload values from the message, that fall between the [ ] brackets
    def get_payload_values(self, message: str) -> list:
        logging.info("Getting the payload values from the message....")
        logging.info(f"Message: {message}")

        # Find all occerences of the strings that fall between their own [ ] brackets
        values = re.findall(r'\[(.*?)\]', message)

        # If the values are is empty, return a list with only a singular empty string
        if len(values) == 0:
            values = []

            return values

        return values
    
    # Function to get the function parameters from a command retrieved from redis
    def get_function_params(self, commandData: commandData) -> list:
        logging.info("Getting the function parameters from the command....")

        params = []
        # Get the function parameters from the command
        if commandData is not None and 'parameters' in commandData and len(commandData['parameters']) > 0:
            params = commandData['parameters']
        else:
            params = None

        return params

    # Function to get the payload keys from a command retrieved from redis
    def get_payload_keys(self, commandData: commandData) -> list:
        logging.info("Getting the payload keys from the command....")

        keys = []
        # Get the payload keys from the command
        if commandData is not None and 'payload_keys' in commandData:
            keys = commandData['payload_keys']
        else:
            keys = None

        return keys
    
    # Function to get the action from the command data
    def get_action(self, commandData: commandData) -> str:
        logging.info("Getting the action from the command data....")

        action = ""
        # Get the action from the command data
        if commandData is not None and 'action' in commandData:
            action = commandData['action']

        return action
    
    # Function to create a function URL with parameters by adding the parameters to the URL
    def create_function_url(self, action: str, params: list) -> str:
        logging.info("Creating the function URL....")

        url = f"{action}"

        # Add the parameters to the URL
        for param in params:
            # Check if the parameter starts with a # character. If it does, replace the first character with %23.
            if param[0] == "#":
                param = "%23" + param[1:]

            url += f"/{param}"

        return url
    
    # Function to create a function payload that contains the identity_name, community_name, and command_string
    def create_function_payload(self, command_string: str, identity_name: str, community_name: str) -> dict:
        logging.info("Creating the function payload....")

        # Create the payload dictionary
        payload = {}

        # Add the identity_name, community_name, and command_string to the payload
        payload['identity_name'] = identity_name
        payload['community_name'] = community_name
        payload['command_string'] = command_string

        return payload
    
    # Function to check if a given community module exists in a given community, using the module id and the community id
    def check_community_module_exists(self, community_id: int, module_id: int) -> bool:
        logging.info("Checking if the community module exists....")

        # Create the function URL
        url = f"{self.communityModulesURL}{community_id}/{module_id}"

        resp = None

        try:
            resp = requests.get(url=url)
        except requests.exceptions.RequestException as e:
            logging.error(e)
            return False

        if resp is not None and resp.ok:
            respJson = resp.json()

            if 'msg' in respJson and respJson['msg'] is not None:
                return False
            elif "community_module" in respJson:
                return True
        else:
            return False

    # Function to check if the given module type of a command is a core module
    def check_core_module(self, moduleType: str) -> bool:
        logging.info("Checking if the module is a core module....")

        if moduleType == "Core":
            return True
        else:
            return False
        
    # Function to check if a given module exists in a given community, using the module id and the community id
    def check_module_exists(self, community_id: int, module_id: int) -> bool:
        logging.info("Checking if the module exists....")

        # Create the function URL
        url = f"{self.communityModulesURL}{community_id}/{module_id}"
        logging.info(f"THE URL TO GET THE MODULE IS: {url}")

        resp = None

        try:
            resp = requests.get(url=url)
        except requests.exceptions.RequestException as e:
            logging.error(e)
            return False

        if resp is not None and  resp.ok:
            respJson = resp.json()

            if 'msg' in respJson and respJson['msg'] is not None:
                return False
            else:
                return True
        else:
            return False

    # Function to get the context of the current user
    def get_context(self, username: str) -> contextData:
        logging.info("Getting the context....")

        # Create the function URL
        url = f"{self.getContextURL}"

        # Create the payload
        payload = {"identity_name": username}

        resp = None

        try:
            resp = requests.get(url=url, json=payload)
        except requests.exceptions.RequestException as e:
            logging.error(e)
            return None

        if resp is not None and resp.ok:
            respJson = resp.json()

            if 'msg' in respJson and respJson['msg'] is not None:
                return None
            # Return the data if the data is in the response
            elif "data" in respJson and "community_name" in respJson["data"] and "community_id" in respJson["data"]:
                return respJson["data"]
        else:
            return None


    # Function to execute a command from the Redis cache, given the message command and the command data
    def execute_command(self, username: str, contextData: contextData, message: str, commandData: commandData, moduleId: int, moduleTypeName: str, sessionData: sessionData, priv_list: list) -> str:
        logging.info("Executing the command....")

        # Get the action value from the metadata
        action = commandData['action']
        
        community_name = contextData['community_name']

        # Check if the user has the required priv_list to execute the command
        if not self.check_permissions(sessionData, contextData, commandData, priv_list):
            return "You do not have the required privileges to execute this command."

        # Get the command parameters from the message
        params = self.get_message_params(message)
        
        # Check if the module_type_name is in the command data. After that, check if the module is a core module. If it is a core module
        # then execute the command. If it is not a core module, check if the module exists in the community. If it does, execute the command.
        # If it does not, return a message saying that the module does not exist in the community.
        if moduleTypeName is not None:
            if self.check_core_module(moduleTypeName):
                logging.info("The module is a core module.")
            else:
                logging.info("The module is not a core module.")
                
                # Check if the module exists in the current community context of the user
                if self.check_module_exists(community_name, moduleId):
                    logging.info("The module exists in the community.")
                else:
                    logging.info("The module does not exist in the community.")
                    return "The module does not exist in the community. Please install it first."

        # Get the command description from the command meta data
        description = ""
        if 'description' in commandData:
            description = commandData['description']

        # Create the function URL
        url = self.create_function_url(action, params)

        # Create the function payload
        payload = self.create_function_payload(identity_name=username, community_name=community_name, command_string=message)

        logging.info(f"URL: {url}")
        logging.info(f"Payload: {payload}")

        resp = None

        # Execute the function, depending on the method
        if commandData['method'] == "GET":
            logging.info("Executing GET Method")
            try:
                resp = requests.get(url=url, json=payload)
            except requests.exceptions.RequestException as e:
                logging.error(e)
                return "An error has occurred while trying to execute the command."
        elif commandData['method'] == "POST":
            logging.info("Executing POST Method")
            try:
                resp = requests.post(url=url, json=payload)
            except requests.exceptions.RequestException as e:
                logging.error(e)
                return "An error has occurred while trying to execute the command."
        elif commandData['method'] == "PUT":
            logging.info("Executing PUT Method")
            try:
                resp = requests.put(url=url, json=payload)
            except requests.exceptions.RequestException as e:
                logging.error(e)
                return "An error has occurred while trying to execute the command."
        elif commandData['method'] == "DELETE":
            logging.info("Executing DELETE Method")
            try:
                resp = requests.delete(url=url, json=payload)
            except requests.exceptions.RequestException as e:
                logging.error(e)
                return "An error has occurred while trying to execute the command."

        if resp is not None and resp.ok:
            respJson = resp.json()

            msg = ""
            # Convert the response data to a string
            if 'msg' in respJson and respJson['msg'] is not None:
                msg = respJson['msg']
            elif "data" in respJson:
                msg = self.data_to_string(respJson["data"])
            
            logging.info(msg)
            return msg
        else:
            msg = f"An error has occurred while trying to execute the command. Command description: {description}. Error: {resp.text}"
            logging.error(msg)
            return msg

    # Function to send a bot message
    def send_bot_message(self, gateway: str, command: str, account: str) -> None:
        logging.info("Sending Bot Message....")

        try:
            payload = sendMessageData(text=command, username="Waddle Bot", gateway=gateway, account=account)

            resp = requests.post(url=self.matterbridgePostURL, json=asdict(payload))

            if resp.ok:
                logging.info("BOT Message Successfully Sent!")
        except requests.exceptions.RequestException as e:
            logging.error(e)
            logging.error("An error has occurred while trying to send the bot message.")

    # Function to add an identity (User) to the database
    def add_identity(self, username : str) -> None:
        logging.info("Adding Identity....")

        try:
            payload = identityData(identity_name=username)

            resp = requests.post(url=self.initialContextURL, json=asdict(payload))

            if resp.ok:
                msg = ""
                if 'msg' in resp.json():
                    msg = resp.json()['msg']
                logging.info(msg) 
        except requests.exceptions.RequestException as e:
            logging.error(e)
            logging.error("An error has occurred while trying to add the identity.")
        

    # Function to turn a data dictionary response from a request into a string
    def data_to_string(self, data: dict) -> str:
        logging.info("Converting Data to String....")
        logging.info("The given data:")
        logging.info(data)

        # Convert the data dictionary to a string
        dataStr = ""
        if len(data) > 0:
            for count in range(len(data)):
                for key in data[count]:
                    dataStr += f"{key}: {data[count][key]}\n"

        return dataStr

    # Function to display the help message, containing all the associated commands from Redis
    def display_help(self) -> str:
        logging.info("Displaying Help Message....")

        keys = self.redisManager.get_all_keys()

        helpMessage = "Available Commands:\n"

        # Loop through the commands and display the command and its description.
        for key in keys:
            # Remove the _ character from the command key
            command = key.replace("_", " ")
            helpMessage += f"{command}\n"


        return helpMessage
    
    # Function to retrieve a marketplace module entry by its URL
    def get_marketplace_module_by_name(self, moduleName: str, identity_name: str) -> marketplaceModuleData:
        logging.info("Getting Marketplace Module by URL....")

        try:
            logging.info(f"Module Name: {moduleName}")

            callURL = self.marketplaceURL

            logging.info(f"Call URL: {callURL}")

            # Create a body for the request that only contains the identity_name
            body = {
                "identity_name": identity_name,
                "name": moduleName
            }

            logging.info(f"Body: {body}")

            resp = requests.get(url=callURL, json=body)

            if resp.ok:
                response = resp.json()

                return response
            else:
                return None
        except requests.exceptions.RequestException as e:
            logging.error(e)
            return None
        
    # A function that accepts a string list, loops through each string and checks if they are present within one another in a given metadata object, and returns the command properties
    def get_command_properties(self, commandlist: list, metadata: dict) -> commandData:
        logging.info("Getting Command Properties....")

        logging.info(f"Command List: {commandlist}")
        logging.info(f"Metadata: {metadata}")

        # Combine all the commands into a single string with the _ character. This will be used to search for the command in the metadata.
        command = "_".join(commandlist)

        logging.info(f"Command that needs to be found in the metadata: {command}")

        # Check if the command is in the metadata
        if command in metadata:
            return metadata[command]
        else:
            return None
    
    # Function to return a flag depending on whether the given admin command can be excuted or not. 
    # For this check to work, it receives the session data of the user, the context of the user, and 
    # the command data of the command to be executed.
    def check_permissions(self, sessionData, contextData, commandData, user_priv_list):
        logging.info("Checking Permissions....")
        if not self._has_required_privileges(user_priv_list, commandData['req_priv_list']):
            # Compile a list of the required privileges
            missing_privileges = [priv for priv in commandData['req_priv_list'] if priv not in user_priv_list]
            logging.info(f"User does not have the required privileges to execute the command. Missing privileges: {missing_privileges}")
            return False
        if 'admin' in commandData['req_priv_list']:
            logging.info("Checking if the user has a valid admin session....")
            return self._is_valid_admin_session(sessionData, contextData)
        return True

    # Function to check if the user has the required privileges to execute the command
    def _has_required_privileges(self, user_priv_list, required_priv_list):
        return all(item in user_priv_list for item in required_priv_list)

    # Function to check if the user has a valid admin session
    def _is_valid_admin_session(self, sessionData, contextData):
        if not (sessionData and contextData and 'identity_id' in sessionData and 'community_id' in sessionData):
            logging.info("User does not have a valid session.")
            return False
        if sessionData["identity_id"] != contextData["identity_id"] or sessionData["community_id"] != contextData["community_id"]:
            logging.info("User does not have a valid session.")
            return False
        return self.check_token_expiry(sessionData)
        
    # Using session data, check if a token has not expired
    def check_token_expiry(self, sessionData: sessionData) -> bool:
        logging.info("Checking Token Expiry....")

        # Get the current time
        currentTime = time.time()

        # Get the session expiry time
        sessionExpiry = sessionData['session_expires']

        logging.info(f"Session Expiry: {sessionExpiry}")

        # Convert the session expiry date string to a datetime object
        sessionExpiry = time.mktime(time.strptime(sessionExpiry, "%Y-%m-%d %H:%M:%S"))

        # Check if the session expiry time is greater than the current time
        if sessionExpiry > currentTime:
            logging.info("The session has not expired. The user has a valid session.")
            return True
        else:
            logging.info("The session has expired.")
            return False  
        
        





# Load the environment variables
load_dotenv()

#waddler vars


# The main function of the program
def main() -> None:
    matterbridgeGetURL = matterbridgeURL + 'messages'
    matterbridgePostURL = matterbridgeURL + 'message'

    # Initialize the Matterbridge Link
    listener = WaddleBotListener(matterbridgeGetURL, matterbridgePostURL, contextURL, redisHost, redisPort, marketplaceURL, communityModulesURL, commandsURL=commandsURL)

    # Start listening for messages
    # listener.listen()

    waddler_instance = The_Waddler(waddler_token = waddler_token,
                                   waddler_context = waddler_context,
                                   waddler_commands = waddler_commands,
                                   waddler_identity = waddler_identity
                                   )
    # await waddler_instance.run()


# if __name__ == '__main__':
    loop = asyncio.get_event_loop()

    loop.create_task(waddler_instance.run())
    loop.create_task(listener.listen())
    
    try:
        loop.run_forever()
    finally:
        loop.stop()

if __name__ == '__main__':
    main()
