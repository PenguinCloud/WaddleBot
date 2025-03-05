import discord
import threading
import os # default module
import logging
import requests
import json
import html2text

from dotenv import load_dotenv



load_dotenv() # load all the variables from the env file



#write logs to file squeeker
logging.basicConfig(level=logging.INFO, handlers=[logging.FileHandler("squeeker.txt"), logging.StreamHandler()])

# declaring the existance of a bot
#lets get classy

class The_Waddler:
    def __init__ (self, waddler_token: str, waddler_context: str, waddler_commands: str, waddler_identity: str):
        self.bot = discord.Bot()

        self.waddler_token = waddler_token
        self.waddler_context = waddler_context
        self.waddler_commands = waddler_commands
        self.waddler_identity = waddler_identity

        @self.bot.slash_command(name="command_grab")
        async def command_grab_function(
        ctx: discord.ApplicationContext,
        request_from_discord: discord.Option(str, "what will be your choice!", autocomplete=self.list_search),
        command_input: str
        ):
        #get and set up the commands for use from url (for what is above this)

            author_name = ctx.author.name

            logging.info("The user who executed the command is: ")
            logging.info(author_name)

            self.add_identity(author_name)

            get_my_context = self.get_context(author_name)

        # get action URL if comand name matches from current command list
            get_my_action = await self.get_action(request_from_discord)
            get_my_method = await self.get_method(request_from_discord)
            command_string = request_from_discord + ' ' + command_input


            response_result_from_action = ""
            if get_my_action == None:
                response_result_from_action = "nada >.<"
            else: 
                # response_result_from_action = f"ya here is the action {get_my_action}"
                response_result_from_action = self.excute_action_url(
                    command_name = request_from_discord, 
                    action_url_to_exe = get_my_action, 
                    method = get_my_method, 
                    command_string = command_string, 
                    author_name = author_name, 
                    get_my_context = get_my_context
                    )



            await ctx.respond(response_result_from_action)


    async def get_commands(self, url):
        command_List_Return = []
        action_list = []
        # Get the commands from the DBM
        url_response = requests.get(url).json()

        commands_from_url = url_response["data"]

        # Loop through the commands
        for command in commands_from_url:
            # Add the command to the list
            command_List_Return.append(command["command_name"])
            action_object = {
                "command_name": command["command_name"],
                "action_url": command["action_url"],
                "request_method": command["request_method"]
        }
            action_list.append( action_object)
        await self.write_to_file(action_list)
        return command_List_Return

    async def write_to_file(self, action_list):
        with open('bananafile.json', "w") as file:
            json.dump(action_list, file)
            file.close()



    async def list_search(self, ctx: discord.AutocompleteContext):
        """Return's A List Of Autocomplete Results"""

        pycord_get_commands = self.waddler_commands # os.getenv('PYCORD_GET_COMMANDS')
        
        # Get the list of commands.json
        commands = await self.get_commands(url=pycord_get_commands)

        # print("The list of retrieved commands is: ", commands)

        # Return the list of commands
        return commands

    # ┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓


    async def read_4m_file(self):
        actions_4m_file = None
        logging.info("getting stuff")
        with open('bananafile.json', "r") as file:
            actions_4m_file = json.load(file)
            logging.info("I GOT STUFFY STUFFS - MJ")
            logging.info(actions_4m_file)
            file.close()
        return actions_4m_file

    async def get_action(self, command_string: str):
        action_list_reader = await self.read_4m_file()
        logging.info("getting an action from list")
        logging.info(action_list_reader)
        foundvalue = None
        for command_check in action_list_reader:
            if command_check["command_name"] == command_string:
                foundvalue = command_check["action_url"]
        
        return foundvalue

    async def get_method(self, command: str):
        actionlist = await self.read_4m_file()
        # logging.info("getting an action from list")
        # logging.info(actionlist)
        foundvalue = None
        for actionobj2 in actionlist:
            if actionobj2["command_name"] == command:
                foundvalue = actionobj2["request_method"]
        
        return foundvalue

    # Function to turn a data dictionary response from a request into a string
    def data_to_string(self, data: dict) -> str:
        # Convert the data dictionary to a string
        dataStr = ""
        if len(data) > 0:
            for count in range(len(data)):
                for key in data[count]:
                    dataStr += f"{key}: {data[count][key]}\n"
    
        return dataStr

    # ┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓

    def excute_action_url(self, command_name: str, action_url_to_exe: str, method: str, command_string: str, author_name: str, get_my_context: str):
        html_to_text = html2text.HTML2Text()
        logging.info(action_url_to_exe)

        

    #for testing, idientiy and community is hard coded
        payload = {
            "identity_name": author_name,
            "community_name": get_my_context,
            "command_string": command_string,
        }
        logging.info("i sent this payload")
        logging.info(payload)
        # community_get_role [Global]

        action_url_to_exe = action_url_to_exe.replace("127.0.0.1", "host.docker.internal")
        response = None
        if method == "GET":
            logging.info("exeing get")
            response = requests.get(url=action_url_to_exe, json=payload)
        if method == "POST":
            logging.info("exeing post")
            response = requests.post(url=action_url_to_exe, json=payload)
        if method == "PUT":
            logging.info("exeing put")
            response = requests.put(url=action_url_to_exe, json=payload)
        if method == "DELETE":
            logging.info("exeing delete")
            response = requests.delete(url=action_url_to_exe, json=payload)
        logging.info("########\n")
        
        # print(response)
        command_output = "An error occured. See logs for details."
        if response.status_code < 400:
            if_not_error = response.json()
            if "msg" in if_not_error:
                command_output = if_not_error["msg"]
            elif "data" in if_not_error:
                command_output = self.data_to_string(if_not_error["data"])
            else: 
                command_output = "no msg, go fetch"
        else:
            # Convert the response to text
            logging.info("Found a response object:")
            handledText = html_to_text.handle(response.text)

            # Split the text by newlines
            splitText = handledText.split("\n")

            # Loop through the text
            for line in splitText:
                # If the line can be translated into a dictionary, add it as an output to the command
                try:
                    jsonOutput = json.loads(line)  
                    logging.info("=====================================================\n")
                    logging.info("I HAVE FOUND A DICTIONARYYYYYY")
                    logging.info(jsonOutput)
                    logging.info("=====================================================\n")

                    if "msg" in jsonOutput:
                        command_output = jsonOutput["msg"]
                except:
                    # logging.info("=====================================================\n")
                    # logging.info("i coudent do it, im skipping this")
                    # logging.info(line + " could not be turned into a json")
                    # logging.info("=====================================================\n")
                    pass

        return command_output



    #intlizing user

    # Function to add an identity (User) to the database
    def add_identity(self, username : str) -> None:
        logging.info("Adding Identity....")

        Pycord_add_identity = self.waddler_identity #os.getenv('PYCORD_ADD_IDENTITY')

        try:
            payload = {
                "identity_name": username
            }
        
            resp = requests.post(url=Pycord_add_identity, json=payload)
        
            if resp.ok:
                msg = ""
                if 'msg' in resp.json():
                    msg = resp.json()['msg']
                logging.info(msg) 
        except requests.exceptions.RequestException as e:
            logging.error(e)
            logging.error("An error has occurred while trying to add the identity.")


    # Function to get the context of the current user
    def get_context(self, username: str):
        logging.info("Getting the context....")

        pycord_get_context =  self.waddler_context #os.getenv('PYCORD_GET_COTEXT')

        payload = {
            "identity_name": username
        }

        # Create the function URL
        url = pycord_get_context

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
                return respJson["data"]["community_name"]
        else:
            return None

        

    # ┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓┏(-_-)┛┗(-_- )┓

    # @bot.slash_command(name="command_grab")
    # async def command_grab_function(
    # ctx: discord.ApplicationContext,
    # request_from_discord: discord.Option(str, "what will be your choice!", autocomplete=self.list_search),
    # command_input: str
    # ):
    # #get and set up the commands for use from url (for what is above this)

    #     author_name = ctx.author.name

    #     logging.info("The user who executed the command is: ")
    #     logging.info(author_name)

    #     self.add_identity(author_name)

    #     get_my_context = self.get_context(author_name)

    # # get action URL if comand name matches from current command list
    #     get_my_action = await self.get_action(request_from_discord)
    #     get_my_method = await self.get_method(request_from_discord)
    #     command_string = request_from_discord + ' ' + command_input


    #     response_result_from_action = ""
    #     if get_my_action == None:
    #         response_result_from_action = "nada >.<"
    #     else: 
    #         # response_result_from_action = f"ya here is the action {get_my_action}"
    #         response_result_from_action = self.excute_action_url(
    #             command_name = request_from_discord, 
    #             action_url_to_exe = get_my_action, 
    #             method = get_my_method, 
    #             command_string = command_string, 
    #             author_name = author_name, 
    #             get_my_context = get_my_context
    #             )



    #     await ctx.respond(response_result_from_action)

    # t = threading.Thread(target=self.bot.start , args=(os.getenv('TOKEN')), daemon=True).start()
    async def run(self):
        await self.bot.start(self.waddler_token)


