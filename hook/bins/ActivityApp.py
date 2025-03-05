from twitchAPI.twitch import Twitch
from twitchAPI.helper import first
from twitchAPI.eventsub.webhook import EventSubWebhook
from twitchAPI.object.eventsub import ChannelFollowEvent, ChannelSubscribeEvent, ChannelSubscriptionGiftEvent
from twitchAPI.oauth import UserAuthenticator
from twitchAPI.type import AuthScope, ChatEvent
from twitchAPI.chat import Chat, EventData, ChatMessage, ChatSub, ChatCommand, ClearChatEvent, NoticeEvent, RoomStateChangeEvent
import asyncio
from dotenv import load_dotenv
import os
import requests
import logging

from src.listeners.twitch_listener import TwitchAPIListener

# Set the logging level
logging.basicConfig(level=logging.INFO)

load_dotenv()    

# TODO: Get the scopes from the Waddlebot's DB
TARGET_SCOPES = [AuthScope.MODERATOR_READ_FOLLOWERS, AuthScope.USER_READ_FOLLOWS, AuthScope.USER_EDIT_FOLLOWS, AuthScope.MODERATOR_MANAGE_AUTOMOD]

# The main function to run the bot
def main() -> None:
    # Get the gateways from the Waddlebot's DB
    gateways = get_gateways(os.getenv('GATEWAYS_GET_URL'))

    # Create an instance of the TwitchAPIListener
    listener = TwitchAPIListener(
        os.getenv('TWITCH_APP_ID'),
        os.getenv('TWITCH_APP_SECRET'),
        TARGET_SCOPES,
        gateways,
        os.getenv('CONTEXT_URL'),
        os.getenv('EVENTSUB_URL'),
        os.getenv('TARGET_USERNAME')
    )

    # Run the bot
    asyncio.run(listener.run())

# This function will retrieve all the gateways stored in the Waddlebot's DB
def get_gateways(url: str) -> list:
    logging.info('Getting gateways')

    channels = []

    try:
        # Make the request to the gateways API
        response = requests.get(url)

        if response.ok:
            data = None

            if response.json() and 'data' in response.json():
                data = response.json()['data']

                if len(data) > 0:
                    for gateway in data:
                        if 'gateway_type' in gateway and gateway['gateway_type'] == 'Twitch' and 'channel_id' in gateway and 'is_active' in gateway and gateway['is_active'] == True:
                            channel_id = gateway['channel_id']

                            if channel_id not in channels:
                                channels.append(gateway['channel_id'])
                
        return channels
    except Exception as e:
        logging.error(f'Error getting gateways: {e}')

        return []


if __name__ == '__main__':
    main()
