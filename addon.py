# Enable unicode strings by default
# from __future__ import unicode_literals

# Import std modules
import datetime
import json
import os
import sys
import urllib
import urlparse

# Import kodi modules
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import requests
import YDStreamExtractor  # todo: correct?

# Import addon modules
from resources.lib.debug import debug


# Define constants
CONTENT_TYPE = 'videos'
VK_API_CLIENT_ID = '6432748'
VK_API_VERSION = '5.85'
ISFOLDER_TRUE = True
ISFOLDER_FALSE = False
# todo: dev only
_VK_API_COOKIE = 'remixlang=21; remixlhk=300eac9d2544ea2904; remixstid=1947479265_931c20d2be6cdf6d3d; remixaudio_date=19-09-2018; remixaudio_background_play_time_=0; remixaudio_background_play_time_limit=1800; remixaudio_show_alert_today=0'


# Define addon class
class MyAddon(object):

    # Initialize addon
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.handle = int(sys.argv[1])
        xbmcplugin.setContent(self.handle, CONTENT_TYPE)
        # get addon settings
        self.settings = {
            'itemsPerPage': int(self.addon.getSetting('itemsPerPage')),
            'vkUserAccessToken': self.addon.getSetting('vkUserAccessToken')
        }
        # get parsed url
        self.url = {}
        self.url['base'] = 'plugin://' + self.addon.getAddonInfo('id')  # 'plugin://plugin.video.vk'
        self.url['path'] = sys.argv[0].replace(self.url['base'], '')  # i.e. '/', '/play', ...
        self.url['args'] = {}
        if sys.argv[2].startswith('?'):
            self.url['args'] = urlparse.parse_qs(sys.argv[2].lstrip('?'))
            for k, v in list(self.url['args'].items()):
                self.url['args'][k] = v.pop()
        # set default url args/values
        if self.url['path'] in ['/searchedvideos', '/videos', '/albumvideos', '/communityvideos', '/likedvideos',
                                '/searchhistory', '/albums', '/communities', '/likedcommunities']:
            if 'offset' not in self.url['args']:
                self.url['args']['offset'] = 0
        debug('self.url', self.url)
        # define addon routing handlers
        self.routing = {
            '/': self.listIndex,
            '/authorize': self.authorize,
            '/albums': None,
            '/albumvideos': None,
            '/communities': None,
            '/communityvideos': None,
            '/likedcommunities': None,
            '/likedvideos': None,
            '/play': self.playVideo,
            '/search': self.searchVideos,
            '/searchedvideos': None,  # todo: needed?
            '/searchhistory': self.listSearchHistory,
            '/stats': None,
            '/videos': self.listVideos,
        }
        # dispatch routing
        if self.url['path'] in self.routing:
            handler = self.routing[self.url['path']]
            if handler is not None:
                handler()

    # Authorize addon
    def authorize(self):
        # request vk oauth2 service for user access token
        response = requests.get(
            url='https://oauth.vk.com/authorize',
            params={
                'v': VK_API_VERSION,
                'client_id': int(VK_API_CLIENT_ID),
                'scope': 'video,groups,friends,notes,email,status,offline',
                'display': 'popup',
                'response_type': 'token',
                'redirect_uri': 'https://oauth.vk.com/blank.html',
            }
        )
        debug('response', response)
        usr = xbmcgui.Dialog().input('ENTER YOUR USERNAME/EMAIL:')
        pwd = xbmcgui.Dialog().input('ENTER YOUR PASSWORD:', type=xbmcgui.INPUT_PASSWORD)
        debug('usr', usr)
        debug('pwd', pwd)

    # Build addon url
    def buildUrl(self, path, args=None):
        url = self.url['base'] + path
        if args is not None:
            url += '?' + urllib.urlencode(args)
        debug('buildUrl()', url)
        return url

    # List index menu
    def listIndex(self):
        listItems = [
            (self.buildUrl('/search'), xbmcgui.ListItem('SEARCH'), ISFOLDER_FALSE),
            (self.buildUrl('/searchhistory'), xbmcgui.ListItem('SEARCH HISTORY'), ISFOLDER_TRUE),
            (self.buildUrl('/videos'), xbmcgui.ListItem('MY VIDEOS'), ISFOLDER_TRUE),
            (self.buildUrl('/albums'), xbmcgui.ListItem('ALBUMS'), ISFOLDER_TRUE),
            (self.buildUrl('/likedvideos'), xbmcgui.ListItem('LIKED VIDEOS'), ISFOLDER_TRUE),
            (self.buildUrl('/communities'), xbmcgui.ListItem('COMMUNITIES'), ISFOLDER_TRUE),
            (self.buildUrl('/likedcommunities'), xbmcgui.ListItem('LIKED COMMUNITIES'), ISFOLDER_TRUE),
            (self.buildUrl('/stats'), xbmcgui.ListItem('STATS'), ISFOLDER_TRUE),
        ]
        xbmcplugin.addDirectoryItems(self.handle, listItems, len(listItems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    # List search history
    def listSearchHistory(self):
        # load history from json file (if exists)
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), 'searchhistory.json')
        if os.path.exists(fp):
            history = {}
            with open(fp) as f:
                history = json.load(f)
            debug('history', history)
            # create list items for historic queries
            listItems = []
            for search in history['items']:
                li = xbmcgui.ListItem(search['q'])
                li.addContextMenuItems(
                    [
                        ('SEARCH QUERY', ''),  # todo: command
                        ('EDIT QUERY', ''),  # todo: command
                        ('DELETE QUERY', ''),  # todo: command
                    ]
                )
                listItems.append(
                    (self.buildUrl('/search', {'q': search['q']}), li, ISFOLDER_TRUE)
                )
            debug('listItems', listItems)
        # show list in kodi (even if empty)
        xbmcplugin.addDirectoryItems(self.handle, listItems, len(listItems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_LABEL)
        xbmcplugin.endOfDirectory(self.handle)

    # List videos
    def listVideos(self):
        # request vk api for videos metadata
        response = requests.get(
            url='https://api.vk.com/method/video.get',
            params={
                'access_token': self.settings['vkUserAccessToken'],
                'v': VK_API_VERSION,
                'extended': 1,
                'count': self.settings['itemsPerPage'],
                'offset': self.url['args']['offset'],
            },
            headers={
                'Cookie': _VK_API_COOKIE,
            }
        ).json()
        videos = response['response']
        debug('videos', videos)
        # create list items for videos
        listItems = []
        for video in videos['items']:
            li = xbmcgui.ListItem(video['title'])
            li.setProperty('IsPlayable', 'true')
            li.setArt({'thumb': video['photo_320']})
            li.setInfo(
                type='video',
                infoLabels={
                    'title': video['title'],
                    'plot': video['description'],
                    'duration': video['duration'],
                    'dateadded': datetime.datetime.fromtimestamp(video['adding_date']).strftime('%Y-%m-%d %H:%M:%S'),
                    'playcount': video['views'],
                }
            )
            li.addContextMenuItems(
                [
                    ('PLAY VIDEO', ''),  # todo: command
                    ('LIKE VIDEO', ''),  # todo: command
                    ('ADD TO MY VIDEOS', ''),  # todo: command / cond: searched only (vs not mine?)
                    ('ADD TO ALBUM', ''),  # todo: command
                    ('ADD TO WATCHLIST', ''),  # todo: command
                    ('SEARCH SIMILAR', ''),  # todo: command
                ]
            )
            listItems.append(
                (self.buildUrl('/play', {'oid': video['owner_id'], 'id': video['id']}), li, ISFOLDER_FALSE)
            )
        # add paginator item
        if videos['count'] > self.settings['itemsPerPage']:
            if videos['count'] > int(self.url['args']['offset']) + self.settings['itemsPerPage']:
                offsetNext = int(self.url['args']['offset']) + self.settings['itemsPerPage']
                listItems.append(
                    (self.buildUrl('/videos', {'offset': offsetNext}), xbmcgui.ListItem('[COLOR yellow]NEXT PAGE[/COLOR]'), ISFOLDER_TRUE)
                )
        debug('listItems', listItems)
        # show list in kodi
        xbmcplugin.addDirectoryItems(self.handle, listItems, len(listItems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_DATEADDED)
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_DURATION)
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_PLAYCOUNT)
        xbmcplugin.endOfDirectory(self.handle)

    # Play video
    def playVideo(self):
        # request vk api for video metadata
        response = requests.get(
            url='https://api.vk.com/method/video.get',
            params={
                'access_token': self.settings['vkUserAccessToken'],
                'v': VK_API_VERSION,
                'videos': '{0}_{1}'.format(self.url['args']['oid'], self.url['args']['id']),
            },
            headers={
                'Cookie': _VK_API_COOKIE,
            }
        ).json()
        video = response['response']['items'][0]
        debug('video', video)
        # get video url and resolve it
        url = video['player']
        isResolveable = YDStreamExtractor.mightHaveVideo(url)
        debug('isResolveable', isResolveable)
        if isResolveable:
            vi = YDStreamExtractor.getVideoInfo(url, quality=3)
            if vi is not None:
                resolvedUrl = vi.streamURL()
                debug('resolvedUrl', resolvedUrl)
                # create item for kodi player
                if resolvedUrl:
                    li = xbmcgui.ListItem()
                    li.setPath(resolvedUrl)
                    xbmcplugin.setResolvedUrl(self.handle, li, succeeded=True)

    # Search videos
    def searchVideos(self):
        # show dialog and let user enter a new search query
        q = xbmcgui.Dialog().input('ENTER SEARCH QUERY')
        debug('q', q)
        if q:
            # update search history json file (if not exists create a new one)
            pass
            # request vk api for search videos
            pass


# Run addon
if __name__ == '__main__':
    MyAddon()
