import requests
import time
import re
from pydal import DAL, Field

# from src.user.user_manager import UserManager
from src.identity.identity_manager import IdentityManager
from src.community.community_manager import CommunityManager
from src.community.community_members_manager import CommunityMembersManager
from src.community.community_module_manager import CommunityModuleManager
from src.roles.roles_manager import RolesManager
from src.discord.discord_manager import DiscordManager
from src.twitch.twitch_manager import TwitchManager
from src.marketplace.marketplace_manager import MarketplaceManager

# TODO: Add these commands to the REDIS cache
botCommands = { "!help": "Displays the list of available commands.",
                "!community": "A set of commands to manage communities, if you have the right permissions.",
                "!community_manage_add": "Creates a new community. Requires the community name and description. The community name must be unique. The community description is optional. Example: !community_manage_add <Test Community>",
                "!community_manage_rem": "Removes a community. Requires the community name. Example: !community_manage_rem <Test Community>",
                "!community_manage_ls": "Lists all communities. Example: !community_manage_ls",
                "!community_manage_desc": "Sets the description of a community. Requires the community name and description. Example: !community_manage_desc <Test Community> <This is a test community>",
}

class matterbridgelink:
    def __init__(self, requestGetURL, requestPostURL, connectionString):
        # Initialize the variables
        self.requestGetURL = requestGetURL
        self.requestPostURL = requestPostURL
        self.connectionString = connectionString

        # Setup database instances
        db = DAL(connectionString, pool_size=2)

        self.identityManager = IdentityManager(db)
        self.discordManager = DiscordManager(db)
        self.twitchManager = TwitchManager(db)
        self.marketplaceManager = MarketplaceManager(db)
        self.communityManager = CommunityManager(db)
        self.communityMembersManager = CommunityMembersManager(db)
        self.communityModuleManager = CommunityModuleManager(db)
        self.rolesManager = RolesManager(db)

        # Create the database on initialization
        self.create_DB()

    # Function to listen for messages
    def listen(self):
        print("Listening for messages....")

        while True:
            resp = requests.get(self.requestGetURL)
            if resp.ok:
                messageData = resp.json()

                # Check if the message data is not empty
                if len(messageData) > 0:
                    print("FOUND MESSAGE!!")
                    print(messageData)

                    # Create a user if the user does not exist
                    if 'username' in messageData[0]:
                        self.add_identity(messageData[0]['username'])

                    if 'text' in messageData[0] and 'gateway' in messageData[0]:
                        gateway = messageData[0]['gateway']
                        message = messageData[0]['text']

                        if "!" in message and message[0] == "!":
                            command = self.get_command(message)

                            # Execute the command
                            # commandResult = self.execute_command(command)

                            print("Command found in text. Looking up command....")

                            # Check if the command is in the botCommands dictionary
                            cmdResult = ""

                            if command in botCommands:
                                if command == "!help":
                                    cmdResult = self.display_help()
                                if command == "!community":
                                    cmdResult = self.display_community_commands()
                                if command == "!community_manage_add":
                                    comName = self.get_community_name(message)
                                    cmdResult = self.create_community(comName)
                                if  command == "!community_manage_rem":
                                    comName = self.get_community_name(message)
                                    cmdResult = self.remove_community(comName)
                                if command == "!community_manage_ls":
                                    cmdResult = self.get_communities()
                                if command == "!community_manage_desc":
                                    comParams = self.get_community_params(message)
                                    cmdResult = self.add_description_to_community(comParams[0], comParams[1])  

                                self.send_bot_message(gateway, cmdResult) 
                            else:
                                print("Command not found in the botCommands dictionary.")
                                self.send_bot_message(gateway, "Command not found. Please use !help to see the list of available commands.")

                            
                        else:
                            print("No command tag found in message.")
                    else:
                        print("Error occured while processing the message. Either the 'gateway' or the 'text' attributes are missing.")
            else:
                print("An error has occurred while trying to communicate with the API.")

            time.sleep(1)

    # Function to get the command from the message
    def get_command(self, message):
        print("Getting the command from the message....")

        command = ""

        # Get the first word from the message
        command = message.split(" ")[0]

        return command

    # Function to send a bot message
    def send_bot_message(self, gateway, command):
        print("Sending Bot Message....")

        payload = {
            "text": f"{command}",
            "username": "Waddle Bot",
            "gateway": gateway
        }

        resp = requests.post(url=self.requestPostURL, json=payload)

        if resp.ok:
            print("BOT Message Successfully Sent!")

    # Function to create the database
    def create_DB(self):
        print("Creating the database, if not exists....")

        # Create the user table, if it doesnt exist
        self.identityManager.create_identity_table()

        # Create the community table, if it doesnt exist
        self.communityManager.create_community_table()

        # Create the community members table, if it doesnt exist
        self.communityMembersManager.create_community_members_table()

        # Create the community module table, if it doesnt exist
        self.communityModuleManager.create_community_module_table()

        # Create the roles table, if it doesnt exist
        self.rolesManager.create_roles_table()

        # Create the discord table, if it doesnt exist
        self.discordManager.create_discord_table()

        # Create the twitch table, if it doesnt exist
        self.twitchManager.create_twitch_table()

        # Create the marketplace table, if it doesnt exist
        self.marketplaceManager.create_marketplace_table()

    # Function to add user to the database, if the user does not exist
    def add_identity(self, username):
        # Get message from the identityManager
        msg = self.identityManager.create_identity(username)

        # Log the resulting message
        print(msg) 
        
    # Function to display list of available commands
    def display_help(self):
        print("Displaying list of available commands....")

        commands = ""
        descriptions = ""

        output = ""

        # Loop through the botCommands dictionary and add the commands for display to the user
        for key in botCommands:
            commands += f"{key}\n"
            descriptions += f"{botCommands[key]}\n"

            output += '%-30s%-30s' % (key, botCommands[key]) + "\n"

        # print(output)

        return output
    
    # Function to display the community commands
    def display_community_commands(self):
        print("Displaying community commands....")

        output = ""

        #Loop through all the community commands
        for key in botCommands:
            if "!community" in key and key != "!community":
                output += '%-30s%-30s' % (key, botCommands[key]) + "\n"

        return output
    
    # Function to create a new community
    def create_community(self, communityname):
        print("Creating a new community....")

        if not communityname:
            return "Community name is required. Example: !community_manage_add <Test Community>"
        
        msg = self.communityManager.create_community(communityname)

        return msg
    
    # Function to return the community parameters from the given message
    def get_community_name(self, message):
        print("Getting community parameters....")

        communityname = ""

        # Return the words between the two characters "<" and ">"
        params = re.findall(r'<(.*?)>', message)
        if len(params) > 0:
            communityname = params[0]
        else:
            communityname = None

        return communityname
    
    # Function to get parameters from a message
    def get_community_params(self, message):
        print("Getting community parameters....")

        communityname = ""
        communitydescription = ""

        # Return the words between the two characters "<" and ">"
        params = re.findall(r'<(.*?)>', message)
        if len(params) == 2:
            communityname = params[0]
            communitydescription = params[1]
        else:
            communityname = None
            communitydescription = None

        return [communityname, communitydescription]
    
    # Function to remove a community
    def remove_community(self, communityname):
        print("Removing a community....")

        if not communityname:
            return "Community name is required. Example: !community_manage_rem <Test Community>"

        msg = self.communityManager.remove_community(communityname)

        return msg
    
    # Function to get a list of all communities
    def get_communities(self):
        print("Getting a list of all communities....")

        communities = self.communityManager.get_communities()

        return communities
    
    # Function to add a description to a community
    def add_description_to_community(self, communityname, communitydescription):
        print("Adding a description to a community....")

        if not communityname or not communitydescription:
            return "Community name and description are required. Example: !community_manage_desc <Test Community> <This is a test community>"

        msg = self.communityManager.add_description_to_community(communityname, communitydescription)

        return msg
    