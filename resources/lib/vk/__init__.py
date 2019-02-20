# coding=utf-8

from vk.api import VERSION, API, Session, AuthSession, InteractiveSession, InteractiveAuthSession, logger
from vk.exceptions import VkAuthError, VkAPIError  # tmi mod

__version__ = version = VERSION
__all__ = ('API', 'Session', 'AuthSession', 'VkAuthError', 'VkAPIError')
