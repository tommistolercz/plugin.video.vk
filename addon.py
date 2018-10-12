# Define dunders
__all__ = []


# Import std lib modules
import datetime
import json
import os
import pickle
import re
import sys
import time
import urllib
import urlparse  # todo: python3: urllib.parse

# Import kodi modules
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

# Import addon modules
sys.path.append('/Users/tom/Library/Application Support/Kodi/addons/plugin.video.vk/resources/lib')  # todo: ugly!
sys.path.append('/Users/tom/Library/Application Support/Kodi/addons/plugin.video.vk/resources/lib/vk')  # todo: ugly!
import vk


# Define constants
VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_VERSION = '5.85'
VK_API_LANG = 'ru'
FILENAME_ADDON_DATA_COOKIES = 'cookies'
FILENAME_ADDON_DATA_SEARCHHISTORY = 'searchhistory.json'
ISFOLDER_TRUE = True
ISFOLDER_FALSE = False


# Define addon class
class MyAddon(object):

    # Initialize addon
    def __init__(self):  # todo: too complex
        self.addon = xbmcaddon.Addon()
        self.handle = int(sys.argv[1])
        # get addon settings
        self.settings = {
            'itemsPerPage': int(self.addon.getSetting('itemsPerPage')),
            'searchSortMethod': int(self.addon.getSetting('searchSortMethod')),
            'vkUserAccessToken': self.addon.getSetting('vkUserAccessToken'),
        }
        self.log('self.settings:', self.settings)
        # init vk session
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
        self.log('self.tracking:', self.tracking)
        # parse addon url
        self.urlBase = 'plugin://' + self.addon.getAddonInfo('id')
        self.urlPath = sys.argv[0].replace(self.urlBase, '')
        self.urlArgs = {}
        if sys.argv[2].startswith('?'):
            self.urlArgs = urlparse.parse_qs(sys.argv[2].lstrip('?'))
            for k, v in list(self.urlArgs.items()):
                self.urlArgs[k] = v.pop()
        self.log('self.urlBase:', self.urlBase)
        self.log('self.urlPath:', self.urlPath)
        self.log('self.urlArgs:', self.urlArgs)
        # dispatch addon routing by calling applicable action handler
        self.routing = {
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

    # Add video to album (contextmenu action handler)
    def addToAlbum(self):
        pass

    # Build addon url (helper function)
    def buildUrl(self, urlPath, urlArgs=None):
        url = self.urlBase + urlPath
        if urlArgs is not None:
            url += '?' + urllib.urlencode(urlArgs)
        return url

    # Build list of communities (helper function)
    def buildListOfCommunities(self, listType, listData):
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
                    ('LIKE VIDEO ALT', 'Container.Update({0})'.format(self.buildUrl('/likevideo', {'ownerId': video['owner_id'], 'id': video['id']}))),
                    ('UNLIKE VIDEO', 'RunPlugin({0})'.format(self.buildUrl('/unlikevideo', {'ownerId': video['owner_id'], 'id': video['id']}))),
                    ('UNLIKE VIDEO ALT', 'Container.Update({0})'.format(self.buildUrl('/unlikevideo', {'ownerId': video['owner_id'], 'id': video['id']}))),
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
        like = self.vkApi.likes.add(
            type='video',
            owner_id=self.urlArgs['ownerId'],
            item_id=self.urlArgs['id'],
        )
        self.log('likeVideo(): like:', like)
        self.notify('Like added. ({0} likes total)'.format(like['likes']))

    # List user's albums (action handler)
    def listAlbums(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for albums
        albums = self.vkApi.video.getAlbums(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        self.log('listAlbums(): albums:', albums)
        # create list items for albums
        listItems = []
        for album in albums['items']:
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

    # List user's album videos (action handler)
    def listAlbumVideos(self):
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
        self.log('listAlbumVideos(): albumVideos:', albumVideos)
        # build list of album videos
        self.buildListOfVideos(listType='albumvideos', listData=albumVideos)

    # List user's communities (action handler)
    def listCommunities(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for communities
        communities = self.vkApi.groups.get(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        self.log('listCommunities(): communities:', communities)
        # build list of communities
        self.buildListOfCommunities(listType='communities', listData=communities)  # todo: listType=communities default?

    # List user's community videos (action handler)
    def listCommunityVideos(self):
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
        self.log('listCommunityVideos(): communityVideos:', communityVideos)
        # build list of community videos
        self.buildListOfVideos(listType='communityvideos', listData=communityVideos)

    # List user's liked communities (action handler)
    def listLikedCommunities(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for liked communities
        likedCommunities = self.vkApi.fave.getLinks(
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        self.log('listLikedCommunities(): likedCommunities:', likedCommunities)
        # build list of liked communities
        self.buildListOfCommunities(listType='likedcommunities', listData=likedCommunities)

    # List user's liked videos (action handler)
    def listLikedVideos(self):
        # set default paging offset
        if 'offset' not in self.urlArgs:
            self.urlArgs['offset'] = 0
        # request vk api for liked videos
        likedVideos = self.vkApi.fave.getVideos(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        self.log('listLikedVideos(): likedVideos:', likedVideos)
        # build list of liked videos
        self.buildListOfVideos('likedvideos', likedVideos)

    # List main menu (action handler)
    def listMainMenu(self):
        # request vk api for menu counters (by executing a stored function)
        try:
            counters = self.vkApi.execute.getMenuCounters()
        except vk.exceptions.VkAPIError:
            counters = {'videos': 'n/a', 'albums': 'n/a', 'communities': 'n/a', 'likedVideos': 'n/a', 'likedCommunities': 'n/a'}
        self.log('listMainMenu(): counters:', counters)
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
        # load search history
        searchHistory = self.loadSearchHistory()
        self.log('listSearchHistory(): searchHistory:', searchHistory)
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
        videos = self.vkApi.video.get(
            extended=1,
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        self.log('listVideos(): videos:', videos)
        # build list of videos
        self.buildListOfVideos(listType='videos', listData=videos)

    # load session cookies from addon data file (helper function)
    def loadCookies(self):
        cookieJar = {}
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), FILENAME_ADDON_DATA_COOKIES)
        if os.path.exists(fp):  # todo: else raise exception
            with open(fp, 'rb') as f:
                cookieJar = pickle.load(f)
        return cookieJar

    # load search history from addon data file (helper function)
    def loadSearchHistory(self):
        sh = {'items': []}
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), FILENAME_ADDON_DATA_SEARCHHISTORY)
        if os.path.exists(fp):
            with open(fp) as f:
                sh = json.load(f)
        return sh

    # Log into Kodi.log using uniform formatting (helper function)
    def log(self, label, value, level=xbmc.LOGDEBUG):
        msg = '{0}: {1} {2}'.format(self.addon.getAddonInfo('id'), label, value)
        xbmc.log(msg, level)

    # Notify user using uniform notif. style (helper function)
    def notify(self, message, icon=xbmcgui.NOTIFICATION_INFO):
        heading = self.addon.getAddonInfo('id')
        xbmcgui.Dialog().notification(heading, message, icon)

    # Play album (contextmenu action handler)
    def playAlbum(self):
        pass

    # Play video (action handler)
    def playVideo(self):
        oidid = '{0}_{1}'.format(self.urlArgs['ownerId'], self.urlArgs['id'])
        # request vk api for video
        video = self.vkApi.video.get(videos=oidid)['items'].pop()
        self.log('playVideo(): video:', video)
        # hack: resolve playable stream/s using vk url api
        resolver = self.vkSession.requests_session.post(
            url='https://vk.com/al_video.php',
            params={
                'act': 'show_inline',
                'al': '1',
                'video': oidid,
            },
            # cookies: logged user's cookies sent autom. (set/restored within vk session init)
            # headers: todo: user-agent?
        )
        self.log('playvideo(): resolver.url:', resolver.url)
        html = resolver.text.replace('\\', '')
        self.log('playVideo(): html:', html)
        matches = re.findall(r'<source src="([^"]+\.(\d+)\.[^"]+)" type="video/mp4" />', html)  # todo: better? 1080?
        playableStreams = {}
        for m in matches:
            stream = m[0]
            quality = str(m[1])
            playableStreams[quality] = stream
        self.log('playVideo(): playableStreams:', playableStreams)
        # create item for kodi player (using max avail. quality)
        if playableStreams:
            xbmcplugin.setContent(self.handle, 'videos')  # todo: required here?
            qualityMax = max(playableStreams.keys())
            li = xbmcgui.ListItem(path=playableStreams[qualityMax])  # todo: infolabels?
            xbmcplugin.setResolvedUrl(self.handle, True, li)
        # or notify user when no luck
        else:
            self.notify('Video cannot be played.', icon=xbmcgui.NOTIFICATION_WARNING)
            self.log('playVideo(): Video cannot be played:', oidid, level=xbmc.LOGWARNING)

    # Remove video from album (contextmenu action handler)
    def removeFromAlbum(self):
        pass

    # Rename album (contextmenu action handler)
    def renameAlbum(self):
        pass

    # Reorder album (contextmenu action handler)
    def reorderAlbum(self):
        pass

    # save session cookies into addon data file (helper function)
    def saveCookies(self, cookieJar):
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), FILENAME_ADDON_DATA_COOKIES)
        with open(fp, 'wb') as f:
            pickle.dump(cookieJar, f)

    # update search history addon data file (helper function)
    def updateSearchHistory(self, q):
        sh = self.loadSearchHistory()
        sh['items'].append(
            {'q': q, 'timestamp': int(time.time())}
        )
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), FILENAME_ADDON_DATA_SEARCHHISTORY)
        with open(fp, 'w') as f:
            json.dump(sh, f)

    # Search similar videos (contextmenu action handler)
    def searchSimilar(self):
        pass

    # Search videos (action handler)
    def searchVideos(self):
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
            extended=1,
            hd=1,
            adult=1,
            search_own=0,  # todo: as user setting, default=1 ?
            longer=600,  # todo: as user setting, default=600 (10min)
            shorter=3600,  # todo: as user setting, default=3600 (60min)
            sort=self.settings['searchSortMethod'],
            q=self.urlArgs['q'],
            offset=self.urlArgs['offset'],
            count=self.settings['itemsPerPage'],
        )
        self.log('searchVideos(): searchedVideos:', searchedVideos)
        # notify user on search results
        if self.urlArgs['offset'] == 0:
            self.notify('{0} videos found.'.format(searchedVideos['count']))
        # build list of searched videos
        self.buildListOfVideos(listType='searchedvideos', listData=searchedVideos)  # todo: const. for listtypes?

    # Unfollow community (contextmenu action handler)
    def unfollowCommunity(self):
        pass

    # Unlike community (contextmenu action handler)
    def unlikeCommunity(self):
        pass

    # Unlike video (contextmenu action handler)
    def unlikeVideo(self):
        unlike = self.vkApi.likes.delete(
            type='video',
            owner_id=self.urlArgs['ownerId'],
            item_id=self.urlArgs['id'],
        )
        self.log('unlikeVideo(): unlike:', unlike)
        self.notify('Like deleted. ({0} likes total)'.format(unlike['likes']))


# Run addon
if __name__ == '__main__':
    MyAddon()
