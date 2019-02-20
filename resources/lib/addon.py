# coding=utf-8
# import web_pdb; web_pdb.set_trace()


import datetime
import os
import pickle
import re
import sys
import urllib  # py2
import urlparse  # py2

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

import tinydb
import vk


# sys.argv passed from Kodi
SYS_ARG_HANDLE = int(sys.argv[1])
SYS_ARG_PATH = str(sys.argv[0])
SYS_ARG_QS = str(sys.argv[2])
# addon
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
# file paths
PATH_PROFILE = xbmc.translatePath(ADDON.getAddonInfo('profile')).decode('utf-8')
PATH_PROFILE_COOKIES = os.path.join(PATH_PROFILE, 'cookiejar.txt').decode('utf-8')
PATH_PROFILE_DB = os.path.join(PATH_PROFILE, 'db.json').decode('utf-8')
# db tables
TBL_ADDON_REQUESTS = 'addonRequests'
TBL_SEARCH_HISTORY = 'searchHistory'
TBL_PLAYED_VIDEOS = 'playedVideos'
# vk api
VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_LANG = 'ru'
VK_API_VERSION = '5.92'
# etc
ALT_COLOR = 'blue'
(FOLDER, NOT_FOLDER) = (True, False)
# errors
ERR_VK_AUTH = 30020
ERR_VK_API = 30021
ERR_ROUTING = 30022
ERR_DATA_FILE = 30023
ERR_RESOLVING = 30024


class VKAddonError(Exception):
    """
    Exception class for addon errors.
    """
    def __init__(self, errid):  # type: (int) -> None
        self.errid = errid


class VKAddon(object):
    """
    Addon class.
    """
    def __init__(self):  # type: () -> None
        """
        Initialize, parse addon request and dispatch routing.
        """
        try:
            self.db = self.initdb()
            self.vksession = self.initvksession()
            self.vkapi = self.initvkapi()
            self.urlpath, self.urlargs = self.parseurl()
            self.dispatch()
        except VKAddonError as e:
            xbmc.log('{0}: {1}'.format(ADDON_ID, ADDON.getLocalizedString(e.errid)), level=xbmc.LOGERROR)
            xbmcgui.Dialog().notification(ADDON_ID, ADDON.getLocalizedString(e.errid), icon=xbmcgui.NOTIFICATION_ERROR)

    def initdb(self):  # type: () -> tinydb.TinyDB
        """
        Initialize addon db (create new data file if doesn't exist).
        """
        db = tinydb.TinyDB(PATH_PROFILE_DB, indent=4, sort_keys=False)
        xbmc.log('{0}: TinyDB initialized: {1}'.format(ADDON_ID, PATH_PROFILE_DB))
        return db

    def initvksession(self):  # type: () -> vk.AuthSession
        """
        Initialize VK session.
        """
        if ADDON.getSetting('vkuseraccesstoken') == '':
            # ask user for entering vk credentials for authorizing addon
            login = xbmcgui.Dialog().input(ADDON.getLocalizedString(30030))
            pswd = xbmcgui.Dialog().input(ADDON.getLocalizedString(30031), option=xbmcgui.ALPHANUM_HIDE_INPUT)
            if not login or not pswd:
                raise VKAddonError(ERR_VK_AUTH)
            # create vk session
            try:
                vksession = vk.AuthSession(VK_API_APP_ID, login, pswd, VK_API_SCOPE)
            except vk.VkAuthError:
                raise VKAddonError(ERR_VK_AUTH)
            xbmc.log('{0}: VK session created.'.format(ADDON_ID))
            # save obtained user access token and cookies
            ADDON.setSetting('vkuseraccesstoken', vksession.access_token)
            self.savecookies(vksession.auth_session.cookies)
        else:
            # restore vk session by sending existing token
            try:
                vksession = vk.Session(ADDON.getSetting('vkuseraccesstoken'))
            except vk.VkAuthError:
                raise VKAddonError(ERR_VK_AUTH)
            xbmc.log('{0}: VK session restored.'.format(ADDON_ID))
            vksession.requests_session.cookies = self.loadcookies()
        return vksession

    def initvkapi(self):  # type: () -> vk.API
        """
        Initialize VK API.
        """
        try:
            # create api object
            vkapi = vk.API(self.vksession, v=VK_API_VERSION, lang=VK_API_LANG)
            _ = vkapi.stats.trackVisitor()
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: VK API initialized.'.format(ADDON_ID))
        return vkapi

    def savecookies(self, cookiejar):  # type: (object) -> None
        """
        Save cookiejar object to addon data file (truncate if exists).
        """
        try:
            with open(PATH_PROFILE_COOKIES, 'wb') as f:
                pickle.dump(cookiejar, f)
        except OSError:
            raise VKAddonError(ERR_DATA_FILE)
        xbmc.log('{0}: Cookies saved: {1}'.format(ADDON_ID, PATH_PROFILE_COOKIES))

    def loadcookies(self):  # type: () -> object
        """
        Load cookiejar object from addon data file (must exist since auth).
        """
        try:
            with open(PATH_PROFILE_COOKIES, 'rb') as f:
                cookiejar = pickle.load(f)
        except OSError:
            raise VKAddonError(ERR_DATA_FILE)
        xbmc.log('{0}: Cookies loaded: {1}'.format(ADDON_ID, PATH_PROFILE_COOKIES))
        return cookiejar

    def buildurl(self, urlpath, urlargs=None):  # type: (str, dict) -> str
        """
        Build addon url.
        """
        url = 'plugin://{0}{1}'.format(ADDON_ID, urlpath)
        if urlargs:
            url += '?{0}'.format(urllib.urlencode(urlargs))
        return url

    def parseurl(self):  # type: () -> tuple
        """
        Parse addon url.
        """
        urlpath = str(urlparse.urlsplit(SYS_ARG_PATH)[2])
        urlargs = {}
        if SYS_ARG_QS.startswith('?'):
            urlargs = urlparse.parse_qs(SYS_ARG_QS.lstrip('?'))
            for k, v in list(urlargs.items()):
                urlargs[k] = v.pop()
        # update addon requests db
        request = {
            'dt': datetime.datetime.now().isoformat(),
            'urlpath': urlpath,
            'urlargs': urlargs,
        }
        _ = self.db.table(TBL_ADDON_REQUESTS).insert(request)
        xbmc.log('{0}: Addon requests db updated: {1}'.format(ADDON_ID, request))
        return urlpath, urlargs

    def dispatch(self):  # type: () -> None
        """
         Dispatch addon routing.
        """
        routing = {
            # common
            '/': self.listmenu,
            '/logout': self.logout,
            # search history
            '/searchhistory': self.listsearchhistory,
            '/deletesearch': self.deletesearch,
            # videos
            '/searchvideos': self.searchvideos,
            '/videos': self.listvideos,
            '/communityvideos': self.listcommunityvideos,
            '/albumvideos': self.listalbumvideos,
            '/likedvideos': self.listlikedvideos,
            '/playedvideos': self.listplayedvideos,
            '/playvideo': self.playvideo,
            '/likevideo': self.likevideo,
            '/unlikevideo': self.unlikevideo,
            '/addvideotoalbums': self.addvideotoalbums,
            # video albums
            '/albums': self.listalbums,
            '/renamealbum': self.renamealbum,
            '/reorderalbum': self.reorderalbum,
            '/deletealbum': self.deletealbum,
            '/createalbum': self.createalbum,
            # communities
            '/communities': self.listcommunities,
            '/likedcommunities': self.listlikedcommunities,
            '/likecommunity': self.likecommunity,
            '/unlikecommunity': self.unlikecommunity,
            '/unfollowcommunity': self.unfollowcommunity,
        }
        try:
            handler = routing[self.urlpath]
        except KeyError:
            raise VKAddonError(ERR_ROUTING)
        xbmc.log('{0}: Routing dispatched: {1}'.format(ADDON_ID, handler.__name__))
        handler()

    # ----- common -----

    def listmenu(self):  # type: () -> None
        """
        List menu.

        ``plugin://plugin.video.vk/``
        """
        # collect counters
        try:
            counters = dict(
                self.vkapi.execute.getMenuCounters(),
                searchhistory=len(self.db.table(TBL_SEARCH_HISTORY)),
                playedvideos=len(self.db.table(TBL_PLAYED_VIDEOS)),
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Counters: {1}'.format(ADDON_ID, counters))
        # create menu items
        listitems = [
            # search videos
            (
                self.buildurl('/searchvideos'),
                xbmcgui.ListItem('{0}'.format(ADDON.getLocalizedString(30040))),
                FOLDER
            ),
            # search history
            (
                self.buildurl('/searchhistory'),
                xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30041), ALT_COLOR, counters['searchhistory'])),
                FOLDER
            ),
            # played videos
            (
                self.buildurl('/playedvideos'),
                xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30047), ALT_COLOR, counters['playedvideos'])),
                FOLDER
            ),
            # videos
            (
                self.buildurl('/videos'),
                xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30042), ALT_COLOR, counters['videos'])),
                FOLDER
            ),
            # liked videos
            (
                self.buildurl('/likedvideos'),
                xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30043), ALT_COLOR, counters['likedvideos'])),
                FOLDER
            ),
            # albums
            (
                self.buildurl('/albums'),
                xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30044), ALT_COLOR, counters['albums'])),
                FOLDER
            ),
            # communities
            (
                self.buildurl('/communities'),
                xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30045), ALT_COLOR, counters['communities'])),
                FOLDER
            ),
            # liked communities
            (
                self.buildurl('/likedcommunities'),
                xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30046), ALT_COLOR, counters['likedcommunities'])),
                FOLDER
            ),
        ]
        # show list in kodi
        xbmcplugin.setContent(SYS_ARG_HANDLE, 'files')
        xbmcplugin.addDirectoryItems(SYS_ARG_HANDLE, listitems, len(listitems))
        xbmcplugin.addSortMethod(SYS_ARG_HANDLE, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(SYS_ARG_HANDLE)

    def logout(self):  # type: () -> None
        """
        Logout user.

        ``plugin://plugin.video.vk/logout``
        """
        # reset user access token, delete cookies
        ADDON.setSetting('vkuseraccesstoken', '')
        os.remove(PATH_PROFILE_COOKIES)
        xbmc.log('{0}: User logged out.'.format(ADDON_ID))
        xbmcgui.Dialog().notification(ADDON_ID, ADDON.getLocalizedString(30032))

    # ----- search history -----

    def listsearchhistory(self):  # type: () -> None
        """
        List search history.

        ``plugin://plugin.video.vk/searchhistory``
        """
        # query db for search history list, empty if no data
        searchhistory = {
            'count': len(self.db.table(TBL_SEARCH_HISTORY)),
            'items': self.db.table(TBL_SEARCH_HISTORY).all(),
        }
        xbmc.log('{0}: Search history: {1}'.format(ADDON_ID, searchhistory))
        # create list, sort by lastUsed reversed
        listitems = []
        for search in sorted(searchhistory['items'], key=lambda x: x['lastUsed'], reverse=True):
            # create search item
            li = xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(search['q'], ALT_COLOR, search['resultsCount']))
            # create context menu
            li.addContextMenuItems(
                [
                    # delete search
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30081)),
                        'RunPlugin({0})'.format(self.buildurl('/deletesearch', {'searchid': search.doc_id}))
                    ),
                    # search videos
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051)),
                        'Container.Update({0})'.format(self.buildurl('/searchvideos'))  # cont.upd. required!
                    ),
                    # search similar
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30080)),
                        'Container.Update({0})'.format(self.buildurl('/searchvideos', {'similarq': search['q']}))  # cont.upd. required!
                    ),
                ]
            )
            # add search item to list
            listitems.append(
                (
                    self.buildurl('/searchvideos', {'q': search['q']}),
                    li,
                    FOLDER
                )
            )
        # show list in kodi, even if empty
        xbmcplugin.setContent(SYS_ARG_HANDLE, 'files')
        xbmcplugin.addDirectoryItems(SYS_ARG_HANDLE, listitems, len(listitems))
        xbmcplugin.addSortMethod(SYS_ARG_HANDLE, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(SYS_ARG_HANDLE)

    def deletesearch(self):  # type: () -> None
        """
        Delete search from search history.

        ``plugin://plugin.video.vk/deletesearch?searchid={searchid}``
        """
        # get urlargs
        searchid = int(self.urlargs.get('searchid'))
        # ask user for confirmation
        if not xbmcgui.Dialog().yesno(ADDON.getLocalizedString(30081), ADDON.getLocalizedString(30082)):
            return
        # query db for deleting
        _ = self.db.table(TBL_SEARCH_HISTORY).remove(doc_ids=[searchid])
        xbmc.log('{0}: Search deleted: {1}'.format(ADDON_ID, searchid))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    # ----- videos -----

    def searchvideos(self):  # type: () -> None
        """
        Search videos.

        ``plugin://plugin.video.vk/searchvideos[?similarq={similarq}]``
        ``plugin://plugin.video.vk/searchvideos?q={q}[&offset={offset}]``
        """
        # get urlargs
        similarq = self.urlargs.get('similarq', '')
        q = self.urlargs.get('q', None)
        offset = int(self.urlargs.get('offset', 0))
        # if q not passed, ask user for entering a new query / editing similar one
        if not q:
            q = self.urlargs['q'] = xbmcgui.Dialog().input(ADDON.getLocalizedString(30051), defaultt=similarq)
            if not q:
                return
        # request vk api for searched videos
        kwargs = {
            'extended': 1,
            'hd': 1,
            'adult': 1 if ADDON.getSetting('searchadult') == 'true' else 0,  # case sens.!
            'search_own': 1 if ADDON.getSetting('searchown') == 'true' else 0,  # case sens.!
            'sort': int(ADDON.getSetting('searchsort')),
            'q': q,
            'offset': offset,
            'count': int(ADDON.getSetting('itemsperpage')),
        }
        if ADDON.getSetting('searchduration') == '1':
            kwargs['longer'] = int(ADDON.getSetting('searchdurationmins')) * 60
        elif ADDON.getSetting('searchduration') == '2':
            kwargs['shorter'] = int(ADDON.getSetting('searchdurationmins')) * 60
        try:
            searchedvideos = self.vkapi.video.search(
                **kwargs
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Searched videos: {1}'.format(ADDON_ID, searchedvideos))
        # only once
        if offset == 0:
            # update search history db with the last search
            lastsearch = {
                'q': q.lower(),
                'resultsCount': int(searchedvideos['count']),
                'lastUsed': datetime.datetime.now().isoformat()
            }
            self.db.table(TBL_SEARCH_HISTORY).upsert(lastsearch, tinydb.where('q') == lastsearch['q'])
            xbmc.log('{0}: Search history db updated: {1}'.format(ADDON_ID, lastsearch))
            # notify search results count
            xbmcgui.Dialog().notification(ADDON_ID, ADDON.getLocalizedString(30052).format(searchedvideos['count']))
        # build list
        self.buildlistofvideos(searchedvideos)

    def listvideos(self):  # type: () -> None
        """
        List videos.

        ``plugin://plugin.video.vk/videos[?offset={offset}]``
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # request vk api
        try:
            videos = self.vkapi.video.get(
                extended=1,
                offset=offset,
                count=int(ADDON.getSetting('itemsperpage'))
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Videos: {1}'.format(ADDON_ID, videos))
        # build list
        self.buildlistofvideos(videos)

    def listlikedvideos(self):  # type: () -> None
        """
        List liked videos.

        ``plugin://plugin.video.vk/likedvideos[?offset={offset}]``
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # request vk api
        try:
            likedvideos = self.vkapi.fave.getVideos(
                extended=1,
                offset=offset,
                count=int(ADDON.getSetting('itemsperpage')),
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Liked videos: {1}'.format(ADDON_ID, likedvideos))
        # build list
        self.buildlistofvideos(likedvideos)

    def listalbumvideos(self):  # type: () -> None
        """
        List album videos.

        ``plugin://plugin.video.vk/albumvideos?albumid={albumid}[&offset={offset}]``
        """
        # get urlargs
        albumid = int(self.urlargs.get('albumid'))
        offset = int(self.urlargs.get('offset', 0))
        # request vk api
        try:
            albumvideos = self.vkapi.video.get(
                extended=1,
                album_id=albumid,
                offset=offset,
                count=int(ADDON.getSetting('itemsperpage')),
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Album videos: {1}'.format(ADDON_ID, albumvideos))
        # build list
        self.buildlistofvideos(albumvideos)

    def listcommunityvideos(self):  # type: () -> None
        """
        List community videos.

        ``plugin://plugin.video.vk/communityvideos?ownerid={ownerid}[&offset={offset}]``
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        offset = int(self.urlargs.get('offset', 0))
        # request vk api
        try:
            communityvideos = self.vkapi.video.get(
                extended=1,
                owner_id=ownerid,
                offset=offset,
                count=int(ADDON.getSetting('itemsperpage')),
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Community videos: {1}'.format(ADDON_ID, communityvideos))
        # build list
        self.buildlistofvideos(communityvideos)

    def listplayedvideos(self):  # type: () -> None
        """
        List played videos.

        ``plugin://plugin.video.vk/playedvideos``
        """
        # get urlargs
        # offset = int(self.urlargs.get('offset', 0))
        # query db for played videos list, empty if no data
        playedvideos = {
            'count': len(self.db.table(TBL_PLAYED_VIDEOS)),
            'items': self.db.table(TBL_PLAYED_VIDEOS).all(),
            # tinydb.where('id')
            # int(ADDON.getSetting('itemsperpage'))
        }
        xbmc.log('{0}: Played videos: {1}'.format(ADDON_ID, playedvideos))
        # build list
        self.buildlistofvideos(playedvideos)

    def buildlistofvideos(self, listdata):  # type: (dict) -> None
        """
        Build list of videos.

        ``/searchvideos, /videos, /likedvideos, /albumvideos, /communityvideos, /playedvideos``
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # create list
        listitems = []
        for video in listdata['items']:
            # create video item
            li = xbmcgui.ListItem(video['title'])
            # set isplayable
            li.setProperty('IsPlayable', 'true')
            # set infolabels
            li.setInfo(
                'video',
                {
                    'title': video['title'],
                    'plot': video['description'],
                    'duration': video['duration'],
                    'date': datetime.datetime.fromtimestamp(video['date']).strftime('%d.%m.%Y')
                }
            )
            # set stream infolabels
            li.addStreamInfo(
                'video',
                {
                    'width': video.get('width', None),
                    'height': video.get('height', None)
                }
            )
            # set art
            if 'photo_800' in video:
                maxthumb = video['photo_800']
            elif 'photo_640' in video:
                maxthumb = video['photo_640']
            else:
                maxthumb = video['photo_320']
            li.setArt({'thumb': maxthumb})
            # create context menu
            cmi = []
            if video['is_favorite']:
                # unlike video
                cmi.append(
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30054)),
                        'RunPlugin({0})'.format(self.buildurl('/unlikevideo', {'ownerid': video['owner_id'], 'videoid': video['id']}))
                    )
                )
            else:
                # like video
                cmi.append(
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30053)),
                        'RunPlugin({0})'.format(self.buildurl('/likevideo', {'ownerid': video['owner_id'], 'videoid': video['id']}))
                    )
                )
            # add video to albums
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30055)),
                    'RunPlugin({0})'.format(self.buildurl('/addvideotoalbums', {'ownerid': video['owner_id'], 'videoid': video['id']}))
                )
            )
            # search videos
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051)),
                    'Container.Update({0})'.format(self.buildurl('/searchvideos'))  # cont.upd. required!
                )
            )
            # search similar
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30080)),
                    'Container.Update({0})'.format(self.buildurl('/searchvideos', {'similarq': video['title']}))  # cont.upd. required!
                )
            )
            li.addContextMenuItems(cmi)
            # add video item to list
            listitems.append(
                (
                    self.buildurl('/playvideo', {'ownerid': video['owner_id'], 'videoid': video['id']}),
                    li,
                    NOT_FOLDER
                )
            )
        # paginator item
        if offset + int(ADDON.getSetting('itemsperpage')) < listdata['count']:
            urlargsnext = dict(self.urlargs, offset=offset+int(ADDON.getSetting('itemsperpage')))
            listitems.append(
                (
                    self.buildurl(self.urlpath, urlargsnext),
                    xbmcgui.ListItem('[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30050))),
                    FOLDER
                )
            )
        # force custom view mode for videos if enabled
        if ADDON.getSetting('forcevideoviewmode') == 'true':  # case sens!
            xbmc.executebuiltin('Container.SetViewMode({0})'.format(int(ADDON.getSetting('forcevideoviewmodeid'))))
        # show list in kodi, even if empty
        xbmcplugin.setContent(SYS_ARG_HANDLE, 'videos')
        xbmcplugin.addDirectoryItems(SYS_ARG_HANDLE, listitems, len(listitems))
        xbmcplugin.addSortMethod(SYS_ARG_HANDLE, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(SYS_ARG_HANDLE)

    def playvideo(self):  # type: () -> None
        """
        Play video.

        ``plugin://plugin.video.vk/playvideo?ownerid={ownerid}&videoid={videoid}``
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        videoid = int(self.urlargs.get('videoid'))
        oidid = '{0}_{1}'.format(ownerid, videoid)
        # request vk api for video
        try:
            video = self.vkapi.video.get(extended=1, videos=oidid)['items'].pop()
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        # resolve playable streams via vk videoinfo url
        vi = self.vksession.requests_session.get(
            url='https://vk.com/al_video.php?act=show_inline&al=1&video={0}'.format(oidid),
            headers={'User-Agent': xbmc.getUserAgent()},  # +cookies required (sent autom.)
        )
        xbmc.log('{0}: Resolving video url: {1}'.format(ADDON_ID, vi.url))
        matches = re.findall(r'"url(\d+)":"([^"]+)"', vi.text.replace('\\', ''))
        playables = {}
        for m in matches:
            qual = int(m[0])
            playables[qual] = m[1]
        if playables:
            # streams resolved, use one of best quality
            maxqual = max(playables.keys())
            xbmc.log('{0}: Playable stream resolved: {1}'.format(ADDON_ID, playables[maxqual]))
        else:
            raise VKAddonError(ERR_RESOLVING)
        # update played videos db
        video.update(
            {
                'oidid': oidid,
                'lastPlayed': datetime.datetime.now().isoformat(),
            }
        )
        self.db.table(TBL_PLAYED_VIDEOS).upsert(video, tinydb.where('oidid') == oidid)
        xbmc.log('{0}: Played videos db updated: {1}'.format(ADDON_ID, video))
        # create playable item for kodi player
        li = xbmcgui.ListItem(path=playables[maxqual])
        xbmcplugin.setContent(SYS_ARG_HANDLE, 'videos')
        xbmcplugin.setResolvedUrl(SYS_ARG_HANDLE, True, li)

    def likevideo(self):  # type: () -> None
        """
        Like video.

        ``plugin://plugin.video.vk/likevideo?ownerid={ownerid}&videoid={videoid}``
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        videoid = int(self.urlargs.get('videoid'))
        oidid = '{0}_{1}'.format(ownerid, videoid)
        # request vk api
        try:
            _ = self.vkapi.likes.add(
                type='video',
                owner_id=ownerid,
                item_id=videoid,
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Video liked: {1}'.format(ADDON_ID, oidid))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def unlikevideo(self):  # type: () -> None
        """
        Unlike video.

        ``plugin://plugin.video.vk/unlikevideo?ownerid={ownerid}&videoid={videoid}``
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        videoid = int(self.urlargs.get('videoid'))
        oidid = '{0}_{1}'.format(ownerid, videoid)
        # request vk api
        try:
            _ = self.vkapi.likes.delete(
                type='video',
                owner_id=ownerid,
                item_id=videoid,
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Video unliked: {1}'.format(ADDON_ID, oidid))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def addvideotoalbums(self):  # type: () -> None
        """
        Add video to albums.

        ``plugin://plugin.video.vk/addvideotoalbums?ownerid={ownerid}&videoid={videoid}``
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        videoid = int(self.urlargs.get('videoid'))
        oidid = '{0}_{1}'.format(ownerid, videoid)
        # request vk api
        try:
            # get user albums
            albums = self.vkapi.video.getAlbums(
                need_system=0,
                offset=0,
                count=100,
            )
            # get list of album ids for video
            albumids = self.vkapi.video.getAlbumsByVideo(
                owner_id=ownerid,
                video_id=videoid,
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        # create dialog w current sel
        opts = []
        sel = []
        for i, album in enumerate(albums['items']):
            opts.append(album['title'])
            if album['id'] in albumids:
                sel.append(i)
        # show dialog, get new sel
        newsel = xbmcgui.Dialog().multiselect(ADDON.getLocalizedString(30055), opts, preselect=sel)
        if newsel is None or newsel == sel:
            return
        # sel changed
        newalbumids = []
        for i in newsel:
            newalbumids.append(albums['items'][i]['id'])
        # request vk api
        try:
            # remove sel album ids if any
            if len(albumids) > 0:
                _ = self.vkapi.video.removeFromAlbum(
                    owner_id=ownerid,
                    video_id=videoid,
                    album_ids=albumids
                )
            # add new sel album ids if any
            if len(newalbumids) > 0:
                _ = self.vkapi.video.addToAlbum(
                    owner_id=ownerid,
                    video_id=videoid,
                    album_ids=newalbumids
                )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Video added to albums: {1}'.format(ADDON_ID, oidid))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    # ----- video albums -----

    def listalbums(self):  # type: () -> None
        """
        List albums.

        ``plugin://plugin.video.vk/albums[?offset={offset}]``
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # workaround due api's maxperpage=100
        albumsperpage = int(ADDON.getSetting('itemsperpage')) if int(ADDON.getSetting('itemsperpage')) <= 100 else 100
        # request vk api for albums
        try:
            albums = self.vkapi.video.getAlbums(
                extended=1,
                offset=offset,
                count=albumsperpage,
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Albums: {1}'.format(ADDON_ID, albums))
        # create list
        listitems = []
        for i, album in enumerate(albums['items']):
            # create album item
            li = xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(album['title'], ALT_COLOR, int(album['count'])))
            # art
            if album['count'] > 0:
                li.setArt({'thumb': album['photo_320']})
            # before/after album ids for reordering
            beforeid = albums['items'][i - 1]['id'] if i > 0 else None
            afterid = albums['items'][i + 1]['id'] if i < len(albums['items']) - 1 else None
            # context menu
            li.addContextMenuItems(
                [
                    # reorder album up
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30061)),
                        'RunPlugin({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'beforeid': beforeid}))
                    ),
                    # reorder album down
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30062)),
                        'RunPlugin({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'afterid': afterid}))
                    ),
                    # rename album
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30060)),
                        'RunPlugin({0})'.format(self.buildurl('/renamealbum', {'albumid': album['id']}))
                    ),
                    # delete album
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30063)),
                        'RunPlugin({0})'.format(self.buildurl('/deletealbum', {'albumid': album['id']}))
                    ),
                    # create new album
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30065)),
                        'RunPlugin({0})'.format(self.buildurl('/createalbum'))
                    ),
                    # search videos
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051)),
                        'Container.Update({0})'.format(self.buildurl('/searchvideos'))  # cont.upd. required!
                    ),
                ]
            )
            listitems.append(
                (
                    self.buildurl('/albumvideos', {'albumid': album['id']}),
                    li,
                    FOLDER
                )
            )
        # paginator item, modded w albumsperpage
        if offset + albumsperpage < albums['count']:
            urlargsnext = dict(self.urlargs, offset=offset + albumsperpage)
            listitems.append(
                (
                    self.buildurl(self.urlpath, urlargsnext),
                    xbmcgui.ListItem('[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30050))),
                    FOLDER
                )
            )
        # show album list in kodi, even if empty
        xbmcplugin.setContent(SYS_ARG_HANDLE, 'files')
        xbmcplugin.addDirectoryItems(SYS_ARG_HANDLE, listitems, len(listitems))
        xbmcplugin.addSortMethod(SYS_ARG_HANDLE, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(SYS_ARG_HANDLE)

    def reorderalbum(self):  # type: () -> None
        """
        Reorder album.

        ``plugin://plugin.video.vk/reorderalbum?albumid={albumid}(&beforeid={beforeid}|&afterid={afterid})``
        """
        # get urlargs
        albumid = int(self.urlargs.get('albumid'))
        reorder = {}
        if 'beforeid' in self.urlargs:
            reorder['before'] = int(self.urlargs.get('beforeid'))
        elif 'afterid' in self.urlargs:
            reorder['after'] = int(self.urlargs.get('afterid'))
        # request vk api
        try:
            _ = self.vkapi.video.reorderAlbums(
                album_id=albumid,
                **reorder
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Album reordered: {1}'.format(ADDON_ID, albumid))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def renamealbum(self):  # type: () -> None
        """
        Rename album.

        ``plugin://plugin.video.vk/renamealbum?albumid={albumid}``
        """
        # get urlargs
        albumid = int(self.urlargs.get('albumid'))
        # request vk api for album
        try:
            album = self.vkapi.video.getAlbumById(
                album_id=albumid
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        # ask user for editing current album title
        newtitle = xbmcgui.Dialog().input(ADDON.getLocalizedString(30060), defaultt=album['title'])
        if not newtitle or newtitle == album['title']:
            return
        # request vk api for renaming album
        try:
            self.vkapi.video.editAlbum(
                album_id=albumid,
                title=newtitle,
                privacy=3  # 3=onlyme
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Album renamed: {1}'.format(ADDON_ID, albumid))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def deletealbum(self):  # type: () -> None
        """
        Delete album.

        ``plugin://plugin.video.vk/deletealbum?albumid={albumid}``
        """
        # get urlargs
        albumid = int(self.urlargs.get('albumid'))
        # ask user for confirmation
        if not xbmcgui.Dialog().yesno(ADDON.getLocalizedString(30063), ADDON.getLocalizedString(30064)):
            return
        # request vk api
        try:
            _ = self.vkapi.video.deletealbum()
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Album deleted: {1}'.format(ADDON_ID, albumid))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def createalbum(self):  # type: () -> None
        """
        Create album.

        ``plugin://plugin.video.vk/createalbum``
        """
        # ask user for entering new album title
        albumtitle = xbmcgui.Dialog().input(ADDON.getLocalizedString(30065))
        if not albumtitle:
            return
        # request vk api
        try:
            album = self.vkapi.video.addAlbum(
                title=albumtitle,
                privacy=3,  # 3=onlyme
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Album created: {1}'.format(ADDON_ID, album['album_id']))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    # ----- communities -----

    def listcommunities(self):  # type: () -> None
        """
        List communities.

        ``plugin://plugin.video.vk/communities[?offset={offset}]``
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # request vk api
        try:
            communities = self.vkapi.groups.get(
                extended=1,
                offset=offset,
                count=int(ADDON.getSetting('itemsperpage')),
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Communities: {1}'.format(ADDON_ID, communities))
        # build list
        self.buildlistofcommunities(communities)

    def listlikedcommunities(self):  # type: () -> None
        """
        List liked communities.

        ``plugin://plugin.video.vk/likedcommunities[?offset={offset}]``
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # request vk api
        try:
            likedcommunities = self.vkapi.fave.getLinks(
                offset=offset,
                count=int(ADDON.getSetting('itemsperpage')),
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Liked communities: {1}'.format(ADDON_ID, likedcommunities))
        # build list
        self.buildlistofcommunities(likedcommunities)

    def buildlistofcommunities(self, listdata):  # type: (dict) -> None
        """
        Build list of communities.

        ``/communities, /likedcommunities``
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # create list
        listtype = self.urlpath
        listitems = []
        _namekey = 'title' if listtype == '/likedcommunities' else 'name'
        for community in listdata['items']:
            if listtype == '/likedcommunities':
                community['id'] = community['id'].split('_')[2]
            # create community item
            li = xbmcgui.ListItem(community[_namekey])
            # set art
            li.setArt({'thumb': community['photo_200']})
            # create context menu
            cmi = []
            # unlike/like community
            if listtype == '/likedcommunities':
                cmi.append(
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30071)),
                        'RunPlugin({0})'.format(self.buildurl('/unlikecommunity', {'communityid': community['id']}))
                    )
                )
            else:
                cmi.append(
                    (
                        '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30070)),
                        'RunPlugin({0})'.format(self.buildurl('/likecommunity', {'communityid': community['id']}))
                    )
                )
            # unfollow community
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30072)),
                    'RunPlugin({0})'.format(self.buildurl('/unfollowcommunity', {'communityid': community['id']}))
                )
            )
            # search videos
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051)),
                    'Container.Update({0})'.format(self.buildurl('/searchvideos'))  # cont.upd. required!
                )
            )
            li.addContextMenuItems(cmi)
            # add community item to list
            listitems.append(
                (
                    self.buildurl('/communityvideos', {'ownerid': '-{0}'.format(community['id'])}),  # negative id required!
                    li,
                    FOLDER
                )
            )
        # paginator item
        if offset + int(ADDON.getSetting('itemsperpage')) < listdata['count']:
            urlargsnext = dict(self.urlargs, offset=offset+int(ADDON.getSetting('itemsperpage')))
            listitems.append(
                (
                    self.buildurl(self.urlpath, urlargsnext),
                    xbmcgui.ListItem('[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30050))),
                    FOLDER
                )
            )
        # show list in kodi, even if empty
        xbmcplugin.setContent(SYS_ARG_HANDLE, 'files')
        xbmcplugin.addDirectoryItems(SYS_ARG_HANDLE, listitems, len(listitems))
        xbmcplugin.addSortMethod(SYS_ARG_HANDLE, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(SYS_ARG_HANDLE)

    def likecommunity(self):  # type: () -> None
        """
        Like community.

        ``plugin://plugin.video.vk/likecommunity?communityid={communityid}``
        """
        # get urlargs
        communityid = int(self.urlargs.get('communityid'))
        # request vk api
        try:
            _ = self.vkapi.fave.addGroup(
                group_id=communityid
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Community liked: {1}'.format(ADDON_ID, communityid))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def unlikecommunity(self):  # type: () -> None
        """
        Unlike community.

        ``plugin://plugin.video.vk/unlikecommunity?communityid={communityid}``
        """
        # get urlargs
        communityid = int(self.urlargs.get('communityid'))
        # request vk api
        try:
            _ = self.vkapi.fave.removeGroup(
                group_id=communityid
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Community unliked: {1}'.format(ADDON_ID, communityid))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def unfollowcommunity(self):  # type: () -> None
        """
        Unfollow community.

        ``plugin://plugin.video.vk/unfollowcommunity?communityid={communityid}``
        """
        # get urlargs
        communityid = int(self.urlargs.get('communityid'))
        # request vk api
        try:
            _ = self.vkapi.groups.leave(
                group_id=communityid
            )
        except vk.VkAPIError:
            raise VKAddonError(ERR_VK_API)
        xbmc.log('{0}: Community unfollowed: {1}'.format(ADDON_ID, communityid))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')


if __name__ == '__main__':
    VKAddon()
