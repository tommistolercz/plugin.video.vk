__all__ = ['VKAddon', 'VKAddonError']


import datetime
import json
import os
import pickle
import re
import sys
import time
import urllib
try:
    import urlparse  # py2
except ImportError:
    import urllib.parse as urlparse  # py3

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

sys.path.append(os.path.join(xbmc.translatePath(xbmcaddon.Addon().getAddonInfo('path')), 'resources', 'lib'))
import vk  # noqa: E402


PY2, PY3 = ((sys.version_info[0] == 2), (sys.version_info[0] == 3))
FOLDER, NOT_FOLDER = (True, False)

VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_VERSION = '5.85'  # todo 5.87
VK_API_LANG = 'ru'
VK_VIDEOINFO_UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/42.0.2311.135 Safari/537.36 Edge/12.246'
ADDON_DATA_FILE_COOKIEJAR = '.cookiejar'
ADDON_DATA_FILE_SEARCH = 'search.json'


class VKAddon():
    """
    Addon class encapsulating all its logic and data.
    """
    def __init__(self):
        """
        Initialize everything and manage all that controlling stuff during runtime ;-)
        """
        self.addon = xbmcaddon.Addon()
        self.handle = int(sys.argv[1])
        # create vk session
        try:
            # first run: authorise addon by entering user credentials and obtain new user access token
            if self.addon.getSetting('vkuseraccesstoken') == '':
                self.vksession = vk.AuthSession(
                    VK_API_APP_ID,
                    xbmcgui.Dialog().input('ENTER VK USER LOGIN (EMAIL)'),
                    xbmcgui.Dialog().input('ENTER VK USER PASSWORD', option=xbmcgui.ALPHANUM_HIDE_INPUT),
                    VK_API_SCOPE
                )
                self.addon.setSetting('vkuseraccesstoken', self.vksession.access_token)
                self.savecookies(self.vksession.auth_session.cookies)
            # restore session by sending user access token
            else:
                self.vksession = vk.Session(self.addon.getSetting('vkuseraccesstoken'))
                self.vksession.requests_session.cookies = self.loadcookies()
        except vk.exceptions.VkAuthError:
            self.log('VK authorization error!', level=xbmc.LOGERROR)
            self.notify('VK authorization error!', icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # create vk api, enable api usage tracking
        try:
            self.vkapi = vk.API(self.vksession, v=VK_API_VERSION, lang=VK_API_LANG)
            tracking = bool(self.vkapi.stats.trackVisitor())
            self.log('VK API object created. API usage tracking: {0}'.format(tracking))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify('VK API error!', icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # parse addon url
        self.urlbase = 'plugin://' + self.addon.getAddonInfo('id')
        self.urlpath = sys.argv[0].replace(self.urlbase, '')
        self.urlargs = {}
        if sys.argv[2].startswith('?'):
            self.urlargs = urlparse.parse_qs(sys.argv[2].lstrip('?'))
            for k, v in list(self.urlargs.items()):
                self.urlargs[k] = v.pop()
        self.log('Addon URL parsed: {0}'.format(self.buildurl(self.urlpath, self.urlargs)))
        # dispatch addon routing by calling a handler for respective user action
        # todo: pass urlargs as **kwargs
        # todo: add hierarchy into urlpath i.e. '/videos/albums'
        self.routing = {
            # menu actions:
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
            # contextmenu actions:
            '/addalbum': self.addalbum,
            '/addtoalbum': self.addtoalbum,
            '/deletealbum': self.deletealbum,
            '/deletesearch': self.deletesearch,
            '/editsearch': self.editsearch,
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
                (self.buildurl('/communityvideos', {'ownerid': '-{0}'.format(community['id'])}), li, FOLDER)  # negative id required when owner is a community
            )
        # add paginator item  # todo: make this a function
        if int(listdata['count']) > int(self.addon.getSetting('itemsperpage')):
            if int(listdata['count']) > int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')):
                self.urlargs['offset'] = int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage'))
                listitems.append(
                    (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), FOLDER)
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
                    # if not video['likes']['user_likes']:    
                    ('[COLOR blue]Like video[/COLOR]', 'RunPlugin({0})'.format(self.buildurl('/likevideo', {'ownerid': video['owner_id'], 'id': video['id']}))),
                    # if video['likes']['user_likes']:    
                    ('[COLOR blue]Unlike video[/COLOR]', 'RunPlugin({0})'.format(self.buildurl('/unlikevideo', {'ownerid': video['owner_id'], 'id': video['id']}))),
                    # ('ADD TO ALBUM', ''),  # todo
                    # ('SEARCH SIMILAR VIDEOS', ''),  # todo
                ]
            )
            listitems.append(
                (self.buildurl('/play', {'ownerid': video['owner_id'], 'id': video['id']}), li, NOT_FOLDER)
            )
        # add paginator item
        if int(listdata['count']) > int(self.addon.getSetting('itemsperpage')):
            if int(listdata['count']) > int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')):
                self.urlargs['offset'] = int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage'))
                listitems.append(
                    (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), FOLDER)
                )
        # show video list in kodi, even if empty
        xbmc.executebuiltin('Container.SetViewMode(500)')
        xbmcplugin.setContent(self.handle, 'videos')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def loadcookies(self):
        """
        load cookiejar object from addon data file.
        (helper)
        :returns: obj
        """
        cookiejar = {}
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_COOKIEJAR)
        with open(fp, 'rb') as f:
            cookiejar = pickle.load(f)
        return cookiejar

    def loadsearchhistory(self):
        """
        load search history data from addon data file.
        (helper)
        :returns: dict
        """
        searchhistory = {}
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_SEARCH)
        with open(fp) as f:
            searchhistory = json.load(f)
        if 'items' not in searchhistory:
            searchhistory['items'] = []
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
        heading = '{0}'.format(self.addon.getAddonInfo('name'))
        xbmcgui.Dialog().notification(heading, msg, icon)

    def savecookies(self, cookiejar):
        """
        Save cookiejar object into addon data file.
        (helper)
        :param cookiejar: obj
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_COOKIEJAR)
        with open(fp, 'wb') as f:
            pickle.dump(cookiejar, f)

    def savesearchhistory(self, searchhistory):
        """
        Save search history data into addon data file.
        (helper)
        :param searchhistory: dict
        """
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
            extended=1,
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
        )
        # create list items for albums
        listitems = []
        for i, album in enumerate(albums['items']):
            li = xbmcgui.ListItem(
                label='{0} [COLOR blue]({1})[/COLOR]'.format(album['title'], album['count']),
            )
            if album['count'] > 0:
                li.setArt({'thumb': album['photo_320']})
            # before/after album ids for reordering
            beforeid = albums['items'][i - 1]['id'] if i > 0 else None
            afterid = albums['items'][i + 1]['id'] if i < len(albums['items']) - 1 else None
            li.addContextMenuItems(
                [
                    # ('PLAY ALBUM', ''),  # todo
                    ('[COLOR blue]Rename album[/COLOR]', 'RunPlugin({0})'.format(self.buildurl('/renamealbum', {'albumid': album['id']}))),
                    ('[COLOR blue]Reorder album up[/COLOR]', 'RunPlugin({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'beforeid': beforeid}))),
                    ('[COLOR blue]Reorder album down[/COLOR]', 'RunPlugin({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'afterid': afterid}))),
                    ('[COLOR blue]Delete album[/COLOR]', 'RunPlugin({0})'.format(self.buildurl('/deletealbum', {'albumid': album['id']}))),
                    ('[COLOR blue]Add album[/COLOR]', 'RunPlugin({0})'.format(self.buildurl('/addalbum'))),
                ]
            )
            listitems.append(
                (self.buildurl('/albumvideos', {'albumid': album['id']}), li, FOLDER)
            )
        # add paginator item  # todo: def func
        if int(albums['count']) > int(self.addon.getSetting('itemsperpage')):
            if int(albums['count']) > int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')):
                self.urlargs['offset'] = int(self.urlargs['offset']) + self.addon.getSetting('itemsperpage')
                listitems.append(
                    (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR blue]NEXT PAGE[/COLOR]'), FOLDER)
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
            extended=1,
            album_id=int(self.urlargs['albumid']),
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
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
            extended=1,
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
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
            extended=1,
            owner_id=int(self.urlargs['ownerid']),
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
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
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
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
            extended=1,
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
        )
        # build list of liked videos
        self.buildlistofvideos('likedvideos', likedvideos)

    def listmainmenu(self):
        """
        List main menu.
        (menu action handler)
        """
        # request vk api for menu counters (stored function)
        try:
            counters = self.vkapi.execute.getMenuCounters()
        except vk.exceptions.VkAPIError:
            counters = {'videos': 'n/a', 'albums': 'n/a', 'communities': 'n/a', 'likedVideos': 'n/a', 'likedCommunities': 'n/a'}
            # todo: do not display counters at all?
        # create list items for main menu
        listitems = [
            (self.buildurl('/search'), xbmcgui.ListItem('SEARCH'), FOLDER),
            (self.buildurl('/searchhistory'), xbmcgui.ListItem('SEARCH HISTORY'), FOLDER),
            (self.buildurl('/videos'), xbmcgui.ListItem('VIDEOS [COLOR blue]({0})[/COLOR]'.format(counters['videos'])), FOLDER),
            (self.buildurl('/likedvideos'), xbmcgui.ListItem('LIKED VIDEOS [COLOR blue]({0})[/COLOR]'.format(counters['likedVideos'])), FOLDER),
            (self.buildurl('/albums'), xbmcgui.ListItem('ALBUMS [COLOR blue]({0})[/COLOR]'.format(counters['albums'])), FOLDER),
            (self.buildurl('/communities'), xbmcgui.ListItem('COMMUNITIES [COLOR blue]({0})[/COLOR]'.format(counters['communities'])), FOLDER),
            (self.buildurl('/likedcommunities'), xbmcgui.ListItem('LIKED COMMUNITIES [COLOR blue]({0})[/COLOR]'.format(counters['likedCommunities'])), FOLDER),
            (self.buildurl('/stats'), xbmcgui.ListItem('STATS'), FOLDER),
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
        # load search history data
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
                (self.buildurl('/search', {'q': search['q']}), li, FOLDER)
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
            extended=1,
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
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
                raise VKAddonError('Resolver error.')
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
        # if not passed, let user to enter a new search query
        if 'q' not in self.urlargs:
            self.urlargs['q'] = xbmcgui.Dialog().input('ENTER SEARCH QUERY')
        # if not passed, reset paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for searching videos
        searchedvideos = self.vkapi.video.search(
            extended=1,
            hd=1,
            q=str(self.urlargs['q']),
            adult=1 if self.addon.getSetting('searchadult') == 'true' else 0,  # case sens.!
            search_own=1 if self.addon.getSetting('searchown') == 'true' else 0,  # case sens.!
            longer=int(self.addon.getSetting('searchlonger')) * 60,  # todo: ignored?
            shorter=int(self.addon.getSetting('searchshorter')) * 60,  # todo: ignored?
            sort=int(self.addon.getSetting('searchsort')),
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
        )
        # notify user on results count
        if int(self.urlargs['offset']) == 0:
            self.notify('{0} videos found.'.format(searchedvideos['count']))
        # update search history  # todo: only once!
        searchhistory = self.loadsearchhistory()
        searchhistory['items'].append(
            {
                'q': str(self.urlargs['q']),
                'results': int(searchedvideos['count']),
                'timestamp': int(time.time()),  # todo: ts->dt
                'count': 1,   
            }
        )
        self.savesearchhistory(searchhistory)
        # build list of searched videos
        self.buildlistofvideos(listtype='searchedvideos', listdata=searchedvideos)  # todo: reverse params, listtype const.?

    """ ----- Contextmenu action handlers ----- """

    def addtoalbum(self):
        """
        Add video into album.
        (contextmenu action handler)
        """
        pass  # todo
        # xbmcgui.Dialog().multiselect(heading, options[, autoclose, preselect, useDetails])

    def addalbum(self):
        """
        Add new album.
        (contextmenu action handler)
        """
        albumtitle = xbmcgui.Dialog().input('ENTER ALBUM TITLE')
        addedalbum = self.vkapi.video.addAlbum(
            title=str(albumtitle),
            privacy=['3']  # 3=onlyme  # todo: editable?
        )
        self.log('New album added: {0}'.format(addedalbum['album_id']))
        self.notify('New album added.')
        # todo: refresh list view

    def deletealbum(self):
        """
        Delete album.
        (contextmenu action handler)
        """
        if xbmcgui.Dialog().yesno('CONFIRMATION', 'DO YOU WANT TO DELETE ALBUM?'):
            self.vkapi.video.deleteAlbum(
                album_id=int(self.urlargs['albumid']),
            )
            self.log('Album deleted: {0}'.format(self.urlargs['albumid']))
            self.notify('Album deleted.')
            # todo: refresh list view

    def deletesearch(self):
        """
        Delete search from history.
        (contextmenu action handler)
        """
        pass

    def editsearch(self):
        """
        Edit search in search history.
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
            owner_id=int(self.urlargs['ownerid']),
            item_id=int(self.urlargs['id']),
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
        albumtitle = self.vkapi.video.getAlbumById(
            album_id=int(self.urlargs['albumid']),
        )['title']
        albumtitle = xbmcgui.Dialog().input('EDIT ALBUM TITLE', albumtitle)
        self.vkapi.video.editAlbum(
            album_id=int(self.urlargs['albumid']),
            title=str(albumtitle),
            privacy=['3']  # 3=onlyme  # todo: editable?
        )
        self.log('Album renamed: {0}'.format(self.urlargs['albumid']))
        self.notify('Album renamed.')
        # todo: refresh list view

    def reorderalbum(self):
        """
        Reorder album.
        (contextmenu action handler)
        """
        self.vkapi.video.reorderAlbums(
            album_id=int(self.urlargs['albumid']),
            before=int(self.urlargs['beforeid']),  # todo
            after=int(self.urlargs['afterid']),  # todo
        )
        self.log('Album reordered: {0}'.format(self.urlargs['albumid']))
        # todo: refresh list view

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
            owner_id=int(self.urlargs['ownerid']),
            item_id=int(self.urlargs['id']),
        )
        self.log('Like deleted from video: {0} ({1} likes)'.format(oidid, unlike['likes']))
        self.notify('Like deleted from video. ({0} likes)'.format(unlike['likes']))


class VKAddonError(Exception):
    """
    Exception type raised for all addon errors.
    :param errmsg: str
    """
    def __init__(self, errmsg):
        self.errmsg = errmsg


if __name__ == '__main__':
    # run addon
    VKAddon()
