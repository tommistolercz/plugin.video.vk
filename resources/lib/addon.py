from sys import argv
from urlparse import parse_qs
from xbmcaddon import Addon
from xbmcgui import ListItem
from xbmcplugin import setContent, setResolvedUrl, addDirectoryItems, endOfDirectory, addSortMethod, SORT_METHOD_NONE, SORT_METHOD_DATEADDED, SORT_METHOD_DURATION, SORT_METHOD_PLAYCOUNT
from requests import get
from urlresolver import resolve
from datetime import datetime

# debug
# addon.xml: <import addon="script.module.web-pdb"/>
# import web_pdb; web_pdb.set_trace()


class VKPlugin(object):

    # plugin initialization
    def __init__(self):
        self.addon = Addon()
        self.handle = int(argv[1])
        self.url = argv[0]
        self.base = 'plugin://plugin.video.vk'
        self.path = self.url.replace(self.base, '')
        self.query = argv[2]
        self.args = {}
        if self.query.startswith('?'):
            self.args = parse_qs(self.query.lstrip('?'))
        self.userSettings = {
            'contentType': self.addon.getSetting('contentType'),
            'itemsPerPage': int(self.addon.getSetting('itemsPerPage')),
            'vkApiVersion': float(self.addon.getSetting('vkApiVersion')),
            'vkUserAccessToken': self.addon.getSetting('vkUserAccessToken'),
        }
        setContent(self.handle, self.userSettings['contentType'])
        self.dispatch()

    # plugin routing
    def dispatch(self):
        if self.path == '/':
            self.listRoot()
        elif self.path == '/videos':
            self.listVideos()
        elif self.path == '/play':
            self.playVideo()

    # plugin directory: /
    def listRoot(self):
        isFolder = True
        listItems = [
            (self.base + '/videos', ListItem(self.addon.getLocalizedString(30005)), isFolder),
        ]
        addDirectoryItems(self.handle, listItems, len(listItems))
        addSortMethod(self.handle, SORT_METHOD_NONE)
        endOfDirectory(self.handle)

    # plugin directory: /videos
    def listVideos(self):
        requestUrl = 'https://api.vk.com/method/video.get'
        requestParams = {
            'access_token': self.userSettings['vkUserAccessToken'],
            'count': self.userSettings['itemsPerPage'],
            'offset': 0,
            'v': self.userSettings['vkApiVersion'],
        }
        videos = get(requestUrl, requestParams).json()
        videosTotalCount = int(videos['response']['count'])
        listItems = []
        isFolder = False
        for video in videos['response']['items']:
            listItem = ListItem(video['title'])
            listItem.setArt({'thumb': video['photo_320']})
            listItem.setInfo(
                'video',
                {
                    'title': video['title'],
                    'plot': video['description'],
                    'duration': video['duration'],
                    'date': datetime.fromtimestamp(video['date']).strftime('%d.%m.%Y'),
                    'dateadded': datetime.fromtimestamp(video['adding_date']).strftime('%Y-%m-%d %H:%M:%S'),
                    'playcount': video['views'],
                }
            )
            listItem.setProperty('IsPlayable', 'true')
            listItems.append((self.base + '/play?oid={0}&id={1}'.format(video['owner_id'], video['id']), listItem, isFolder))
        addDirectoryItems(self.handle, listItems, len(listItems))
        addSortMethod(self.handle, SORT_METHOD_DATEADDED)
        addSortMethod(self.handle, SORT_METHOD_DURATION)
        addSortMethod(self.handle, SORT_METHOD_PLAYCOUNT)
        endOfDirectory(self.handle)

    # play video
    def playVideo(self):
        video = {
            'oid': self.args['oid'].pop(),
            'id': self.args['id'].pop(),
        }
        video['player_vk'] = 'https://vk.com/video{0}_{1}'.format(video['oid'], video['id'])
        video['url'] = resolve(video['player_vk'])
        playItem = ListItem()
        playItem.setPath(video['url'])
        setResolvedUrl(self.handle, True, playItem)


# and action! ;-)
if __name__ == '__main__':
    VKPlugin()
