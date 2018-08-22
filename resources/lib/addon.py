from sys import argv
from urlparse import parse_qs
from xbmcaddon import Addon
from xbmcgui import ListItem, Dialog
from xbmcplugin import setContent, setResolvedUrl, addDirectoryItems, endOfDirectory, addSortMethod, SORT_METHOD_NONE, SORT_METHOD_LABEL, SORT_METHOD_DATEADDED, SORT_METHOD_DURATION, SORT_METHOD_PLAYCOUNT
from requests import get
from urlresolver import resolve
from datetime import datetime
from math import ceil

# debugger
# <import addon="script.module.web-pdb"/>
# import web_pdb; web_pdb.set_trace()

PLUGIN_CONTENT_TYPE_VIDEOS = 'videos'
VK_API_VERSION = '5.80'
ISFOLDER_TRUE = True
ISFOLDER_FALSE = False


class VKPlugin(object):

    # Initialize plugin
    def __init__(self):
        self.handle = int(argv[1])
        self.addon = Addon()
        self.dialog = Dialog()
        # content type
        setContent(self.handle, PLUGIN_CONTENT_TYPE_VIDEOS)
        # user settings
        self.settings = {
            'itemsPerPage': int(self.addon.getSetting('itemsPerPage')),
            'vkUserAccessToken': self.addon.getSetting('vkUserAccessToken'),
        }
        # url parsing
        self.urlBase = 'plugin://' + self.addon.getAddonInfo('id')
        self.urlPath = argv[0].replace(self.urlBase, '')
        self.urlQS = argv[2]
        self.urlArgs = {}
        if self.urlQS.startswith('?'):
            self.urlArgs = parse_qs(self.urlQS.lstrip('?'))
            for k, v in self.urlArgs.items():
                self.urlArgs[k] = v.pop()
        # dispatch routing
        self.dispatch()

    # Dispatch plugin's routing
    def dispatch(self):
        if self.urlPath == '/':
            self.listRoot()
        elif self.urlPath == '/videos':
            self.listVideos()
        elif self.urlPath == '/videos/search':
            if not ('new' in self.urlArgs or 'q' in self.urlArgs):
                self.listSearchHistory()
            elif 'new' in self.urlArgs:
                self.newSearch()
            elif 'q' in self.urlArgs:
                self.listSearchedVideos()
        elif self.urlPath == '/videos/play':
            self.playVideo()
        elif self.urlPath == '/communities':
            self.listCommunities()

    # List root directory
    def listRoot(self):
        items = [
            (self.urlBase + '/videos?offset=0', ListItem(self.addon.getLocalizedString(30005)), ISFOLDER_TRUE),
            (self.urlBase + '/communities?offset=0', ListItem(self.addon.getLocalizedString(30008)), ISFOLDER_TRUE),
        ]
        addSortMethod(self.handle, SORT_METHOD_NONE)
        addDirectoryItems(self.handle, items, len(items))
        endOfDirectory(self.handle)

    # List videos
    def listVideos(self):
        # vk api request
        requestUrl = 'https://api.vk.com/method/video.get'
        requestParams = {
            'access_token': self.settings['vkUserAccessToken'],
            'v': VK_API_VERSION,
            'extended': 1,
            'offset': int(self.urlArgs['offset']),  # todo: test if set (rather than set it default)
            'count': self.settings['itemsPerPage'],
        }
        videos = get(requestUrl, requestParams).json()
        items = []
        # searchvideos item
        items.append(
            (self.urlBase + '/videos/search', ListItem(self.addon.getLocalizedString(30006)), ISFOLDER_TRUE)
        )
        # pagination item
        if videos['response']['count'] > self.settings['itemsPerPage']:
            if videos['response']['count'] > int(self.urlArgs['offset']) + self.settings['itemsPerPage']:
                offsetNext = int(self.urlArgs['offset']) + self.settings['itemsPerPage']
                items.append(
                    (self.urlBase + '/videos?offset={0}'.format(offsetNext), ListItem(self.addon.getLocalizedString(30007)), ISFOLDER_TRUE)
                )
        # video items
        for video in videos['response']['items']:
            listItem = ListItem(video['title'])
            listItem.setProperty('IsPlayable', 'true')
            listItem.setArt({'thumb': video['photo_320']})
            infoLabels = {
                'title': video['title'],
                'plot': video['description'],
                'duration': video['duration'],
                'dateadded': datetime.fromtimestamp(video['adding_date']).strftime('%Y-%m-%d %H:%M:%S'),
                'playcount': video['views'],
            }
            listItem.setInfo('video', infoLabels)
            # TODO: add width/height info (if any)
            items.append(
                (self.urlBase + '/videos/play?oidid={0}_{1}'.format(video['owner_id'], video['id']), listItem, ISFOLDER_FALSE)
            )
        addSortMethod(self.handle, SORT_METHOD_DATEADDED)
        addSortMethod(self.handle, SORT_METHOD_DURATION)
        addSortMethod(self.handle, SORT_METHOD_PLAYCOUNT)
        addDirectoryItems(self.handle, items, len(items))
        endOfDirectory(self.handle)
        # issue: when entering list of videos (on page 1 only) the additional list items (search, paging) are sorted at the end of list

    def listSearchHistory(self):
        items = []
        # newsearch item
        items.append(
            (self.urlBase + '/videos/search?new=1', ListItem(self.addon.getLocalizedString(30009)), ISFOLDER_TRUE)
        )
        # searchhistory items 
        # todo: get from db (pickle?)
        searchHistory = {
            'count': 1,
            'items': [
                {
                    'q': 'hd 1080 russian',
                    'date': 1533025439,
                    'count': 1,
                },
            ]
        }
        for search in searchHistory['items']:
            items.append(
                (self.urlBase + '/videos/search?q={0}'.format(search['q']), ListItem(search['q']), ISFOLDER_TRUE)
            )
        addSortMethod(self.handle, SORT_METHOD_LABEL)
        addDirectoryItems(self.handle, items, len(items))
        endOfDirectory(self.handle)

    # New search (entering query)
    def newSearch(self):
        q = self.dialog.input('Search query:')
        # todo
    
    # List searched videos
    def listSearchedVideos(self):
     # vk api request
        requestUrl = 'https://api.vk.com/method/video.search'
        requestParams = {
            'access_token': self.settings['vkUserAccessToken'],
            'v': VK_API_VERSION,
            'extended': 1,
            'q': self.urlArgs['q'],
            'offset': int(self.urlArgs['offset']),   # todo: test if set (rather than set it default)
            'count': self.settings['itemsPerPage'],
        }
        videos = get(requestUrl, requestParams).json()
    
    # Play video 
    def playVideo(self):
        videoUrl = 'https://vk.com/video{0}'.format(self.urlArgs['oidid'])
        resolvedUrl = resolve(videoUrl)
        listItem = ListItem()
        listItem.setPath(resolvedUrl)
        setResolvedUrl(self.handle, True, listItem)

    # List communities
    def listCommunities(self):
        pass


# Run plugin
if __name__ == '__main__':
    VKPlugin()
