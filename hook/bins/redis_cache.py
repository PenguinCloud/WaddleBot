import redis
import os

import logging
import requests

# TODO: Remove these test commands when the cache is officially deployed
testCommands = {
    # Community related commands
    "!community": "Community",
    # Context related commands
    "!namespace": "Context",
    # Marketplace Related Commands
    "!marketplace": "Marketplace",
    # Gateway route related commands
    "!gateway": "Gateway Manager",
    # Routing related commands
    "!route": "Routing Manager",
    # Currency related commands
    "!currency": "Currency",
    # Admin related commands
    "!admin": "Admin Context",
    # Text Response related commands
    "!text": "Text Response",
    # Alias related commands
    "!alias": "Alias Commands",
    # Calender related commands
    "!calender": "Calender",
    # Identity label related commands
    "!identity": "Identity Label",
    # Giveaway related commands
    "!giveaway": "Giveaway",
    # Test script related commands
    "#test": "Test Module",
}

class RedisCache:
    def __init__(self, host: str, port: int):
        self.redis = redis.Redis(host=host, port=port, decode_responses=True)

    # Function to get all the necessary commands from waddledbm.
    def init_commands(self, commandsUrl: str) -> None:
        logging.info("Initializing commands from WaddleDBM")

        # Get the commands from the given URL
        response = requests.get(commandsUrl)

        data = response.json()

        # If the response is successful, add the commands to redis
        if "data" in data:
            commands = data["data"]
            for command in commands:
                if not self.redis.exists(command["command_name"]):
                    self.redis.set(command["command_name"], command["action_url"])
        else:
            logging.error("Failed to get commands from WaddleDBM")

    # Function to add the given test commands to redis, if they do not already exist.
    def add_test_commands(self) -> None:
        for command in testCommands:
            if not self.redis.exists(command):
                self.redis.set(command, testCommands[command])

    # Function to get a command from redis, return None if it does not exist.
    def get_command(self, command: str) -> str:
        if self.redis.exists(command):
            return self.redis.get(command)
        return None
    
    # Function to get all commands from redis
    def get_all_commands(self) -> list:
        commands = []
        for key in self.redis.keys():
            commands.append(key + ": " + self.redis.get(key))
        return commands
    
    # Function to get all keys from redis
    def get_all_keys(self) -> list:
        return self.redis.keys()
        

    