__all__ = []

"""
VK (plugin.video.vk)
Kodi add-on for watching videos from VK.com social network.

:features:
- todo

:copyright: (c) 2018 TomMistolerCZ.
:license: GNU GPL v2, see LICENSE for more details.
"""

import datetime
import json
import os
import pickle
import re
import sys
import time
import urllib
import urlparse  # todo: python3: urllib.parse

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

sys.path.append('/Users/tom/Library/Application Support/Kodi/addons/plugin.video.vk/resources/lib')  # todo: ugly!
sys.path.append('/Users/tom/Library/Application Support/Kodi/addons/plugin.video.vk/resources/lib/vk')  # todo: ugly!
import vk  # todo: replace by inpos vk module?


VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_VERSION = '5.85'
VK_API_LANG = 'ru'
VK_VIDEOINFO_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246'
ADDON_DATA_FILE_COOKIEJAR = '.cookiejar'
ADDON_DATA_FILE_SEARCH = 'search.json'

ISFOLDER_TRUE = True
ISFOLDER_FALSE = False


class VkAddonError(Exception):
    def __init__():
        pass


class VkAddon():

    def __init__(self):
        """
        Initialize addon instance.
        """
        self.addon = xbmcaddon.Addon()
        self.handle = int(sys.argv[1])
        self.settings = self.getSettings()
        # init vk session  # todo: too complex
        if self.settings['vkUserAccessToken'] == '':
            credentials = {
                'login': xbmcgui.Dialog().input('ENTER VK USER LOGIN (EMAIL)'),
                'password': xbmcgui.Dialog().input('ENTER VK USER PASSWORD', option=xbmcgui.ALPHANUM_HIDE_INPUT),
            }
            self.vkSession = vk.AuthSession(VK_API_APP_ID, credentials['login'], credentials['password'], VK_API_SCOPE)
            self.addon.setSetting('vkUserAccessToken', self.vkSession.access_token)
            self.saveCookies(self.vkSession.auth_session.cookies)
        else:
            self.vkSession = vk.Session(self.settings['vkUserAccessToken'])
            self.vkSession.requests_session.cookies = self.loadCookies()
        # create vk api object
        self.vkApi = vk.API(self.vkSession, v=VK_API_VERSION, lang=VK_API_LANG)
        # request vk api for tracking the addon usage
        self.tracking = bool(self.vkApi.stats.trackVisitor())
        self.log('vk api usage tracking: {0}'.format(self.tracking))
        # parse addon url
        self.urlBase = 'plugin://' + self.addon.getAddonInfo('id')
        self.urlPath = sys.argv[0].replace(self.urlBase, '')
        self.urlArgs = {}
        if sys.argv[2].startswith('?'):
            self.urlArgs = urlparse.parse_qs(sys.argv[2].lstrip('?'))
            for k, v in list(self.urlArgs.items()):
                self.urlArgs[k] = v.pop()
        self.log('addon url parsed: {0} {1} {2}'.format(self.urlBase, self.urlPath, self.urlArgs))
        # dispatch addon routing by calling applicable action handler
        self.routing = {  # todo: pass urlargs as **kwargs
            # menu actions:
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
            # contextmenu actions:
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
            self.routing[self.urlPath]()

    def addToAlbum(self):
        """
        Add video into album.
        """
        pass  # todo

    def buildUrl(self, urlPath, urlArgs=None):
        """
        Build addon url.
        :param urlPath:
        :param urlArgs:
        :returns: url
        """
        url = self.urlBase + urlPath
        if urlArgs is not None:
            url += '?' + urllib.urlencode(urlArgs)
        return url

    def buildListOfCommunities(self, listType, listData):
        """
        Build list of communities.
        :param listType:
        :param listData:
        """
        listTypes = ['communities', 'likedcommunities']
        if listType not in listTypes:
            return False  # todo: raise exception
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
            # todo: use infolabels (plot, ...) for showing community details?
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

    def buildListOfVideos(self, listType, listData):
        """
        Build list of videos.
        :param listType:
        :param listData:
        """
        # listTypes = ['videos', 'searchedvideos', 'albumvideos', 'communityvideos', 'likedvideos']  # todo: take into account
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
                    # 'playcount': video['views'],  # todo
                }
            )
            if 'photo_800' in video:  # todo: ugly!
                thumbMax = video['photo_800']
            elif 'photo_640' in video:
                thumbMax = video['photo_640']
            else:
                thumbMax = video['photo_320']
            li.setArt({'thumb': thumbMax})
            li.addContextMenuItems(
                [
                    ('LIKE VIDEO', 'RunPlugin({0})'.format(self.buildUrl('/likevideo', {'ownerId': video['owner_id'], 'id': video['id']}))),
                    # ('LIKE VIDEO ALT', 'Container.Update({0})'.format(self.buildUrl('/likevideo', {'ownerId': video['owner_id'], 'id': video['id']}))),
                    ('UNLIKE VIDEO', 'RunPlugin({0})'.format(self.buildUrl('/unlikevideo', {'ownerId': video['owner_id'], 'id': video['id']}))),
                    # ('UNLIKE VIDEO ALT', 'Container.Update({0})'.format(self.buildUrl('/unlikevideo', {'ownerId': video['owner_id'], 'id': video['id']}))),
                    # ('ADD TO ALBUM', ''),  # todo
                    # ('SEARCH SIMILAR', ''),  # todo
                ]
            )
            listItems.append(
                (self.buildUrl('/play', {'ownerId': video['owner_id'], 'id': video['id']}), li, ISFOLDER_FALSE)
            )
        # add paginator item
        if int(listData['count']) > int(self.settings['itemsPerPage']):
            if int(listData['count']) > int(self.urlArgs['offset']) + int(self.settings['itemsPerPage']):
                self.urlArgs['offset'] = int(self.urlArgs['offset']) + int(self.settings['itemsPerPage'])  # next page's offset
                listItems.append(
                    (self.buildUrl(self.urlPath, self.urlArgs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), ISFOLDER_TRUE)
                )
        # show video list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'videos')
        xbmcplugin.addDirectoryItems(self.handle, listItems, len(listItems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def deleteAlbum(self):
        """
        Delete album (contextmenu action handler).
        """
        pass  # todo

    def deleteQuery(self):
        """
        Delete query from search history (contextmenu action handler).
        """
        pass

    def editQuery(self):
        """
        Edit query in search history (contextmenu action handler).
        """
        pass  # todo

    def getSettings(self):
        """
        Get addon settings managed by user via Kodi GUI.
        :returns: dict
        """
        settings = {
            'vkUserAccessToken': self.addon.getSetting('vkUserAccessToken'),
            'itemsPerPage': self.addon.getSetting('itemsPerPage'),  # todo: itemsPerPage int => str
            'searchAdult': self.addon.getSetting('searchAdult'),
            'searchOwn': self.addon.getSetting('searchOwn'),
            'searchLonger': self.addon.getSetting('searchLonger'),
            'searchShorter': self.addon.getSetting('searchShorter'),
            'searchSort': self.addon.getSetting('searchSort'),
        }
        self.log('Settings: {0}'.format(settings))
        return settings

    def likeCommunity(self):
        """
        Like community (contextmenu action handler).
        """
        pass

    def likeVideo(self):
        """
        Like video (contextmenu action handler).
        """
        oidid = '{0}_{1}'.format(self.urlArgs['ownerId'], self.urlArgs['id'])
        like = self.vkApi.likes.add(
            type='video',
            owner_id=self.urlArgs['ownerId'],
            item_id=self.urlArgs['id'],
        )
        self.log('Like added: {0} ({1} likes)'.format(oidid, like['likes']))
        self.notify('Like added. ({0} likes)'.format(like['likes']))

    def listAlbums(self):
        """
        List user's albums (action handler).
        """
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for albums
        albums = self.vkApi.video.getAlbums(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        # self.log('listAlbums(): albums:', albums)  # todo rest...
        # create list items for albums
        listItems = []
        for album in albums['items']:
            li = xbmcgui.ListItem(
                label='{0} [COLOR blue]({1})[/COLOR]'.format(album['title'], album['count']),
            )
            # todo: use infolabels (plot, ...) for showing album details?
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
        if albums['count'] > self.settings['itemsPerPage']:
            if albums['count'] > int(self.urlArgs['offset']) + self.settings['itemsPerPage']:
                self.urlArgs['offset'] += self.settings['itemsPerPage']  # next page's offset
                listItems.append(
                    (self.buildUrl(self.urlPath, self.urlArgs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), ISFOLDER_TRUE)
                )
        # show album list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listItems, len(listItems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def listAlbumVideos(self):
        """
        List user's album videos (action handler).
        """
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for album videos
        albumVideos = self.vkApi.video.get(
            extended=1,
            album_id=self.urlArgs['albumId'],
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        # self.log('listAlbumVideos(): albumVideos:', albumVideos)
        # build list of album videos
        self.buildListOfVideos(listType='albumvideos', listData=albumVideos)

    def listCommunities(self):
        """
        List user's communities (action handler).
        """
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for communities
        communities = self.vkApi.groups.get(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        # self.log('listCommunities(): communities:', communities)
        # build list of communities
        self.buildListOfCommunities(listType='communities', listData=communities)  # todo: listType=communities default?

    def listCommunityVideos(self):
        """
        List user's community videos (action handler).
        """
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for community videos
        communityVideos = self.vkApi.video.get(
            extended=1,
            owner_id=self.urlArgs['ownerId'],
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        # self.log('listCommunityVideos(): communityVideos:', communityVideos)
        # build list of community videos
        self.buildListOfVideos(listType='communityvideos', listData=communityVideos)

    def listLikedCommunities(self):
        """
        List user's liked communities (action handler).
        """
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for liked communities
        likedCommunities = self.vkApi.fave.getLinks(
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        # self.log('listLikedCommunities(): likedCommunities:', likedCommunities)
        # build list of liked communities
        self.buildListOfCommunities(listType='likedcommunities', listData=likedCommunities)

    def listLikedVideos(self):
        """
        List user's liked videos (action handler).
        """
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for liked videos
        likedVideos = self.vkApi.fave.getVideos(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        # self.log('listLikedVideos(): likedVideos:', likedVideos)
        # build list of liked videos
        self.buildListOfVideos('likedvideos', likedVideos)

    def listMainMenu(self):
        """
        List main menu (action handler).
        """
        # request vk api for menu counters (by executing a stored function)
        try:
            counters = self.vkApi.execute.getMenuCounters()
        except vk.exceptions.VkAPIError:
            counters = {'videos': 'n/a', 'albums': 'n/a', 'communities': 'n/a', 'likedVideos': 'n/a', 'likedCommunities': 'n/a'}  # todo: better?
        # self.log('listMainMenu(): counters:', counters)
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

    def listSearchHistory(self):
        """
        List search history (action handler).
        """
        # load search history
        searchHistory = self.loadSearchHistory()
        # self.log('listSearchHistory(): searchHistory:', searchHistory)
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
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def listStats(self):
        """
        List stats (action handler).
        Metrics:
            - totals:
                - timeUsageTotal
                - countVideosPlayedTotal
            - session (current):
                - timeUsageSession
                - countVideosPlayedSession
            - session stats:
                - timeUsageSessionAvg
                - timeUsageSessionMax
                - countVideosPlayedSessionAvg
                - countVideosPlayedSessionMax
        """
        pass  # todo

    def listVideos(self):
        """
        List user's videos (action handler).
        """
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for videos
        videos = self.vkApi.video.get(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        # self.log('listVideos(): videos:', videos)
        # build list of videos
        self.buildListOfVideos(listType='videos', listData=videos)

    def loadCookies(self):
        """
        load session cookies from addon data file (helper function).
        """
        cookieJar = {}
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_COOKIEJAR)
        if os.path.exists(fp):  # todo: else raise exception
            with open(fp, 'rb') as f:
                cookieJar = pickle.load(f)
        return cookieJar

    def loadSearchHistory(self):
        """
        Load search history from addon data file (helper function).
        """
        sh = {'items': []}
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_SEARCH)
        if os.path.exists(fp):
            with open(fp) as f:
                sh = json.load(f)
        return sh

    def log(self, msg, level=xbmc.LOGDEBUG):
        """
        Log message into default Kodi.log using an uniform style (incl. addon id).
        :param msg: str
        :param level: xbmc.LOGDEBUG (default)
        """
        msg = '{0}: {1}'.format(self.addon.getAddonInfo('id'), msg)
        xbmc.log(msg, level)

    def notify(self, msg, icon=xbmcgui.NOTIFICATION_INFO):
        """
        Notify user using uniform style (helper function).
        :param msg: str
        :param icon: xbmcgui.NOTIFICATION_INFO (default)
        """
        heading = self.addon.getAddonInfo('id')
        xbmcgui.Dialog().notification(heading, msg, icon)

    def playAlbum(self):
        """
        Play album (contextmenu action handler).
        """
        pass  # todo

    def playVideo(self):
        """
        Play video (action handler).
        """
        oidid = '{0}_{1}'.format(self.urlArgs['ownerId'], self.urlArgs['id'])
        self.log('Trying to play video: {0}'.format(oidid))
        # resolve playable streams using vk videoinfo api (hack)
        try:
            vi = self.vkSession.requests_session.get(
                url='https://vk.com/al_video.php?act=show_inline&al=1&video={0}'.format(oidid),
                headers={'User-Agent': VK_VIDEOINFO_UA},
                # logged user's cookies sent autom. (set/restored within vk session init)
            )
            # self.log('playVideo(): vi.url:', vi.url)
            # self.log('playVideo(): vi.text:', vi.text)
            # matches = re.findall(r'<source src="([^"]+\.(\d+)\.[^"]+)" type="video/mp4" />', vi.text.replace('\\', ''))  # alt
            matches = re.findall(r'"url(\d+)":"([^"]+)"', vi.text.replace('\\', ''))
            playableStreams = {}
            for m in matches:
                playableStreams[int(m[0])] = m[1]
            # self.log('playVideo(): playableStreams:', playableStreams)
            if not playableStreams:
                raise VkAddonError
        except VkAddonError:
            self.log('Video cannot be played: {0}'.format(oidid), level=xbmc.LOGERROR)
            self.notify('Video cannot be played.', icon=xbmcgui.NOTIFICATION_ERROR)
            return
        # create item for kodi player (using max avail. quality)
        xbmcplugin.setContent(self.handle, 'videos')
        qualityMax = max(playableStreams.keys())
        li = xbmcgui.ListItem(path=playableStreams[qualityMax])
        xbmcplugin.setResolvedUrl(self.handle, True, li)

    def removeFromAlbum(self):
        """
        Remove video from album (contextmenu action handler).
        """
        pass  # todo

    def renameAlbum(self):
        """
        Rename album (contextmenu action handler).
        """
        pass  # todo

    def reorderAlbum(self):
        """
        Reorder album (contextmenu action handler).
        """
        pass  # todo

    def saveCookies(self, cookieJar):
        """
        Save session cookiejar as addon data file (helper function).
        :param cookieJar:
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_COOKIEJAR)
        with open(fp, 'wb') as f:
            pickle.dump(cookieJar, f)

    def updateSearchHistory(self, q):
        """
        Update search history addon data file (helper function).
        :param q: search query (str)
        """
        sh = self.loadSearchHistory()
        sh['items'].append(
            {'q': q, 'timestamp': int(time.time())}
        )
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_SEARCH)
        with open(fp, 'w') as f:
            json.dump(sh, f)

    def searchSimilar(self):
        """
        Search similar videos (contextmenu action handler).
        """
        pass  # todo

    def searchVideos(self):
        """
        Search videos (action handler).
        """
        # if there is not a search query let the user enter a new one
        if 'q' not in self.urlArgs:
            self.urlArgs['q'] = xbmcgui.Dialog().input('ENTER SEARCH QUERY')
        # update search history json file
        self.updateSearchHistory(q=self.urlArgs['q'])
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for searched videos
        searchedVideos = self.vkApi.video.search(
            q=self.urlArgs['q'],
            extended='1',
            hd='1',
            adult=self.settings['searchAdult'],
            search_own=self.settings['searchOwn'],
            longer=str(int(self.settings['searchLonger']) * 60),
            shorter=str(int(self.settings['searchShorter']) * 60),
            sort=self.settings['searchSort'],
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        # todo: log request params
        # self.log('searchVideos(): searchedVideos:', searchedVideos)
        # notify user on search results
        if self.urlArgs['offset'] == 0:
            self.notify('{0} videos found.'.format(searchedVideos['count']))
        # build list of searched videos
        self.buildListOfVideos(listType='searchedvideos', listData=searchedVideos)  # todo: const. for listtypes?

    def unfollowCommunity(self):
        """
        Unfollow community (contextmenu action handler).
        """
        pass  # todo

    def unlikeCommunity(self):
        """
        Unlike community (contextmenu action handler).
        """
        pass  # todo

    def unlikeVideo(self):
        """
        Unlike video (contextmenu action handler).
        """
        oidid = '{0}_{1}'.format(self.urlArgs['ownerId'], self.urlArgs['id'])
        unlike = self.vkApi.likes.delete(
            type='video',
            owner_id=self.urlArgs['ownerId'],
            item_id=self.urlArgs['id'],
        )
        self.log('Like deleted: {0} ({1} likes)'.format(oidid, unlike['likes']))
        self.notify('Like deleted. ({0} likes)'.format(unlike['likes']))


if __name__ == '__main__':
    # run addon
    VkAddon()
