# coding=utf-8

"""
VK (plugin.video.vk)

Kodi add-on for watching videos from VK.com social network.
"""

__version__ = '1.1.0-devel'


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

sys.path.append(os.path.join(xbmc.translatePath(xbmcaddon.Addon().getAddonInfo('path')).decode('utf-8'), 'resources', 'lib'))
import tinydb  # noqa: E402
import vk  # noqa: E402


ALT_COLOR = 'blue'
FOLDER, NOT_FOLDER = (True, False)
FP_PROFILE = xbmc.translatePath(xbmcaddon.Addon().getAddonInfo('profile')).decode('utf-8')
FP_PROFILE_COOKIES = os.path.join(FP_PROFILE, 'cookiejar.txt')
FP_PROFILE_DB = os.path.join(FP_PROFILE, 'db.json')
TABLE_ADDON_REQUESTS = 'addonRequests'
TABLE_SEARCH_HISTORY = 'searchHistory'
VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_LANG = 'ru'
VK_API_VERSION = '5.92'  # https://vk.com/dev/versions


class VKAddonError(Exception):
    pass


class VKAddon:

    def __init__(self):
        """
        Initialize addon, parse addon request url and dispatch routing.
        """
        self.handle = int(sys.argv[1])
        self.addon = xbmcaddon.Addon()
        self.db = self.initdb()
        self.vkapi = self.initvkapi()
        # parse addon request url
        self.urlbase = 'plugin://' + self.addon.getAddonInfo('id')
        self.urlpath = sys.argv[0].replace(self.urlbase, '')
        self.urlargs = {}
        if sys.argv[2].startswith('?'):
            self.urlargs = urlparse.parse_qs(sys.argv[2].lstrip('?'))
            for k, v in list(self.urlargs.items()):
                self.urlargs[k] = v.pop()
        self.url = self.buildurl(self.urlpath, self.urlargs)
        # save addon request
        request = {
            'dt': datetime.datetime.now().isoformat(),
            'url': self.url
        }
        self.db.table(TABLE_ADDON_REQUESTS).insert(request)
        # dispatch addon routing
        routing = {
            # common
            '/': self.menu,
            '/logout': self.logout,
            # videos
            '/searchvideos': self.searchvideos,
            '/videos': self.videos,
            '/communityvideos': self.communityvideos,
            '/albumvideos': self.albumvideos,
            '/likedvideos': self.likedvideos,
            '/playvideo': self.playvideo,
            '/likevideo': self.likevideo,
            '/unlikevideo': self.unlikevideo,
            '/addvideotoalbums': self.addvideotoalbums,
            # video albums
            '/albums': self.albums,
            '/renamealbum': self.renamealbum,
            '/reorderalbum': self.reorderalbum,
            '/deletealbum': self.deletealbum,
            '/createalbum': self.createalbum,
            # communities
            '/communities': self.communities,
            '/likedcommunities': self.likedcommunities,
            '/likecommunity': self.likecommunity,
            '/unlikecommunity': self.unlikecommunity,
            '/unfollowcommunity': self.unfollowcommunity,
            # search history
            '/searchhistory': self.searchhistory,
            '/deletesearch': self.deletesearch,
        }
        try:
            handler = routing[self.urlpath]
            self.log('Routing dispatched: request={0}, handler={1}'.format(request, handler.__name__))
            handler()
        except KeyError:
            self.log('Routing error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30022), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    # ----- helpers -----

    def initdb(self):
        """
        Initialize TinyDB addon data file (create new if doesn't exist).

        :rtype: tinydb.TinyDB
        """
        db = tinydb.TinyDB(FP_PROFILE_DB, indent=4, sort_keys=False)
        self.log('TinyDB initialized: {0}'.format(FP_PROFILE_DB))
        return db

    def initvkapi(self):
        """
        Initialize VK API.

        :rtype: vk.API
        """
        try:
            # obtain new user access token by authorizing addon using user credentials
            if self.addon.getSetting('vkuseraccesstoken') == '':
                credentials = {
                    'login': xbmcgui.Dialog().input(self.addon.getLocalizedString(30030)),
                    'password': xbmcgui.Dialog().input(self.addon.getLocalizedString(30031), option=xbmcgui.ALPHANUM_HIDE_INPUT)
                }
                if not all(credentials.values()):
                    raise vk.exceptions.VkAuthError()
                self.vksession = vk.AuthSession(VK_API_APP_ID, credentials['login'], credentials['password'], VK_API_SCOPE)
                self.log('VK session created.')
                self.addon.setSetting('vkuseraccesstoken', self.vksession.access_token)
                self.savecookies(self.vksession.auth_session.cookies)
            # restore session by sending user access token
            else:
                self.vksession = vk.Session(self.addon.getSetting('vkuseraccesstoken'))
                self.log('VK session restored.')
                self.vksession.requests_session.cookies = self.loadcookies()
        except vk.exceptions.VkAuthError:
            self.log('VK authorization error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30020), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        try:
            # create vkapi
            vkapi = vk.API(self.vksession, v=VK_API_VERSION, lang=VK_API_LANG)
            vkapi.stats.trackVisitor()
            self.log('VK API initialized.')
            return vkapi
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def savecookies(self, cookiejar):
        """
        Save cookiejar object to addon data file (rewrite if exists).

        :param object cookiejar:
        :rtype: None
        """
        with open(FP_PROFILE_COOKIES, 'wb') as f:
            pickle.dump(cookiejar, f)
        self.log('Cookies saved: {0}'.format(FP_PROFILE_COOKIES))

    def loadcookies(self):
        """
        Load cookiejar object from addon data file (must exist since auth).

        :rtype: object
        """
        try:
            with open(FP_PROFILE_COOKIES, 'rb') as f:
                cookiejar = pickle.load(f)
            self.log('Cookies loaded: {0}'.format(FP_PROFILE_COOKIES))
            return cookiejar
        except OSError:
            # file doesn't exist
            self.log('Addon data file error: {0}'.format(FP_PROFILE_COOKIES), level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30023), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def buildurl(self, urlpath, urlargs=None):
        """
        Build addon url.

        :param string urlpath:
        :param dict urlargs:
        :rtype: string
        """
        url = self.urlbase + urlpath
        if urlargs:
            url += '?' + urllib.urlencode(urlargs)
        return url

    def log(self, msg, level=xbmc.LOGDEBUG):
        """
        Log message into default Kodi.log using an uniform style.

        :param string msg:
        :param int level:
        :rtype: None
        """
        msg = '{0}: {1}'.format(self.addon.getAddonInfo('id'), msg)
        xbmc.log(msg, level)

    def notify(self, msg, icon=xbmcgui.NOTIFICATION_INFO):
        """
        Notify user using uniform style.

        :param string msg:
        :param string icon:
        :rtype: None
        """
        heading = self.addon.getAddonInfo('name')
        xbmcgui.Dialog().notification(heading, msg, icon)

    # ----- common -----

    def menu(self):
        """
        List addon menu.

        ``plugin://plugin.video.vk/``

        :rtype: None
        """
        # get menu counters from different sources
        counters = {}
        try:
            # request vk api stored function
            counters.update(self.vkapi.execute.getMenuCounters())
            # query local db
            counters.update({'searchhistory': len(self.db.table(TABLE_SEARCH_HISTORY))})
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # create menu items
        listitems = [
            (self.buildurl('/searchvideos'), xbmcgui.ListItem('{0}'.format(self.addon.getLocalizedString(30040))),
             FOLDER),
            (self.buildurl('/searchhistory'), xbmcgui.ListItem(
                '{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30041),
                                                          counters['searchhistory'], color=ALT_COLOR)), FOLDER),
            (self.buildurl('/videos'), xbmcgui.ListItem(
                '{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30042), counters['videos'],
                                                          color=ALT_COLOR)), FOLDER),
            (self.buildurl('/likedvideos'), xbmcgui.ListItem(
                '{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30043), counters['likedvideos'],
                                                          color=ALT_COLOR)), FOLDER),
            (self.buildurl('/albums'), xbmcgui.ListItem(
                '{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30044), counters['albums'],
                                                          color=ALT_COLOR)), FOLDER),
            (self.buildurl('/communities'), xbmcgui.ListItem(
                '{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30045), counters['communities'],
                                                          color=ALT_COLOR)), FOLDER),
            (self.buildurl('/likedcommunities'), xbmcgui.ListItem(
                '{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30046),
                                                          counters['likedcommunities'], color=ALT_COLOR)), FOLDER),
        ]
        # show list in kodi
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def logout(self):
        """
        Logout user.

        ``plugin://plugin.video.vk/logout``

        :rtype: None
        """
        # reset user access token, delete cookies
        self.addon.setSetting('vkuseraccesstoken', '')
        os.remove(FP_PROFILE_COOKIES)
        self.log('User logged out.')
        self.notify(self.addon.getLocalizedString(30032))

    # ----- videos -----

    def searchvideos(self):
        """
        Search videos.

        ``plugin://plugin.video.vk/searchvideos[?similarq={similarq}]``
        ``plugin://plugin.video.vk/searchvideos?q={q}[&offset={offset}]``

        :rtype: None
        """
        # get urlargs
        similarq = self.urlargs.get('similarq', '')
        q = self.urlargs.get('q', None)
        offset = int(self.urlargs.get('offset', 0))
        # if q not passed, ask user for entering a new query / editing similar one
        if not q:
            q = self.urlargs['q'] = xbmcgui.Dialog().input(self.addon.getLocalizedString(30051), defaultt=similarq)
            if not q:
                return
        # request vk api for searched videos
        searchedvideos = {}
        try:
            kwargs = {
                'extended': 1,
                'hd': 1,
                'adult': 1 if self.addon.getSetting('searchadult') == 'true' else 0,  # case sens.!
                'search_own': 1 if self.addon.getSetting('searchown') == 'true' else 0,  # case sens.!
                'sort': int(self.addon.getSetting('searchsort')),
                'q': q,
                'offset': offset,
                'count': int(self.addon.getSetting('itemsperpage')),
            }
            if self.addon.getSetting('searchduration') == '1':
                kwargs['longer'] = int(self.addon.getSetting('searchdurationmins')) * 60
            elif self.addon.getSetting('searchduration') == '2':
                kwargs['shorter'] = int(self.addon.getSetting('searchdurationmins')) * 60
            searchedvideos = self.vkapi.video.search(**kwargs)
            self.log('Searched videos: {0}'.format(searchedvideos))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # only once
        if offset == 0:  # BUG: duplicated on container refresh
            # update search history db with the last search
            lastsearch = {
                'q': q.lower(),
                'resultsCount': int(searchedvideos['count']),
                'lastUsed': datetime.datetime.now().isoformat()
            }
            self.db.table(TABLE_SEARCH_HISTORY).upsert(lastsearch, tinydb.where('q') == lastsearch['q'])
            self.log('Search history db updated: {0}'.format(lastsearch))
            # notify search results count
            self.notify(self.addon.getLocalizedString(30052).format(searchedvideos['count']))
        # build list
        self.buildlistofvideos(searchedvideos)

    def videos(self):
        """
        List videos.

        ``plugin://plugin.video.vk/videos``

        :rtype: None
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # request vk api for videos
        videos = {}
        try:
            videos = self.vkapi.video.get(
                extended=1,
                offset=offset,
                count=int(self.addon.getSetting('itemsperpage'))
            )
            self.log('Videos: {0}'.format(videos))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list
        self.buildlistofvideos(videos)

    def likedvideos(self):
        """
        List liked videos.

        ``plugin://plugin.video.vk/likedvideos``

        :rtype: None
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # request vk api for liked videos
        likedvideos = {}
        try:
            likedvideos = self.vkapi.fave.getVideos(
                extended=1,
                offset=offset,
                count=int(self.addon.getSetting('itemsperpage')),
            )
            self.log('Liked videos: {0}'.format(likedvideos))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list
        self.buildlistofvideos(likedvideos)

    def albumvideos(self):
        """
        List album videos.

        ``plugin://plugin.video.vk/albumvideos``

        :rtype: None
        """
        # get urlargs
        albumid = int(self.urlargs.get('albumid'))
        offset = int(self.urlargs.get('offset', 0))
        # request vk api for album videos
        albumvideos = {}
        try:
            albumvideos = self.vkapi.video.get(
                extended=1,
                album_id=albumid,
                offset=offset,
                count=int(self.addon.getSetting('itemsperpage')),
            )
            self.log('Album videos: {0}'.format(albumvideos))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list
        self.buildlistofvideos(albumvideos)

    def communityvideos(self):
        """
        List community videos.

        ``plugin://plugin.video.vk/communityvideos``

        :rtype: None
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        offset = int(self.urlargs.get('offset', 0))
        # request vk api for community videos
        communityvideos = {}
        try:
            communityvideos = self.vkapi.video.get(
                extended=1,
                owner_id=ownerid,
                offset=offset,
                count=int(self.addon.getSetting('itemsperpage')),
            )
            self.log('Community videos: {0}'.format(communityvideos))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list
        self.buildlistofvideos(communityvideos)

    def buildlistofvideos(self, listdata):
        """
        Build list of videos.

        ``/searchvideos, /videos, /likedvideos, /albumvideos, /communityvideos``

        :param dict listdata:
        :rtype: None
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
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30054), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/unlikevideo', {'ownerid': video['owner_id'], 'videoid': video['id']}))))
            else:
                # like video
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30053), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/likevideo', {'ownerid': video['owner_id'], 'videoid': video['id']}))))
            # add video to albums
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30055), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/addvideotoalbums', {'ownerid': video['owner_id'], 'videoid': video['id']}))))
            # search similar
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30080), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/searchvideos', {'similarq': video['title']}))))
            li.addContextMenuItems(cmi)
            # add complete video item to list
            listitems.append((self.buildurl('/playvideo', {'ownerid': video['owner_id'], 'videoid': video['id']}), li, NOT_FOLDER))
        # paginator item
        if offset + int(self.addon.getSetting('itemsperpage')) < listdata['count']:
            urlargsnext = dict(self.urlargs, offset=offset+int(self.addon.getSetting('itemsperpage')))
            listitems.append(
                (self.buildurl(self.urlpath, urlargsnext), xbmcgui.ListItem('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30050), color=ALT_COLOR)), FOLDER)
            )
        # force custom view mode for videos if enabled
        if self.addon.getSetting('forcevideoviewmode') == 'true':  # case sens!
            xbmc.executebuiltin('Container.SetViewMode({0})'.format(int(self.addon.getSetting('forcevideoviewmodeid'))))
        # show list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'videos')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def playvideo(self):
        """
        Play video.

        ``plugin://plugin.video.vk/playvideo``

        :rtype: None
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        videoid = int(self.urlargs.get('videoid'))
        oidid = '{0}_{1}'.format(ownerid, videoid)
        # request vk api for playing video  # TODO
        # video = {}
        # resolve playable streams via vk videoinfo url
        try:
            vi = self.vksession.requests_session.get(
                url='https://vk.com/al_video.php?act=show_inline&al=1&video={0}'.format(oidid),
                headers={'User-Agent': xbmc.getUserAgent()},
                # cookies sent autom.
            )
            self.log('Resolving video url: {0}'.format(vi.url))
            matches = re.findall(r'"url(\d+)":"([^"]+)"', vi.text.replace('\\', ''))
            playables = {}
            for m in matches:
                qual = int(m[0])
                playables[qual] = m[1]
            if not playables:
                raise VKAddonError()
        except VKAddonError:
            self.log('Video resolving error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30024), icon=xbmcgui.NOTIFICATION_ERROR)
            return
        # stream resolved, use max quality
        self.log('Resolved playable streams: {0}'.format(playables))
        maxqual = max(playables.keys())
        # create playable item for kodi player
        xbmcplugin.setContent(self.handle, 'videos')
        li = xbmcgui.ListItem(path=playables[maxqual])
        xbmcplugin.setResolvedUrl(self.handle, True, li)

    def likevideo(self):
        """
        Like video.

        ``plugin://plugin.video.vk/likevideo``

        :rtype: None
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        videoid = int(self.urlargs.get('videoid'))
        oidid = '{0}_{1}'.format(ownerid, videoid)
        # request vk api
        try:
            self.vkapi.likes.add(
                type='video',
                owner_id=ownerid,
                item_id=videoid,
            )
            self.log('Video liked: {0}'.format(oidid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def unlikevideo(self):
        """
        Unlike video.

        ``plugin://plugin.video.vk/unlikevideo``

        :rtype: None
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        videoid = int(self.urlargs.get('videoid'))
        oidid = '{0}_{1}'.format(ownerid, videoid)
        # request vk api
        try:
            self.vkapi.likes.delete(
                type='video',
                owner_id=ownerid,
                item_id=videoid,
            )
            self.log('Video unliked: {0}'.format(oidid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def addvideotoalbums(self):
        """
        Add video to albums.

        ``plugin://plugin.video.vk/addvideotoalbums``

        :rtype: None
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        videoid = int(self.urlargs.get('videoid'))
        oidid = '{0}_{1}'.format(ownerid, videoid)
        # request vk api
        albums = {}
        albumids = []
        try:
            # get user albums  # BUG: returns only first 100 albums
            albums = self.vkapi.video.getAlbums(
                need_system=0,
                count=100,
            )
            # get list of album ids for video
            albumids = self.vkapi.video.getAlbumsByVideo(
                owner_id=ownerid,
                video_id=videoid,
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # create dialog w current sel
        opts = []
        sel = []
        for i, album in enumerate(albums['items']):
            opts.append(album['title'])
            if album['id'] in albumids:
                sel.append(i)
        # show dialog, get new sel
        sel_new = xbmcgui.Dialog().multiselect(self.addon.getLocalizedString(30055), opts, preselect=sel)
        if sel_new is None or sel_new == sel:
            return
        # sel changed
        albumids_new = []
        for i in sel_new:
            albumids_new.append(albums['items'][i]['id'])
        # request vk api
        try:
            # remove sel album ids if any
            if len(albumids) > 0:
                self.vkapi.video.removeFromAlbum(
                    owner_id=ownerid,
                    video_id=videoid,
                    album_ids=albumids
                )
            # add new sel album ids if any
            if len(albumids_new) > 0:
                self.vkapi.video.addToAlbum(
                    owner_id=ownerid,
                    video_id=videoid,
                    album_ids=albumids_new
                )
            self.log('Video added to albums: {0}'.format(oidid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    # ----- video albums -----

    def albums(self):
        """
        List video albums.

        ``plugin://plugin.video.vk/albums``

        :rtype: None
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # workaround due api's maxperpage=100
        albumsperpage = int(self.addon.getSetting('itemsperpage')) if int(self.addon.getSetting('itemsperpage')) <= 100 else 100
        # request vk api for albums
        albums = {}
        try:
            albums = self.vkapi.video.getAlbums(
                extended=1,
                offset=offset,
                count=albumsperpage,
            )
            self.log('Albums: {0}'.format(albums))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # create list
        listitems = []
        for i, album in enumerate(albums['items']):
            # create album item
            li = xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(album['title'], int(album['count']), color=ALT_COLOR))
            # art
            if album['count'] > 0:
                li.setArt({'thumb': album['photo_320']})
            # before/after album ids for reordering
            beforeid = albums['items'][i - 1]['id'] if i > 0 else None
            afterid = albums['items'][i + 1]['id'] if i < len(albums['items']) - 1 else None
            # context menu
            li.addContextMenuItems(
                [
                    # reorder album up/down
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30061), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'beforeid': beforeid}))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30062), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'afterid': afterid}))),
                    # rename album
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30060), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/renamealbum', {'albumid': album['id']}))),
                    # delete album
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30063), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/deletealbum', {'albumid': album['id']}))),
                    # create new album
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30065), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/createalbum'))),
                ]
            )
            listitems.append(
                (self.buildurl('/albumvideos', {'albumid': album['id']}), li, FOLDER)
            )
        # paginator item, modded w albumsperpage
        if offset + albumsperpage < albums['count']:
            urlargsnext = dict(self.urlargs, offset=offset + albumsperpage)
            listitems.append(
                (self.buildurl(self.urlpath, urlargsnext), xbmcgui.ListItem('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30050), color=ALT_COLOR)), FOLDER)
            )
        # show album list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def reorderalbum(self):
        """
        Reorder album.

        ``plugin://plugin.video.vk/reorderalbum``

        :rtype: None
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
            self.vkapi.video.reorderAlbums(
                album_id=albumid,
                **reorder
            )
            self.log('Album reordered: {0}'.format(albumid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def renamealbum(self):
        """
        Rename album.

        ``plugin://plugin.video.vk/renamealbum``

        :rtype: None
        """
        # get urlargs
        albumid = int(self.urlargs.get('albumid'))
        # request vk api
        try:
            # request vk api for album
            album = self.vkapi.video.getAlbumById(
                album_id=albumid
            )
            # ask user for editing current album title
            newtitle = xbmcgui.Dialog().input(self.addon.getLocalizedString(30060), defaultt=album['title'])
            if not newtitle or newtitle == album['title']:
                return
            # request vk api for renaming album
            self.vkapi.video.editAlbum(
                album_id=albumid,
                title=newtitle,
                privacy=3  # 3=onlyme
            )
            self.log('Album renamed: {0}'.format(albumid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def deletealbum(self):
        """
        Delete album.

        ``plugin://plugin.video.vk/deletealbum``

        :rtype: None
        """
        # get urlargs
        albumid = int(self.urlargs.get('albumid'))
        # ask user for confirmation
        if not xbmcgui.Dialog().yesno(self.addon.getLocalizedString(30063), self.addon.getLocalizedString(30064)):
            return
        # request vk api
        try:
            self.vkapi.video.deletealbum()
            self.log('Album deleted: {0}'.format(albumid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def createalbum(self):
        """
        Create album.

        ``plugin://plugin.video.vk/createalbum``

        :rtype: None
        """
        # ask user for entering new album title
        albumtitle = xbmcgui.Dialog().input(self.addon.getLocalizedString(30065))
        if not albumtitle:
            return
        # request vk api
        try:
            album = self.vkapi.video.addAlbum(
                title=albumtitle,
                privacy=3,  # 3=onlyme
            )
            self.log('Album created: {0}'.format(album['album_id']))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    # ----- communities -----

    def communities(self):
        """
        List communities.

        ``plugin://plugin.video.vk/communities``

        :rtype: None
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # request vk api for communities
        communities = {}
        try:
            communities = self.vkapi.groups.get(
                extended=1,
                offset=offset,
                count=int(self.addon.getSetting('itemsperpage')),
            )
            self.log('Communities: {0}'.format(communities))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list
        self.buildlistofcommunities(communities)

    def likedcommunities(self):
        """
        List liked communities.

        ``plugin://plugin.video.vk/likedcommunities``

        :rtype: None
        """
        # get urlargs
        offset = int(self.urlargs.get('offset', 0))
        # request vk api
        likedcommunities = {}
        try:
            likedcommunities = self.vkapi.fave.getLinks(
                offset=offset,
                count=int(self.addon.getSetting('itemsperpage')),
            )
            self.log('Liked communities: {0}'.format(likedcommunities))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list
        self.buildlistofcommunities(likedcommunities)

    def buildlistofcommunities(self, listdata):
        """
        Build list of communities.

        ``/communities, /likedcommunities``

        :param dict listdata:
        :rtype: None
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
            if listtype == '/likedcommunities':
                # unlike community
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30071), color=ALT_COLOR), 'RunPlugin({0})'.format(
                    self.buildurl('/unlikecommunity', {'communityid': community['id']}))))
            else:
                # like community
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30070), color=ALT_COLOR), 'RunPlugin({0})'.format(
                    self.buildurl('/likecommunity', {'communityid': community['id']}))))
            # unfollow community
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30072), color=ALT_COLOR), 'RunPlugin({0})'.format(
                self.buildurl('/unfollowcommunity', {'communityid': community['id']}))))
            li.addContextMenuItems(cmi)
            # add complete community item to list
            listitems.append(
                (self.buildurl('/communityvideos', {'ownerid': '-{0}'.format(community['id'])}), li, FOLDER)  # negative id required!
            )
        # paginator item
        if offset + int(self.addon.getSetting('itemsperpage')) < listdata['count']:
            urlargsnext = dict(self.urlargs, offset=offset+int(self.addon.getSetting('itemsperpage')))
            listitems.append(
                (self.buildurl(self.urlpath, urlargsnext), xbmcgui.ListItem('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30050), color=ALT_COLOR)), FOLDER)
            )
        # show list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def likecommunity(self):
        """
        Like community.

        ``plugin://plugin.video.vk/likecommunity``

        :rtype: None
        """
        # get urlargs
        communityid = int(self.urlargs.get('communityid'))
        # request vk api
        try:
            self.vkapi.fave.addGroup(
                group_id=communityid
            )
            self.log('Community liked: {0}'.format(communityid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def unlikecommunity(self):
        """
        Unlike community.

        ``plugin://plugin.video.vk/unlikecommunity``

        :rtype: None
        """
        # get urlargs
        communityid = int(self.urlargs.get('communityid'))
        # request vk api
        try:
            self.vkapi.fave.removeGroup(
                group_id=communityid
            )
            self.log('Community unliked: {0}'.format(communityid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    def unfollowcommunity(self):
        """
        Unfollow community.

        ``plugin://plugin.video.vk/unfollowcommunity``

        :rtype: None
        """
        # get urlargs
        communityid = int(self.urlargs.get('communityid'))
        # request vk api
        try:
            self.vkapi.groups.leave(
                group_id=communityid
            )
            self.log('Community unfollowed: {0}'.format(communityid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # refresh content
        xbmc.executebuiltin('Container.Refresh')

    # ----- search history -----

    def searchhistory(self):
        """
        List search history.

        ``plugin://plugin.video.vk/searchhistory``

        :rtype: None
        """
        # query db for search history, empty list if no data
        searchhistory = self.db.table(TABLE_SEARCH_HISTORY).all()
        self.log('Search history: {0}'.format(searchhistory))
        # create list, sort by lastUsed reversed
        listitems = []
        for search in sorted(searchhistory, key=lambda x: x['lastUsed'], reverse=True):
            # create search item
            li = xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(search['q'], search['resultsCount'], color=ALT_COLOR))
            # create context menu
            li.addContextMenuItems(
                [
                    # delete search
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30081), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/deletesearch', {'q': search['q']}))),
                    # search similar
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30080), color=ALT_COLOR), 'RunPlugin({0})'.format(self.buildurl('/searchvideos', {'similarq': search['q']}))),
                ]
            )
            # add complete search item to list
            listitems.append(
                (self.buildurl('/searchvideos', {'q': search['q']}), li, FOLDER)
            )
        # show list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def deletesearch(self):
        """
        Delete search from search history.

        ``plugin://plugin.video.vk/deletesearch``

        :rtype: None
        """
        # get urlargs
        q = self.urlargs.get('q')
        # ask user for confirmation
        if not xbmcgui.Dialog().yesno(self.addon.getLocalizedString(30081), self.addon.getLocalizedString(30082)):
            return
        # query db
        self.db.table(TABLE_SEARCH_HISTORY).remove(tinydb.where('q') == q)
        self.log('Search deleted: {0}'.format(q))
        # refresh content
        xbmc.executebuiltin('Container.Refresh')


if __name__ == '__main__':
    VKAddon()
