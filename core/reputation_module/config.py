"""Configuration for reputation_module"""
import logging
import os
import threading
from typing import Optional

from dotenv import load_dotenv
from flask_core.secrets import require_secret_key

load_dotenv()

logger = logging.getLogger(__name__)


class Config:
    """Reputation module configuration from environment variables."""

    MODULE_NAME = 'reputation_module'
    MODULE_VERSION = '2.0.0'
    MODULE_PORT = int(os.getenv('MODULE_PORT', '8021'))
    GRPC_PORT = int(os.getenv('GRPC_PORT', '50021'))
    DEPLOYMENT_TIER = os.getenv('DEPLOYMENT_TIER', 'development').lower()  # development, alpha, beta, gamma, production
    DATABASE_URL = os.getenv(
        'DATABASE_URL',
        'postgresql://waddlebot:password@localhost:5432/waddlebot'
    )
    CORE_API_URL = os.getenv('CORE_API_URL', 'http://router-service:8000')
    ROUTER_API_URL = os.getenv(
        'ROUTER_API_URL',
        'http://router-service:8000/api/v1/router'
    )
    HUB_API_URL = os.getenv('HUB_API_URL', 'http://hub-module:8060')
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    SECRET_KEY = require_secret_key()
    SERVICE_API_KEY = os.getenv('SERVICE_API_KEY', '')
    # Whether to issue CREATE TABLE DDL for the read-only tenants/
    # communities/community_members subset `flask_core.
    # bind_community_read_tables` binds for community-scoped authz.
    # Prod NEVER migrates these -- owned by hub-api's own migrations.
    DB_MIGRATE = os.getenv('DB_MIGRATE', 'false').strip().lower() in {'1', 'true', 'yes', 'on'}

    # Redis Configuration (for credential refresh notifications)
    REDIS_URL: str = os.getenv('REDIS_URL', '')

    # Credential state management
    _credentials_loaded: bool = False
    _credential_lock: threading.Lock = threading.Lock()

    # FICO-style reputation score boundaries
    REPUTATION_MIN = 300
    REPUTATION_MAX = 850
    REPUTATION_DEFAULT = 600
    REPUTATION_AUTO_BAN_THRESHOLD = 450

    # Cache settings
    WEIGHT_CACHE_TTL = int(os.getenv('WEIGHT_CACHE_TTL', '300'))

    # Default weights (used for all non-premium communities). chat_message/
    # command_usage are whole, positive ints (gh-310) -- see
    # WeightManager.CommunityWeights and ReputationService._clamp_score for
    # why sub-1.0-magnitude weights never move the INTEGER-typed score
    # columns across repeated events.
    DEFAULT_WEIGHTS = {
        'chat_message': 1.0,
        'command_usage': 1.0,
        'giveaway_entry': -1.0,  # Larger penalty to dissuade giveaway bots
        'follow': 1.0,
        'subscription': 5.0,
        'subscription_tier2': 10.0,
        'subscription_tier3': 20.0,
        'gift_subscription': 3.0,
        'donation_per_dollar': 1.0,
        'cheer_per_100bits': 1.0,
        'raid': 2.0,
        'boost': 5.0,
        'warn': -25.0,
        'timeout': -50.0,
        'kick': -75.0,
        'ban': -200.0,
    }

    # Reputation tier definitions (FICO-style)
    REPUTATION_TIERS = {
        'exceptional': {'min': 800, 'max': 850, 'label': 'Exceptional'},
        'very_good': {'min': 740, 'max': 799, 'label': 'Very Good'},
        'good': {'min': 670, 'max': 739, 'label': 'Good'},
        'fair': {'min': 580, 'max': 669, 'label': 'Fair'},
        'poor': {'min': 300, 'max': 579, 'label': 'Poor'},
    }

    @classmethod
    def load_credentials_from_db(cls, db_connection) -> bool:
        """Load credentials from platform_integrations table.

        Falls back to environment variables if DB lookup fails.

        Args:
            db_connection: A database connection with executesql support.

        Returns:
            True if credentials were loaded from DB.
        """
        try:
            rows = db_connection.executesql(
                "SELECT access_token, config_data "
                "FROM platform_integrations "
                "WHERE platform = 'reputation' "
                "AND integration_type = 'bot' "
                "AND is_active = TRUE "
                "LIMIT 1"
            )
            if rows and rows[0]:
                with cls._credential_lock:
                    cls._credentials_loaded = True
                logger.info(
                    "Credentials loaded from platform_integrations for reputation"
                )
                return True
        except Exception as e:
            logger.warning(
                "Failed to load credentials from DB, using env vars: %s", e
            )
        return False

    @classmethod
    def start_credential_listener(cls, redis_client) -> Optional[threading.Thread]:
        """Start a background thread that listens for credential refresh events.

        Args:
            redis_client: A Redis client instance.

        Returns:
            The listener thread, or None if Redis is not configured.
        """
        if not cls.REDIS_URL:
            return None

        channel = "credentials:reputation:bot:refreshed"

        def _listen():
            try:
                pubsub = redis_client.pubsub()
                pubsub.subscribe(channel)
                logger.info(
                    "Listening for credential refresh on: %s",
                    channel,
                )
                for message in pubsub.listen():
                    if message["type"] == "message":
                        logger.info(
                            "Credential refresh notification received"
                        )
                        with cls._credential_lock:
                            cls._credentials_loaded = False
            except Exception as e:
                logger.error("Credential listener error: %s", e)

        thread = threading.Thread(
            target=_listen, daemon=True, name="credential-listener"
        )
        thread.start()
        return thread
