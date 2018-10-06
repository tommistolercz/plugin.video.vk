# Import std lib modules
import datetime
import json
import os
import re
import sys
import urllib
import urllib2  # python3: urllib.request, urllib.error
import urlparse  # python3: urllib.parse

# Import kodi modules
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

# Import addon modules
sys.path.append('/Users/tom/Library/Application Support/Kodi/addons/plugin.video.vk/resources/lib')  # todo
import debug
sys.path.append('/Users/tom/Library/Application Support/Kodi/addons/plugin.video.vk/resources/lib/vk')  # todo
import vk


# Define constants
VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_VERSION = '5.85'
VK_API_LANG = 'en'
VK_API_TIMEOUT = 10
VK_API_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0 Safari/605.1.15'
ISFOLDER_TRUE = True
ISFOLDER_FALSE = False


# Define addon class
class MyAddon(object):

    # Initialize addon
    def __init__(self):
        self.addon = xbmcaddon.Addon()
        self.handle = int(sys.argv[1])
        # get addon settings
        self.settings = {
            'itemsPerPage': int(self.addon.getSetting('itemsPerPage')),
            'searchSortMethod': int(self.addon.getSetting('searchSortMethod')),
            'vkUserLogin': self.addon.getSetting('vkUserLogin'),  # todo
            'vkUserPassword': self.addon.getSetting('vkUserPassword'),  # todo
            'vkUserPhone': self.addon.getSetting('vkUserPhone'),  # todo
            'vkUserAccessToken': self.addon.getSetting('vkUserAccessToken'),
        }
        debug.log('self.settings', self.settings)
        # init vk api session using user credentials, then use saved user access token only
        # vk.logger.setLevel('DEBUG')
        if self.settings['vkUserAccessToken'] == '':
            session = vk.AuthSession(
                app_id=VK_API_APP_ID,
                user_login=self.settings['vkUserLogin'],
                user_password=self.settings['vkUserPassword'],
                # phone_number=self.settings['vkUserPhone'],
                scope=VK_API_SCOPE,
            )
            # save user access token
            self.addon.setSetting('vkUserAccessToken', session.access_token)
        else:
            session = vk.Session(
                access_token=self.settings['vkUserAccessToken']
            )
        # create vk api object
        self.vkapi = vk.API(
            session,
            v=VK_API_VERSION,
            lang=VK_API_LANG,
            timeout=VK_API_TIMEOUT
        )
        # request vk api to track addon usage
        response = self.vkapi.stats.trackVisitor()
        debug.log('self.vkapi.stats.trackVisitor()', response)
        # parse addon url
        self.urlBase = 'plugin://' + self.addon.getAddonInfo('id')
        self.urlPath = sys.argv[0].replace(self.urlBase, '')
        self.urlArgs = {}
        if sys.argv[2].startswith('?'):
            self.urlArgs = urlparse.parse_qs(sys.argv[2].lstrip('?'))
            for k, v in list(self.urlArgs.items()):
                self.urlArgs[k] = v.pop()
        debug.log('self.urlBase', self.urlBase)
        debug.log('self.urlPath', self.urlPath)
        debug.log('self.urlArgs', self.urlArgs)
        # dispatch addon routing
        self.routing = {
            # action handlers
            '/': self.listMainMenu,
            '/albums': self.listAlbums,
            '/albumvideos': self.listAlbumVideos,
            '/communities': self.listCommunities,
            '/communityvideos': self.listCommunityVideos,
            '/likedcommunities': self.listLikedCommunities,
            '/likedvideos': self.listLikedVideos,
            '/play': self.playVideo,
            '/search': self.searchVideos,
            '/searchhistory': self.listSearchHistory,
            '/stats': self.listStats,
            '/videos': self.listVideos,
            # contextmenu action handlers
            '/addtoalbum': self.addToAlbum,
            '/deletealbum': self.deleteAlbum,
            '/deletequery': self.deleteQuery,
            '/editquery': self.editQuery,
            '/likecommunity': self.likeCommunity,
            '/likevideo': self.likeVideo,
            '/playalbum': self.playAlbum,
            '/removefromalbum': self.removeFromAlbum,
            '/renamealbum': self.renameAlbum,
            '/reorderalbum': self.reorderAlbum,
            '/searchsimilar': self.searchSimilar,
            '/unfollowcommunity': self.unfollowCommunity,
            '/unlikecommunity': self.unlikeCommunity,
            '/unlikevideo': self.unlikeVideo,
        }
        if self.urlPath in self.routing:
            handler = self.routing[self.urlPath]
            if handler is not None:
                handler()

    # Add video to album (contextmenu action handler)
    def addToAlbum(self):
        pass

    # Build addon url (helper function)
    def buildUrl(self, urlPath, urlArgs=None):
        url = self.urlBase + urlPath
        if urlArgs is not None:
            url += '?' + urllib.urlencode(urlArgs)
        debug.log('self.buildUrl()', url)
        return url

    # Build list of communities (helper function)
    def buildListOfCommunities(self, listType, listData):
        listTypes = ['communities', 'likedcommunities']
        if listType not in listTypes:
            return False
        # create list items for communities
        listItems = []
        _nameKey = 'title' if listType == 'likedcommunities' else 'name'  # ugly!
        for community in listData['items']:
            if listType == 'likedcommunities':
                community['id'] = community['id'].split('_')[2]  # ugly!
            li = xbmcgui.ListItem(
                label=community[_nameKey],
            )
            li.setArt({'thumb': community['photo_200']})
            # todo: try to use infolabels (plot, ...) for showing community details
            li.addContextMenuItems(
                [
                    ('LIKE COMMUNITY', ''),  # todo
                    ('UNLIKE COMMUNITY', ''),  # todo
                    ('UNFOLLOW COMMUNITY', ''),  # todo
                ]
            )
            listItems.append(
                (self.buildUrl('/communityvideos', {'ownerId': '-{0}'.format(community['id'])}), li, ISFOLDER_TRUE)  # negative id required when owner is a community
            )
        # add paginator item  # todo: make this a function
        if listData['count'] > self.settings['itemsPerPage']:
            if listData['count'] > int(self.urlArgs['offset']) + self.settings['itemsPerPage']:
                self.urlArgs['offset'] += self.settings['itemsPerPage']  # next page's offset
                listItems.append(
                    (self.buildUrl(self.urlPath, self.urlArgs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), ISFOLDER_TRUE)
                )
        # show community list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listItems, len(listItems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    # Build list of videos (helper function)
    def buildListOfVideos(self, listType, listData):
        listTypes = ['videos', 'searchedvideos', 'albumvideos', 'communityvideos', 'likedvideos']  # todo: take list type into account
        if listType not in listTypes:
            return False
        # create list items for videos
        listItems = []
        for video in listData['items']:
            li = xbmcgui.ListItem(label=video['title'])
            li.setProperty('IsPlayable', 'true')
            li.setInfo(
                type='video',
                infoLabels={
                    'title': video['title'],  # todo: needed here vs move to playVideo()?
                    'plot': video['description'],
                    'duration': video['duration'],
                    'date': datetime.datetime.fromtimestamp(video['date']).strftime('%d.%m.%Y'),
                    # 'dateadded': datetime.datetime.fromtimestamp(video['adding_date']).strftime('%Y-%m-%d %H:%M:%S'),
                    # 'playcount': video['views'],  # todo
                }
            )
            if 'photo_800' in video:
                thumbMax = video['photo_800']
            elif 'photo_640' in video:
                thumbMax = video['photo_640']
            else:
                thumbMax = video['photo_320']
            li.setArt({'thumb': thumbMax})
            li.addContextMenuItems(
                [
                    ('LIKE VIDEO', 'RunPlugin({0})'.format(self.buildUrl('/likevideo', {'ownerId': video['owner_id'], 'id': video['id']}))),
                    ('UNLIKE VIDEO', 'RunPlugin({0})'.format(self.buildUrl('/unlikevideo', {'ownerId': video['owner_id'], 'id': video['id']}))),
                    ('ADD TO ALBUM', ''),  # todo
                    ('SEARCH SIMILAR', ''),  # todo
                ]
            )
            listItems.append(
                (self.buildUrl('/play', {'ownerId': video['owner_id'], 'id': video['id']}), li, ISFOLDER_FALSE)
            )
        # add paginator item
        if listData['count'] > self.settings['itemsPerPage']:
            if listData['count'] > int(self.urlArgs['offset']) + self.settings['itemsPerPage']:
                self.urlArgs['offset'] += self.settings['itemsPerPage']  # next page's offset
                listItems.append(
                    (self.buildUrl(self.urlPath, self.urlArgs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), ISFOLDER_TRUE)
                )
        # show video list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'videos')
        xbmcplugin.addDirectoryItems(self.handle, listItems, len(listItems))
        searchSortMethods = [xbmcplugin.SORT_METHOD_DATE, xbmcplugin.SORT_METHOD_DURATION, xbmcplugin.SORT_METHOD_PLAYCOUNT]  # todo: playcount?
        xbmcplugin.addSortMethod(self.handle, searchSortMethods[self.settings['searchSortMethod']])  # todo: take listType into account
        xbmcplugin.endOfDirectory(self.handle)

    # Delete album (contextmenu action handler)
    def deleteAlbum(self):
        pass

    # Delete query from search history (contextmenu action handler)
    def deleteQuery(self):
        pass

    # Edit query in search history (contextmenu action handler)
    def editQuery(self):
        pass

    # Like community (contextmenu action handler)
    def likeCommunity(self):
        pass

    # Like video (contextmenu action handler)
    def likeVideo(self):
        response = self.vkapi.likes.add(
            type='video',
            owner_id=self.urlArgs['ownerId'],
            item_id=self.urlArgs['id'],
        )
        debug.log('self.vkapi.likes.add()', response)
        xbmcgui.Dialog().notification('LIKES:', '{0}'.format(response['likes']))

    # List user's albums (action handler)
    def listAlbums(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for video albums
        response = self.vkapi.video.getAlbums(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        debug.log('self.vkapi.video.getAlbums()', response)
        # notify of total items count
        xbmcgui.Dialog().notification('ALBUMS:', '{0}'.format(response['count']))
        # create list items for albums
        listItems = []
        for album in response['items']:
            li = xbmcgui.ListItem(
                label='{0} [COLOR blue]({1})[/COLOR]'.format(album['title'], album['count']),
            )
            # todo: try to use infolabels (plot, ...) for showing album details
            if album['count'] > 0:  # empty albums have no thumbs
                li.setArt({'thumb': album['photo_320']})
            li.addContextMenuItems(
                [
                    ('PLAY ALBUM', ''),  # todo
                    ('RENAME ALBUM', ''),  # todo
                    ('REORDER ALBUM', ''),  # todo
                    ('DELETE ALBUM', ''),  # todo
                ]
            )
            listItems.append(
                (self.buildUrl('/albumvideos', {'albumId': album['id']}), li, ISFOLDER_TRUE)
            )
        # add paginator item  # todo: make this a function
        if response['count'] > self.settings['itemsPerPage']:
            if response['count'] > int(self.urlArgs['offset']) + self.settings['itemsPerPage']:
                self.urlArgs['offset'] += self.settings['itemsPerPage']  # next page's offset
                listItems.append(
                    (self.buildUrl(self.urlPath, self.urlArgs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), ISFOLDER_TRUE)
                )
        # show album list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listItems, len(listItems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    # List user's album videos (action handler)
    def listAlbumVideos(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for album videos
        response = self.vkapi.video.get(
            extended=1,
            album_id=self.urlArgs['albumId'],
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        debug.log('self.vkapi.video.get()', response)
        # notify of total items count
        xbmcgui.Dialog().notification('ALBUM VIDEOS:', '{0}'.format(response['count']))
        # build list of album videos
        self.buildListOfVideos('albumvideos', response)

    # List user's communities (action handler)
    def listCommunities(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for communities
        response = self.vkapi.groups.get(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        debug.log('self.vkapi.groups.get()', response)
        # notify of total items count
        xbmcgui.Dialog().notification('COMMUNITIES:', '{0}'.format(response['count']))
        # build list of communities
        self.buildListOfCommunities('communities', response)  # todo: make listType=communities default?

    # List user's community videos (action handler)
    def listCommunityVideos(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for community videos
        response = self.vkapi.video.get(
            extended=1,
            owner_id=self.urlArgs['ownerId'],
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        debug.log('self.vkapi.video.get()', response)
        # notify of total items count
        xbmcgui.Dialog().notification('COMMUNITY VIDEOS:', '{0}'.format(response['count']))
        # build list of community videos
        self.buildListOfVideos('communityvideos', response)

    # List user's liked communities (action handler)
    def listLikedCommunities(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for liked communities
        response = self.vkapi.fave.getLinks(
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        debug.log('self.vkapi.fave.getLinks()', response)
        # notify of total items count
        xbmcgui.Dialog().notification('LIKED COMMUNITIES:', '{0}'.format(response['count']))
        # build list of liked communities
        self.buildListOfCommunities('likedcommunities', response)

    # List user's liked videos (action handler)
    def listLikedVideos(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for liked videos
        response = self.vkapi.fave.getVideos(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        debug.log('self.vkapi.fave.getVideos()', response)
        # notify of total items count
        xbmcgui.Dialog().notification('LIKED VIDEOS:', '{0}'.format(response['count']))
        # build list of liked videos
        self.buildListOfVideos('likedvideos', response)

    # List main menu (action handler)
    def listMainMenu(self):
        # request vk api for menu counters (by executing a stored function)
        counters = self.vkapi.execute.getMenuCounters()
        debug.log('self.vkapi.execute.getMenuCounters()', counters)
        # create list items for main menu
        listItems = [
            (self.buildUrl('/search'), xbmcgui.ListItem('SEARCH'), ISFOLDER_TRUE),
            (self.buildUrl('/searchhistory'), xbmcgui.ListItem('SEARCH HISTORY'), ISFOLDER_TRUE),
            (self.buildUrl('/videos'), xbmcgui.ListItem('VIDEOS [COLOR blue]({0})[/COLOR]'.format(counters['videos'])), ISFOLDER_TRUE),
            (self.buildUrl('/albums'), xbmcgui.ListItem('ALBUMS [COLOR blue]({0})[/COLOR]'.format(counters['albums'])), ISFOLDER_TRUE),
            (self.buildUrl('/communities'), xbmcgui.ListItem('COMMUNITIES [COLOR blue]({0})[/COLOR]'.format(counters['communities'])), ISFOLDER_TRUE),
            (self.buildUrl('/likedvideos'), xbmcgui.ListItem('LIKED VIDEOS [COLOR blue]({0})[/COLOR]'.format(counters['likedVideos'])), ISFOLDER_TRUE),
            (self.buildUrl('/likedcommunities'), xbmcgui.ListItem('LIKED COMMUNITIES [COLOR blue]({0})[/COLOR]'.format(counters['likedCommunities'])), ISFOLDER_TRUE),
            (self.buildUrl('/stats'), xbmcgui.ListItem('STATS'), ISFOLDER_TRUE),
        ]
        # show main menu list in kodi
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listItems, len(listItems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    # List search history (action handler)
    def listSearchHistory(self):
        # load search history from json file if exists
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), 'searchhistory.json')
        if os.path.exists(fp):
            searchHistory = {}
            with open(fp) as f:
                searchHistory = json.load(f)
            debug.log('searchHistory', searchHistory)
        # create list items for search history sorted by timestamp reversed
        listItems = []
        for search in sorted(searchHistory['items'], key=lambda x: x['timestamp'], reverse=True):
            li = xbmcgui.ListItem(
                label=search['q'],
                label2=datetime.datetime.fromtimestamp(search['timestamp']).strftime('%d.%m.%Y'),
            )
            li.addContextMenuItems(
                [
                    ('EDIT QUERY', ''),  # todo
                    ('DELETE QUERY', ''),  # todo
                ]
            )
            listItems.append(
                (self.buildUrl('/search', {'q': search['q']}), li, ISFOLDER_TRUE)
            )
        # show search history list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listItems, len(listItems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_DATE)
        xbmcplugin.endOfDirectory(self.handle)

    # List stats (action handler)
    def listStats(self):
        '''
        totals:
            timeUsageTotal
            countVideosPlayedTotal
        session (current):
            timeUsageSession
            countVideosPlayedSession
        session stats:
            timeUsageSessionAvg
            timeUsageSessionMax
            countVideosPlayedSessionAvg
            countVideosPlayedSessionMax
        '''
        pass

    # List user's videos (action handler)
    def listVideos(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for videos
        response = self.vkapi.video.get(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        debug.log('self.vkapi.video.get()', response)
        # notify of total items count
        xbmcgui.Dialog().notification('VIDEOS:', '{0}'.format(response['count']))
        # build list of videos
        self.buildListOfVideos('videos', response)

    # Play album (contextmenu action handler)
    def playAlbum(self):
        pass

    # Play video (action handler)
    def playVideo(self):
        # request vk api for video
        response = self.vkapi.video.get(
            videos='{0}_{1}'.format(self.urlArgs['ownerId'], self.urlArgs['id']),
        )
        video = response['items'].pop()
        debug.log('video', video)
        # resolve video url into playable stream/s
        videoUrl = video['player']
        debug.log('videoUrl', videoUrl)
        urlo = urllib2.urlopen(
            urllib2.Request(url=videoUrl, headers={'User-Agent': VK_API_UA})
        )
        html = urlo.read()
        po = re.compile('"url(\d+)":"([^"]+)"')
        matches = po.findall(html)
        playableStreams = {}
        for m in matches:
            quality = str(m[0])
            stream = m[1].replace('\\', '')
            playableStreams[quality] = stream
        debug.log('playableStreams', playableStreams)
        # create item for kodi player (using max avail. quality)
        if playableStreams:
            qualityMax = max(playableStreams.keys())
            li = xbmcgui.ListItem(path=playableStreams[qualityMax])
            # todo: set info labels?
            xbmcplugin.setContent(self.handle, 'videos')
            xbmcplugin.setResolvedUrl(self.handle, True, li)
        # or notify of error
        else:
            xbmcgui.Dialog().notification('ERROR', 'Video cannot be played', icon=xbmcgui.NOTIFICATION_ERROR)
            debug.log('ERROR: Video cannot be played', videoUrl)  # todo
            return False

    # Remove video from album (contextmenu action handler)
    def removeFromAlbum(self):
        pass

    # Rename album (contextmenu action handler)
    def renameAlbum(self):
        pass

    # Reorder album (contextmenu action handler)
    def reorderAlbum(self):
        pass

    # Search similar videos (contextmenu action handler)
    def searchSimilar(self):
        pass

    # Search videos (action handler)
    def searchVideos(self):
        # if there is not a search query let the user enter a new one
        if 'q' not in self.urlArgs:
            self.urlArgs['q'] = xbmcgui.Dialog().input('ENTER SEARCH QUERY')
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for searched videos
        response = self.vkapi.video.search(
            extended=1,
            hd=1,
            adult=1,
            search_own=1,  # todo: as user setting?
            longer=600,  # todo: as user setting with default=600 (10min)
            shorter=3600,  # todo: as user setting with default=3600 (60min)
            sort=self.settings['searchSortMethod'],
            q=self.urlArgs['q'],
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        debug.log('self.vkapi.video.search()', response)
        # update search history json file, if not exists create a new one
        pass  # todo
        # notify of total items count
        xbmcgui.Dialog().notification('SEARCHED VIDEOS:', '{0}'.format(response['count']))
        # build list of searched videos
        self.buildListOfVideos('searchedvideos', response)

    # Unfollow community (contextmenu action handler)
    def unfollowCommunity(self):
        pass

    # Unlike community (contextmenu action handler)
    def unlikeCommunity(self):
        pass

    # Unlike video (contextmenu action handler)
    def unlikeVideo(self):
        response = self.vkapi.likes.delete(
            type='video',
            owner_id=self.urlArgs['ownerId'],
            item_id=self.urlArgs['id'],
        )
        debug.log('self.vkapi.likes.delete()', response)
        xbmcgui.Dialog().notification('LIKES:', '{0}'.format(response['likes']))


# Run addon
if __name__ == '__main__':
    MyAddon()
