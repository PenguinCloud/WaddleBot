from src.listener.listener import WaddleBotListener
from dotenv import load_dotenv
import os
from src.pycord_listener.pycord import The_Waddler
import asyncio




# Load the environment variables
load_dotenv()

#waddler vars
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
