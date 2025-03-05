from dataclasses import dataclass

@dataclass
class messageData():
    text: str
    channel: str
    username: str
    userid: str
    avatar: str
    account: str
    event: str
    protocol: str
    gateway: str
    parent_id: str
    timestamp: str
    id: str
    Extra: str

@dataclass
class sessionData():
    id: str
    identity_id: int
    community_id: int
    session_token: str
    session_expires: str

@dataclass
class marketplaceModuleData():
    name: str
    description: str
    gateway_url: str
    module_type_id: int
    metadata: dict
    module_type_name: str
    priv_list: list
    session_data: sessionData
    aliased_command: str

@dataclass
class commandData():
    action: str
    description: str
    method: str
    parameters: list
    payload_keys: list
    req_priv_list: list

@dataclass
class sendMessageData():
    text: str
    username: str
    gateway: str
    account: str

@dataclass
class identityData():
    identity_name: str

@dataclass
class contextData():
    identity_name: str
    identity_id: int
    community_name: str
    community_id: int