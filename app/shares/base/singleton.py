from app.config.logging import log


class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super().__call__(*args, **kwargs)
            log.info(f"Create new instance of {cls}")
        return cls._instances[cls]

    def clear_instances(cls):
        cls._instances.pop(cls, None)


class SingletonBase(metaclass=SingletonMeta):
    pass


class SingletonMetaWithOrgId(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        org_id = kwargs.get("org_id")

        if org_id is None and len(args) > 0:
            org_id = args[0]

        if org_id is None:
            raise ValueError("org_id is required to create a singleton instance")

        key = (cls, org_id)

        if key not in cls._instances:
            cls._instances[key] = super().__call__(*args, **kwargs)
            log.info(f"Create new instance of {cls} with org_id: {org_id}")

        return cls._instances[key]

    def clear_instances(cls, org_id: str):
        key = (cls, org_id)
        cls._instances.pop(key, None)


class SingletonMetaWithOrgIdAndChatBotId(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        org_id = kwargs.get("org_id")
        chat_bot_id = kwargs.get("chat_bot_id")

        if org_id is None and len(args) > 0:
            org_id = args[0]

        if chat_bot_id is None and len(args) > 1:
            chat_bot_id = args[1]

        if org_id is None:
            raise ValueError("org_id is required to create a singleton instance")

        if chat_bot_id is None:
            raise ValueError("chat_bot_id is required to create a singleton instance")

        key = (cls, org_id, chat_bot_id)

        if key not in cls._instances:
            cls._instances[key] = super().__call__(*args, **kwargs)
            log.info(
                f"Create new instance of {cls} with "
                f"org_id: {org_id} "
                f"chat_bot_id: {chat_bot_id}"
            )

        return cls._instances[key]

    def clear_instances(cls, org_id: str, chat_bot_id: str):
        key = (cls, org_id, chat_bot_id)
        cls._instances.pop(key, None)


class SingletonBaseWithOrgId(metaclass=SingletonMetaWithOrgId):
    org_id: str

    def __init__(self, org_id: str):
        self.org_id = org_id


class SingletonBaseWithOrgIdAndChatBotId(metaclass=SingletonMetaWithOrgIdAndChatBotId):
    org_id: str
    chat_bot_id: str

    def __init__(self, org_id: str, chat_bot_id: str):
        self.org_id = org_id
        self.chat_bot_id = chat_bot_id
