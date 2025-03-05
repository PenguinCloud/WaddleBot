FROM ghcr.io/penguincloud/core
LABEL company="Penguin Tech Group LLC"
LABEL org.opencontainers.image.authors="info@penguintech.group"
LABEL license="GNU AGPL3"
# TODO - Switch FROM to web2py

# GET THE FILES WHERE WE NEED THEM!
COPY . /opt/manager/
WORKDIR /opt/manager


# PUT YER ARGS in here
ARG APP_TITLE="waddlebot-core" 
ARG MATTERBRIDGE_VERSION="1.26.0"


# PUT YER ENVS in here
ENV GATEWAYS_GET_URL="http://host.docker.internal:8000/WaddleDBM/routing_gateways/get_all.json"
ENV COM_ROUTES_GET_URL="http://host.docker.internal:8000/WaddleDBM/routing/get_all_community_routes.json"
ENV GATEWAY_SERVERS_GET_URL="http://host.docker.internal:8000/WaddleDBM/gateway_servers/get_all.json"
ENV APP_TITLE="waddlebot" 
ENV USER_NAME="waddlebot" 
ENV USER_DISCORD_ID=""
ENV USER_DISCORD_NAME="PenguinzRockExample"
ENV DISCORD_TOKEN=""
ENV DISCORD_CHANNEL=""
ENV DISCORD_ENABLE="1"
ENV TWITCH_NAME="TwitchExample"
ENV TWITCH_NICK=""
ENV TWITCH_CHANNEL="#"
ENV TWITCH_TOKEN=""
ENV TWITCH_ENABLE="1"
ENV API_NAME="WaddleAPI"
ENV API_ADDRESS="0.0.0.0:4000"
ENV API_ENABLE="1"
ENV TELEGRAM_NAME="TelegramExample"
ENV TELEGRAM_TOKEN=""
ENV TELEGRAM_CHANNEL=""
ENV TELEGRAM_ENABLE="0"
ENV GATEWAY_NAME="GatewayExample"

# Python related commands to install dependencies, create a virtual environment, and run the application
#RUN apt-get update && apt-get install -y python3

# Set the working directory to the WaddleBot-Configurator directory
WORKDIR /opt/manager/modules/WaddleBot-Configurator

# # Install the dependencies in the virtual environment, located in the WaddleBot-Configurator directory
RUN pip install -r requirements.txt

# Set the working directory back to the manager directory
WORKDIR /opt/manager

# BUILD IT!
RUN ansible-playbook entrypoint.yml -c local --tags "build"


# Switch to non-root user
# TODO: Uncomment the below user line when the user's privilages have been fixed
# USER www-data

# Entrypoint time (aka runtime)
ENTRYPOINT ["/bin/bash","/opt/manager/entrypoint.sh"]
