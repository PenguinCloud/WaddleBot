FROM ghcr.io/penguincloud/core
LABEL company="Penguin Tech Group LLC"
LABEL org.opencontainers.image.authors="info@penguintech.group"
LABEL license="GNU AGPL3"

# GET THE FILES WHERE WE NEED THEM!
COPY . /opt/manager/
WORKDIR /opt/manager


# PUT YER ARGS in here
ARG APP_TITLE="waddlebot-hook" 
ARG MATTERBRIDGE_VERSION="1.26.0"


# PUT YER ENVS in here
ENV GATEWAY_ACTIVATE_URL="http://host.docker.internal:8000/WaddleDBM/routing_gateways/activate_gateway.json"
ENV MATTERBRIDGE_URL='http://localhost:4200/api/'
ENV USER_MANGER_URL='http://localhost:8000/WaddleDBM/identities/create.json/'
ENV MARKETPLACE_URL='http://localhost:8000/marketplace_manager/marketplace/get.json'
ENV COMMUNITY_MODULES_URL='http://localhost:8000/WaddleDBM/community_modules/get_by_community_name_and_module_id.json/'
ENV CONTEXT_URL='http://localhost:8000/WaddleDBM/context/'
ENV REDIS_HOST='localhost'
ENV REDIS_PORT=6379
ENV TWITCH_APP_ID=""
ENV TWITCH_APP_SECRET=""
ENV CONTEXT_URL="http://host.docker.internal:8000/WaddleDBM/context/initialize_user.json"
ENV GATEWAYS_GET_URL="http://host.docker.internal:8000/WaddleDBM/routing_gateways/get_all.json"
ENV EVENTSUB_URL = 'https://mj-dev.penguintech.io/'

# Set the working directory to the WaddleBot-Configurator directory
WORKDIR /opt/manager/

# BUILD IT!
RUN ansible-playbook entrypoint.yml -c local --tags "build"


# Switch to non-root user
USER waddlebot

# Entrypoint time (aka runtime)
ENTRYPOINT ["/bin/bash","/opt/manager/entrypoint.sh"]
