from sys import argv
from urlparse import parse_qs
from xbmcaddon import Addon
from xbmcgui import ListItem
from xbmcplugin import setContent, setResolvedUrl, addDirectoryItems, endOfDirectory, addSortMethod, SORT_METHOD_NONE, SORT_METHOD_DATEADDED, SORT_METHOD_DURATION, SORT_METHOD_PLAYCOUNT
from requests import get
from urlresolver import resolve
from datetime import datetime
from math import ceil

# debugger
# <import addon="script.module.web-pdb"/>
# import web_pdb; web_pdb.set_trace()

ISFOLDER_TRUE = True
ISFOLDER_FALSE = False


class VKPlugin(object):

    # plugin initialization
    def __init__(self):
        self.addon = Addon()
        self.handle = int(argv[1])
        self.urlBase = 'plugin://plugin.video.vk'
        self.urlPath = argv[0].replace(self.urlBase, '')
        self.urlQS = argv[2]
        self.urlArgs = {}
        if self.urlQS.startswith('?'):
            self.urlArgs = parse_qs(self.urlQS.lstrip('?'))
            for k, v in self.urlArgs.items():
                self.urlArgs[k] = v.pop()
        self.settings = {
            'contentType': self.addon.getSetting('contentType'),
            'itemsPerPage': int(self.addon.getSetting('itemsPerPage')),
            'vkApiVersion': self.addon.getSetting('vkApiVersion'),
            'vkUserAccessToken': self.addon.getSetting('vkUserAccessToken'),
        }
        setContent(self.handle, self.settings['contentType'])
        self.dispatch()

    # plugin's routing dispatcher
    def dispatch(self):
        if self.urlPath == '/':
            self.listRoot()
        elif self.urlPath == '/videos':
            self.listVideos()
        elif self.urlPath == '/play':
            self.playVideo()

    # plugin's root directory
    def listRoot(self):
        items = [
            (self.urlBase + '/videos?offset=0', ListItem(self.addon.getLocalizedString(30005)), ISFOLDER_TRUE),
            (self.urlBase + '/communities?offset=0', ListItem(self.addon.getLocalizedString(30007)), ISFOLDER_TRUE),
        ]
        addDirectoryItems(self.handle, items, len(items))
        addSortMethod(self.handle, SORT_METHOD_NONE)
        endOfDirectory(self.handle)

    # plugin's directory: /videos
    def listVideos(self):
        requestUrl = 'https://api.vk.com/method/video.get'
        requestParams = {
            'access_token': self.settings['vkUserAccessToken'],
            'v': self.settings['vkApiVersion'],
            'extended': 1,
            'offset': int(self.urlArgs['offset']),
            'count': self.settings['itemsPerPage'],
        }
        videos = get(requestUrl, requestParams).json()
        items = []
        # pagination
        if videos['response']['count'] > self.settings['itemsPerPage']:
            offset = int(self.urlArgs['offset'])
            offsetNext = offset + self.settings['itemsPerPage']
            page = 1 if not offset else int(offset / self.settings['itemsPerPage']) + 1
            pagesCount = int(ceil(videos['response']['count'] / self.settings['itemsPerPage'])) + 1
            itemsCount = videos['response']['count']
            pagination = {}
            pagination['listItem'] = ListItem('PAGE {0} OF {1} ({2} ITEMS)'.format(page, pagesCount, itemsCount))
            pagination['url'] = self.urlBase + '/videos?offset={0}'.format(offsetNext)
            items.append(
                (pagination['url'], pagination['listItem'], ISFOLDER_FALSE)
            )
        for video in videos['response']['items']:
            listItem = ListItem(video['title'])
            listItem.setProperty('IsPlayable', 'true')
            listItem.setArt({'thumb': video['photo_320']})
            listItem.setInfo(
                'video',
                {
                    'title': video['title'],
                    'plot': video['description'],
                    'duration': video['duration'],
                    'dateadded': datetime.fromtimestamp(video['adding_date']).strftime('%Y-%m-%d %H:%M:%S'),
                    'playcount': video['views'],
                }
            )
            items.append(
                (self.urlBase + '/play?oid={0}&id={1}'.format(video['owner_id'], video['id']), listItem, ISFOLDER_FALSE)
            )
        addDirectoryItems(self.handle, items, len(items))
        addSortMethod(self.handle, SORT_METHOD_DATEADDED)
        addSortMethod(self.handle, SORT_METHOD_DURATION)
        addSortMethod(self.handle, SORT_METHOD_PLAYCOUNT)
        endOfDirectory(self.handle)

    # play video
    def playVideo(self):
        video = {
            'url': resolve('https://vk.com/video{0}_{1}'.format(self.urlArgs['oid'], self.urlArgs['id'])),
        }
        setResolvedUrl(self.handle, True, ListItem().setPath(video['url']))


# and action! ;-)
if __name__ == '__main__':
    VKPlugin()
