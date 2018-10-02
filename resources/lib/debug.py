
import xbmc


DEBUG_LOG_PREFIX = 'plugin.video.vk'


def log(label, value):
    msg = '{0}: {1}: {2}'.format(DEBUG_LOG_PREFIX, label, value)
    xbmc.log(msg, level=xbmc.LOGDEBUG)
