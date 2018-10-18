__all__ = ['VKAddon', 'VKAddonError']


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

sys.path.append(os.path.join(xbmc.translatePath(xbmcaddon.Addon().getAddonInfo('path')), 'resources', 'lib'))
import vk


VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_VERSION = '5.85'
VK_API_LANG = 'ru'
VK_VIDEOINFO_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246'
ADDON_DATA_FILE_COOKIEJAR = '.cookiejar'
ADDON_DATA_FILE_SEARCH = 'search.json'

ISFOLDER_TRUE = True
ISFOLDER_FALSE = False


class VKAddon():
    """
    Main addon class encapsulating all logic and data.
    """
    def __init__(self):
        """
        Initialize addon.
        """
        # todo: too complex
        self.addon = xbmcaddon.Addon()
        self.handle = int(sys.argv[1])
        # init vk session
        if self.addon.getSetting('vkuseraccesstoken') == '':
            credentials = {
                'login': xbmcgui.Dialog().input('ENTER VK USER LOGIN (EMAIL)'),
                'password': xbmcgui.Dialog().input('ENTER VK USER PASSWORD', option=xbmcgui.ALPHANUM_HIDE_INPUT),
            }
            self.vksession = vk.AuthSession(VK_API_APP_ID, credentials['login'], credentials['password'], VK_API_SCOPE)
            credentials = None  # no longer used
            self.addon.setSetting('vkuseraccesstoken', self.vksession.access_token)
            self.savecookies(self.vksession.auth_session.cookies)
        else:
            self.vksession = vk.Session(self.addon.getSetting('vkuseraccesstoken'))
            self.vksession.requests_session.cookies = self.loadcookies()
        # create vk api object
        self.vkapi = vk.API(self.vksession, v=VK_API_VERSION, lang=VK_API_LANG)
        # request vk api for tracking the addon usage
        self.tracking = bool(self.vkapi.stats.trackVisitor())
        self.log('vk api usage tracked: {0}'.format(self.tracking))
        # parse addon url
        self.urlbase = 'plugin://' + self.addon.getAddonInfo('id')
        self.urlpath = sys.argv[0].replace(self.urlbase, '')
        self.urlargs = {}
        if sys.argv[2].startswith('?'):
            self.urlargs = urlparse.parse_qs(sys.argv[2].lstrip('?'))
            for k, v in list(self.urlargs.items()):
                self.urlargs[k] = v.pop()
        self.log('addon url parsed: {0}{1} urlargs: {2}'.format(self.urlbase, self.urlpath, self.urlargs))
        # dispatch addon routing by calling handler for respective user action
        self.routing = {  # todo: pass urlargs as **kwargs, add hierarchy into urlpath i.e. '/videos/albums'
            # menu actions/handlers:
            '/': self.listmainmenu,
            '/albums': self.listalbums,
            '/albumvideos': self.listalbumvideos,
            '/communities': self.listcommunities,
            '/communityvideos': self.listcommunityvideos,
            '/likedcommunities': self.listlikedcommunities,
            '/likedvideos': self.listlikedvideos,
            '/play': self.playvideo,
            '/search': self.searchvideos,
            '/searchhistory': self.listsearchhistory,
            '/stats': self.liststats,
            '/videos': self.listvideos,
            # contextmenu actions/handlers:
            '/addtoalbum': self.addtoalbum,
            '/createalbum': self.createalbum,
            '/deletealbum': self.deletealbum,
            '/deletequery': self.deletequery,
            '/editquery': self.editquery,
            '/likecommunity': self.likecommunity,
            '/likevideo': self.likevideo,
            '/playalbum': self.playalbum,
            '/removefromalbum': self.removefromalbum,
            '/renamealbum': self.renamealbum,
            '/reorderalbum': self.reorderalbum,
            '/searchsimilar': self.searchsimilarvideos,
            '/unfollowcommunity': self.unfollowcommunity,
            '/unlikecommunity': self.unlikecommunity,
            '/unlikevideo': self.unlikevideo,
        }
        if self.urlpath in self.routing:
            self.routing[self.urlpath]()

    def buildoidid(self, ownerid, id):
        """
        Build a full video identifier, aka oidid.
        (helper)
        :param ownerid: str
        :param id: str
        :returns: str
        """
        return '{0}_{1}'.format(ownerid, id)

    def buildurl(self, urlpath, urlargs=None):
        """
        Build addon url.
        (helper)
        :param urlpath: str
        :param urlargs: dict
        :returns: str
        """
        url = self.urlbase + urlpath
        if urlargs is not None:
            url += '?' + urllib.urlencode(urlargs)
        return url

    def buildlistofcommunities(self, listtype, listdata):
        """
        Build list of communities.
        (helper)
        :param listtype: str
        :param listdata:
        """
        # todo: as class?, listtype=>subtype = ['likedcommunities']
        # create list items for communities
        listitems = []
        _namekey = 'title' if listtype == 'likedcommunities' else 'name'  # ugly!
        for community in listdata['items']:
            if listtype == 'likedcommunities':
                community['id'] = community['id'].split('_')[2]  # ugly!
            li = xbmcgui.ListItem(
                label=community[_namekey],
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
            listitems.append(
                (self.buildurl('/communityvideos', {'ownerid': '-{0}'.format(community['id'])}), li, ISFOLDER_TRUE)  # negative id required when owner is a community
            )
        # add paginator item  # todo: make this a function
        if int(listdata['count']) > int(self.addon.getSetting('itemsperpage')):
            if int(listdata['count']) > int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')):
                self.urlargs['offset'] = int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage'))
                listitems.append(
                    (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), ISFOLDER_TRUE)
                )
        # show community list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def buildlistofvideos(self, listtype, listdata):
        """
        Build list of videos.
        (helper)
        :param listtype:
        :param listdata:
        """
        # todo: as class?
        # listtypes = ['videos', 'searchedvideos', 'albumvideos', 'communityvideos', 'likedvideos']  # todo: stop ignor.
        # create list items for videos
        listitems = []
        for video in listdata['items']:
            li = xbmcgui.ListItem(label=video['title'])
            li.setProperty('IsPlayable', 'true')
            li.setInfo(
                type='video',
                infoLabels={
                    'title': video['title'],  # todo: needed here vs move to playvideo()?
                    'plot': video['description'],
                    'duration': video['duration'],
                    'date': datetime.datetime.fromtimestamp(video['date']).strftime('%d.%m.%Y'),
                    # 'playcount': video['views'],  # todo
                }
            )
            if 'photo_800' in video:  # todo: ugly!
                maxthumb = video['photo_800']
            elif 'photo_640' in video:
                maxthumb = video['photo_640']
            else:
                maxthumb = video['photo_320']
            li.setArt({'thumb': maxthumb})
            li.addContextMenuItems(
                [
                    ('LIKE VIDEO', 'RunPlugin({0})'.format(self.buildurl('/likevideo', {'ownerid': video['owner_id'], 'id': video['id']}))),
                    # ('LIKE VIDEO ALT', 'Container.Update({0})'.format(self.buildurl('/likevideo', {'ownerid': video['owner_id'], 'id': video['id']}))),
                    ('UNLIKE VIDEO', 'RunPlugin({0})'.format(self.buildurl('/unlikevideo', {'ownerid': video['owner_id'], 'id': video['id']}))),
                    # ('UNLIKE VIDEO ALT', 'Container.Update({0})'.format(self.buildurl('/unlikevideo', {'ownerid': video['owner_id'], 'id': video['id']}))),
                    # ('ADD TO ALBUM', ''),  # todo
                    # ('SEARCH SIMILAR VIDEOS', ''),  # todo
                ]
            )
            listitems.append(
                (self.buildurl('/play', {'ownerid': video['owner_id'], 'id': video['id']}), li, ISFOLDER_FALSE)
            )
        # add paginator item
        if int(listdata['count']) > int(self.addon.getSetting('itemsperpage')):
            if int(listdata['count']) > int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')):
                self.urlargs['offset'] = int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage'))
                listitems.append(
                    (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), ISFOLDER_TRUE)
                )
        # show video list in kodi, even if empty
        xbmc.executebuiltin('Container.SetViewMode(500)')
        xbmcplugin.setContent(self.handle, 'videos')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def loadcookies(self):
        """
        load session cookies from addon data file.
        (helper)
        :returns: obj
        """
        cookiejar = {}
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_COOKIEJAR)
        if os.path.exists(fp):  # todo: else raise exception
            with open(fp, 'rb') as f:
                cookiejar = pickle.load(f)
        return cookiejar

    def loadsearchhistory(self):
        """
        Load search history from addon data file.
        (helper)
        """
        searchhistory = {'items': []}
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_SEARCH)
        if os.path.exists(fp):
            with open(fp) as f:
                searchhistory = json.load(f)
        return searchhistory

    def log(self, msg, level=xbmc.LOGDEBUG):
        """
        Log message into default Kodi.log using an uniform style.
        (helper)
        :param msg: str
        :param level: xbmc.LOGDEBUG (default)
        """
        msg = '{0}: {1}'.format(self.addon.getAddonInfo('id'), msg)
        xbmc.log(msg, level)

    def notify(self, msg, icon=xbmcgui.NOTIFICATION_INFO):
        """
        Notify user using uniform style.
        (helper)
        :param msg: str
        :param icon: xbmcgui.NOTIFICATION_INFO (default)
        """
        heading = self.addon.getAddonInfo('id')
        xbmcgui.Dialog().notification(heading, msg, icon)

    def savecookies(self, cookiejar):
        """
        Save session cookiejar object as addon data file.
        (helper)
        :param cookiejar: obj
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_COOKIEJAR)
        with open(fp, 'wb') as f:
            pickle.dump(cookiejar, f)

    def updatesearchhistory(self, q):
        """
        Update search history addon data file.
        (helper)
        :param q: str
        """
        # todo: ts->dt
        # todo: When updating, save results count for q as well
        searchhistory = self.loadsearchhistory()
        searchhistory['items'].append(
            {'q': q, 'timestamp': int(time.time())}
        )
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_SEARCH)
        with open(fp, 'w') as f:
            json.dump(searchhistory, f)

    """ ----- Menu action handlers ----- """

    def listalbums(self):
        """
        List user's albums.
        (menu action handler)
        """
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for albums
        albums = self.vkapi.video.getAlbums(
            extended='1',
            offset=self.urlargs['offset'],
            count=self.addon.getSetting('itemsperpage'),
        )
        # create list items for albums
        listitems = []
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
            listitems.append(
                (self.buildurl('/albumvideos', {'albumid': album['id']}), li, ISFOLDER_TRUE)
            )
        # add paginator item  # todo: def func
        if int(albums['count']) > int(self.addon.getSetting('itemsperpage')):
            if int(albums['count']) > int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')):
                self.urlargs['offset'] = int(self.urlargs['offset']) + self.addon.getSetting('itemsperpage')
                listitems.append(
                    (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), ISFOLDER_TRUE)
                )
        # show album list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def listalbumvideos(self):
        """
        List user's album videos.
        (menu action handler)
        """
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for album videos
        albumvideos = self.vkapi.video.get(
            extended='1',
            album_id=self.urlargs['albumid'],
            offset=self.urlargs['offset'],
            count=self.addon.getSetting('itemsperpage'),
        )
        # build list of album videos
        self.buildlistofvideos(listtype='albumvideos', listdata=albumvideos)

    def listcommunities(self):
        """
        List user's communities.
        (menu action handler)
        """
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for communities
        communities = self.vkapi.groups.get(
            extended='1',
            offset=self.urlargs['offset'],
            count=self.addon.getSetting('itemsperpage'),
        )
        # build list of communities
        self.buildlistofcommunities(listtype='communities', listdata=communities)  # todo: listtype=communities default?

    def listcommunityvideos(self):
        """
        List user's community videos.
        (menu action handler)
        """
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for community videos
        communityvideos = self.vkapi.video.get(
            extended='1',
            owner_id=self.urlargs['ownerid'],
            offset=self.urlargs['offset'],
            count=self.addon.getSetting('itemsperpage'),
        )
        # build list of community videos
        self.buildlistofvideos(listtype='communityvideos', listdata=communityvideos)

    def listlikedcommunities(self):
        """
        List user's liked communities.
        (menu action handler)
        """
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for liked communities
        likedcommunities = self.vkapi.fave.getLinks(
            offset=self.urlargs['offset'],
            count=self.addon.getSetting('itemsperpage'),
        )
        # build list of liked communities
        self.buildlistofcommunities(listtype='likedcommunities', listdata=likedcommunities)

    def listlikedvideos(self):
        """
        List user's liked videos.
        (menu action handler)
        """
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for liked videos
        likedvideos = self.vkapi.fave.getVideos(
            extended='1',
            offset=self.urlargs['offset'],
            count=self.addon.getSetting('itemsperpage'),
        )
        # build list of liked videos
        self.buildlistofvideos('likedvideos', likedvideos)

    def listmainmenu(self):
        """
        List main menu.
        (menu action handler)
        """
        # request vk api for menu counters (by executing a stored function)
        try:
            counters = self.vkapi.execute.getMenuCounters()
        except vk.exceptions.VkAPIError:
            counters = {'videos': 'n/a', 'albums': 'n/a', 'communities': 'n/a', 'likedVideos': 'n/a', 'likedCommunities': 'n/a'}  # todo: better? do not display at all?
        # create list items for main menu
        listitems = [
            (self.buildurl('/search'), xbmcgui.ListItem('SEARCH'), ISFOLDER_TRUE),
            (self.buildurl('/searchhistory'), xbmcgui.ListItem('SEARCH HISTORY'), ISFOLDER_TRUE),
            (self.buildurl('/videos'), xbmcgui.ListItem('VIDEOS [COLOR blue]({0})[/COLOR]'.format(counters['videos'])), ISFOLDER_TRUE),
            (self.buildurl('/albums'), xbmcgui.ListItem('ALBUMS [COLOR blue]({0})[/COLOR]'.format(counters['albums'])), ISFOLDER_TRUE),
            (self.buildurl('/communities'), xbmcgui.ListItem('COMMUNITIES [COLOR blue]({0})[/COLOR]'.format(counters['communities'])), ISFOLDER_TRUE),
            (self.buildurl('/likedvideos'), xbmcgui.ListItem('LIKED VIDEOS [COLOR blue]({0})[/COLOR]'.format(counters['likedVideos'])), ISFOLDER_TRUE),
            (self.buildurl('/likedcommunities'), xbmcgui.ListItem('LIKED COMMUNITIES [COLOR blue]({0})[/COLOR]'.format(counters['likedCommunities'])), ISFOLDER_TRUE),
            (self.buildurl('/stats'), xbmcgui.ListItem('STATS'), ISFOLDER_TRUE),
        ]
        # show main menu list in kodi
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def listsearchhistory(self):
        """
        List search history.
        (menu action handler)
        """
        # load search history
        searchhistory = self.loadsearchhistory()
        # create list items for search history sorted by timestamp reversed
        listitems = []
        for search in sorted(searchhistory['items'], key=lambda x: x['timestamp'], reverse=True):
            li = xbmcgui.ListItem(
                label=search['q'],
                label2=datetime.datetime.fromtimestamp(search['timestamp']).strftime('%d.%m.%Y'),  # todo: ts->dt
            )
            li.addContextMenuItems(
                [
                    ('EDIT QUERY', ''),  # todo
                    ('DELETE QUERY', ''),  # todo
                ]
            )
            listitems.append(
                (self.buildurl('/search', {'q': search['q']}), li, ISFOLDER_TRUE)
            )
        # show search history list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def liststats(self):
        """
        List stats.
        (menu action handler)
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

    def listvideos(self):
        """
        List user's videos.
        (menu action handler)
        """
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for videos
        videos = self.vkapi.video.get(
            extended='1',
            offset=self.urlargs['offset'],
            count=self.addon.getSetting('itemsperpage'),
        )
        # build list of videos
        self.buildlistofvideos(listtype='videos', listdata=videos)

    def playvideo(self):
        """
        Play video.
        (menu action handler)
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        self.log('Playing video: {0}'.format(oidid))
        # resolve playable streams via vk videoinfo api (hack)
        try:
            vi = self.vksession.requests_session.get(
                url='https://vk.com/al_video.php?act=show_inline&al=1&video={0}'.format(oidid),
                headers={'User-Agent': VK_VIDEOINFO_UA},
                # logged user's cookies sent autom. (set/restored within vksession init)
            )
            self.log('Resolving video url: {0}'.format(vi.url))
            matches = re.findall(r'"url(\d+)":"([^"]+)"', vi.text.replace('\\', ''))
            playables = {}
            for m in matches:
                qual = int(m[0])
                playables[qual] = m[1]
            self.log('Resolving ok, playable stream/s found: {0}'.format(playables))
            if not playables:
                raise VKAddonError
        except VKAddonError:
            self.log('Resolving failed, playable stream/s not found.', level=xbmc.LOGERROR)
            self.notify('Resolving failed, playable stream/s not found.', icon=xbmcgui.NOTIFICATION_ERROR)
            return
        # create item for kodi player (using max avail. quality)
        xbmcplugin.setContent(self.handle, 'videos')
        maxqual = max(playables.keys())
        li = xbmcgui.ListItem(path=playables[maxqual])
        xbmcplugin.setResolvedUrl(self.handle, True, li)

    def searchvideos(self):
        """
        Search videos.
        (menu action handler)
        """
        # if there is not a search query let the user enter a new one
        if 'q' not in self.urlargs:
            self.urlargs['q'] = xbmcgui.Dialog().input('ENTER SEARCH QUERY')
        # update search history json file
        self.updatesearchhistory(q=self.urlargs['q'])
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for searched videos
        searchedvideos = self.vkapi.video.search(
            q=self.urlargs['q'],
            extended='1',
            hd='1',
            adult='1' if self.addon.getSetting('searchadult') == 'true' else '0',  # case sens.
            search_own='1' if self.addon.getSetting('searchown') == 'true' else '0',  # case sens.
            longer=str(int(self.addon.getSetting('searchlonger')) * 60),  # todo: ignored?
            shorter=str(int(self.addon.getSetting('searchshorter')) * 60),  # todo: ignored?
            sort=self.addon.getSetting('searchsort'),
            offset=self.urlargs['offset'],
            count=self.addon.getSetting('itemsperpage'),
        )
        # notify user on results count
        if self.urlargs['offset'] == 0:
            self.notify('{0} videos found.'.format(searchedvideos['count']))
        # build list of searched videos
        self.buildlistofvideos(listtype='searchedvideos', listdata=searchedvideos)  # todo: reverse params, listtype const.?

    """ ----- Contextmenu action handlers ----- """

    def addtoalbum(self):
        """
        Add video into album.
        (contextmenu action handler)
        """
        pass  # todo

    def createalbum(self):
        """
        Create a new album of videos.
        (contextmenu action handler)
        """
        pass  # todo

    def deletealbum(self):
        """
        Delete album.
        (contextmenu action handler)
        """
        pass  # todo

    def deletequery(self):
        """
        Delete query from search history.
        (contextmenu action handler)
        """
        pass

    def editquery(self):
        """
        Edit query in search history.
        (contextmenu action handler)
        """
        pass  # todo

    def likecommunity(self):
        """
        Like community.
        (contextmenu action handler)
        """
        pass

    def likevideo(self):
        """
        Like video.
        (contextmenu action handler)
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        like = self.vkapi.likes.add(
            type='video',
            owner_id=self.urlargs['ownerid'],
            item_id=self.urlargs['id'],
        )
        self.log('Like added to video: {0} ({1} likes)'.format(oidid, like['likes']))
        self.notify('Like added to video. ({0} likes)'.format(like['likes']))

    def playalbum(self):
        """
        Play album.
        (contextmenu action handler)
        """
        pass  # todo

    def removefromalbum(self):
        """
        Remove video from album.
        (contextmenu action handler)
        """
        pass  # todo

    def renamealbum(self):
        """
        Rename album.
        (contextmenu action handler)
        """
        pass  # todo

    def reorderalbum(self):
        """
        Reorder album.
        (contextmenu action handler)
        """
        pass  # todo

    def searchsimilarvideos(self):
        """
        Search similar videos.
        (contextmenu action handler)
        """
        pass  # todo

    def unfollowcommunity(self):
        """
        Unfollow community.
        (contextmenu action handler)
        """
        pass  # todo

    def unlikecommunity(self):
        """
        Unlike community.
        (contextmenu action handler)
        """
        pass  # todo

    def unlikevideo(self):
        """
        Unlike video.
        (contextmenu action handler)
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        unlike = self.vkapi.likes.delete(
            type='video',
            owner_id=self.urlargs['ownerid'],
            item_id=self.urlargs['id'],
        )
        self.log('Like deleted from video: {0} ({1} likes)'.format(oidid, unlike['likes']))
        self.notify('Like deleted from video. ({0} likes)'.format(unlike['likes']))


class VKAddonError(Exception):
    """
    todo
    """
    def __init__():
        """
        todo
        """
        pass  # todo


if __name__ == '__main__':
    VKAddon()  # run
