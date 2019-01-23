# coding=utf-8

"""
VK (plugin.video.vk).

Kodi add-on for watching videos from VK.com social network.
:source: https://github.com/tommistolercz/plugin.video.vk
:author: TomMistolerCZ
:version: v1.1.0-devel
"""

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
FILENAME_COOKIEJAR = 'cookiejar.txt'
FILENAME_DB = 'db.json'
FOLDER, NOT_FOLDER = (True, False)
TABLE_ADDON_REQUESTS = 'addonRequests'
TABLE_SEARCH_HISTORY = 'searchHistory'
VK_API_APP_ID = '6432748'
VK_API_LANG = 'en'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_VERSION = '5.92'  # https://vk.com/dev/versions


class VKAddon(object):

    """Addon class."""

    def __init__(self):
        """
        Initialize, process addon request and dispatch routing.
        """
        # init addon
        self.addon = xbmcaddon.Addon()
        self.handle = int(sys.argv[1])
        self.sysinfo = self.getsysinfo()
        # init 3rd party components
        self.db = self.initdb()
        self.vkapi = self.initvkapi()
        # parse addon url
        self.urlbase = 'plugin://' + self.addon.getAddonInfo('id')
        self.urlpath = sys.argv[0].replace(self.urlbase, '')
        self.urlargs = {}
        if sys.argv[2].startswith('?'):
            self.urlargs = urlparse.parse_qs(sys.argv[2].lstrip('?'))
            for k, v in list(self.urlargs.items()):
                self.urlargs[k] = v.pop()
        self.url = self.buildurl(self.urlpath, self.urlargs)
        self.log('Addon url parsed: {0}'.format(self.url))
        # save addon request
        request = {
            'dt': datetime.datetime.now().isoformat(),
            'url': self.url
        }
        self.db.table(TABLE_ADDON_REQUESTS).insert(request)
        self.log('Addon request saved: {0}'.format(request))
        # dispatch addon routing
        routing = {
            # common
            '/': self.menu,
            '/logout': self.logout,
            # videos
            '/searchvideos': self.searchvideos,
            '/videos': self.videos,
            '/likedvideos': self.likedvideos,
            '/albumvideos': self.albumvideos,
            '/communityvideos': self.communityvideos,
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
            self.log('Routing dispatched. handler: {0}'.format(handler.__name__))
            handler()
        except KeyError:
            self.log('Routing error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30022), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    # ----- helpers -----

    def initdb(self):
        """
        Initialize TinyDB used for persisting addon data.

        :rtype: tinydb.TinyDB
        """
        # path to addon data file (create new autom. if doesn't exist)
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')).decode('utf-8'), FILENAME_DB)
        # create db
        db = tinydb.TinyDB(fp, indent=4, sort_keys=False)
        self.log('TinyDB initialized.')
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
                self.log('VK session created by authorizing addon using user credentials.')
                self.addon.setSetting('vkuseraccesstoken', self.vksession.access_token)
                self.savecookies(self.vksession.auth_session.cookies)
            # restore session by sending user access token
            else:
                self.vksession = vk.Session(self.addon.getSetting('vkuseraccesstoken'))
                self.log('VK session restored using user access token.')
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

    def getsysinfo(self):
        """
        Get system info.

        :rtype: dict
        """
        sysinfo = {
            'kodiversion': int(xbmc.getInfoLabel('System.BuildVersion').split(' ')[0].split('.')[0])
        }
        self.log('Sysinfo: {0}'.format(sysinfo))
        return sysinfo

    def savecookies(self, cookiejar):
        """
        Save cookiejar object to addon data file.

        :param object cookiejar:
        :rtype: None
        """
        # path to addon data file (create new autom. if doesn't exist)
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')).decode('utf-8'), FILENAME_COOKIEJAR)
        with open(fp, 'wb') as f:
            pickle.dump(cookiejar, f)
        self.log('Cookiejar data file saved.')

    def loadcookies(self):
        """
        Load cookiejar object from addon data file.

        :rtype: object
        """
        # path to addon data file (must exist since auth.)
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')).decode('utf-8'), FILENAME_COOKIEJAR)
        try:
            with open(fp, 'rb') as f:
                cookiejar = pickle.load(f)
            self.log('Cookiejar data file loaded.')
            return cookiejar
        except OSError:
            # file doesn't exist
            self.log('Addon data file error: {0}'.format(FILENAME_COOKIEJAR), level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30023), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def buildurl(self, urlpath, urlargs=None):
        """
        Build addon url (plugin://...).

        :param string urlpath: action name registered in routing
        :param dict urlargs: action parameters (default None)
        :rtype: string
        """
        url = self.urlbase + urlpath
        if urlargs is not None and len(list(urlargs)) > 0:
            url += '?' + urllib.urlencode(urlargs)
        return url

    def log(self, msg, level=xbmc.LOGDEBUG):
        """
        Log message into default Kodi.log using an uniform style.

        :param string msg:
        :param int level: (default: xbmc.LOGDEBUG)
        :rtype: None
        """
        msg = '{0}: {1}'.format(self.addon.getAddonInfo('id'), msg)
        xbmc.log(msg, level)

    def notify(self, msg, icon=xbmcgui.NOTIFICATION_INFO):
        """
        Notify user using uniform style.

        :param string msg:
        :param string icon: (default: xbmcgui.NOTIFICATION_INFO)
        :rtype: None
        """
        heading = self.addon.getAddonInfo('name')
        xbmcgui.Dialog().notification(heading, msg, icon)

    # ----- common -----

    def logout(self):
        """
        Logout user.

        :rtype: None
        """
        # reset user access token
        self.addon.setSetting('vkuseraccesstoken', '')
        # delete cookiejar data file
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')).decode('utf-8'), FILENAME_COOKIEJAR)
        if os.path.isfile(fp):
            os.remove(fp)
        self.log('User logged out by resetting access token a deleting cookiejar data file.')
        self.notify(self.addon.getLocalizedString(30032))

    def menu(self):
        """
        List addon menu.

        :rtype: None
        """
        # get counters from different sources
        try:
            counters = dict(
                # request vk api stored function
                self.vkapi.execute.getMenuCounters(),
                # query local db
                searchhistory=len(self.db.table(TABLE_SEARCH_HISTORY))
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # create menu items
        listitems = [
            (self.buildurl('/searchvideos'), xbmcgui.ListItem('{0}'.format(self.addon.getLocalizedString(30040))), FOLDER),
            (self.buildurl('/searchhistory'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30041), counters['searchhistory'], color=ALT_COLOR)), FOLDER),
            (self.buildurl('/videos'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30042), counters['videos'], color=ALT_COLOR)), FOLDER),
            (self.buildurl('/likedvideos'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30043), counters['likedvideos'], color=ALT_COLOR)), FOLDER),
            (self.buildurl('/albums'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30044), counters['albums'], color=ALT_COLOR)), FOLDER),
            (self.buildurl('/communities'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30045), counters['communities'], color=ALT_COLOR)), FOLDER),
            (self.buildurl('/likedcommunities'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30046), counters['likedcommunities'], color=ALT_COLOR)), FOLDER),
        ]
        # show list in kodi
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    # ----- videos -----

    def searchvideos(self):
        """
        Search videos.

        :rtype: None
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        # only once:
        if int(self.urlargs['offset']) == 0:
            # if not in urlargs, ask user for entering a new search query (or editing passed one)
            if 'q' not in self.urlargs:
                self.urlargs['q'] = xbmcgui.Dialog().input(self.addon.getLocalizedString(30051), defaultt=self.urlargs.get('qdef', ''))
            if not self.urlargs['q']:
                return
        # request vk api for searched videos
        try:
            params = {
                'extended': 1,
                'hd': 1,
                'q': self.urlargs['q'],
                'adult': 1 if self.addon.getSetting('searchadult') == 'true' else 0,  # case sens.!
                'search_own': 1 if self.addon.getSetting('searchown') == 'true' else 0,  # case sens.!
                'sort': int(self.addon.getSetting('searchsort')),
                'offset': int(self.urlargs['offset']),
                'count': int(self.addon.getSetting('itemsperpage')),
            }
            if self.addon.getSetting('searchduration') == '1':
                params['longer'] = int(self.addon.getSetting('searchdurationmins')) * 60
            elif self.addon.getSetting('searchduration') == '2':
                params['shorter'] = int(self.addon.getSetting('searchdurationmins')) * 60
            searchedvideos = self.vkapi.video.search(**params)
            self.log('Searched videos: {0}'.format(searchedvideos))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # only once:
        if int(self.urlargs['offset']) == 0:
            # update search history db with last search
            lastsearch = {
                'q': self.urlargs['q'].lower(),
                'resultsCount': int(searchedvideos['count']),
                'lastUsed': datetime.datetime.now().isoformat()
            }
            self.db.table(TABLE_SEARCH_HISTORY).upsert(lastsearch, tinydb.where('q') == lastsearch['q'])
            self.log('Search history db updated: {0}'.format(lastsearch))
            # notify search results count
            self.notify(self.addon.getLocalizedString(30052).format(searchedvideos['count']))
        # build list of searched videos
        self.buildlistofvideos(searchedvideos)

    def videos(self):
        """
        List videos.

        :rtype: None
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        # request vk api for videos
        try:
            videos = self.vkapi.video.get(
                extended=1,
                offset=int(self.urlargs['offset']),
                count=int(self.addon.getSetting('itemsperpage')),
            )
            self.log('Videos: {0}'.format(videos))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list of videos
        self.buildlistofvideos(videos)

    def likedvideos(self):
        """
        List liked videos.

        :rtype: None
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        # request vk api for liked videos
        try:
            likedvideos = self.vkapi.fave.getVideos(
                extended=1,
                offset=int(self.urlargs['offset']),
                count=int(self.addon.getSetting('itemsperpage')),
            )
            self.log('Liked videos: {0}'.format(likedvideos))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list of liked videos
        self.buildlistofvideos(likedvideos)

    def albumvideos(self):
        """
        List album videos.

        :rtype: None
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        # request vk api for album videos
        try:
            albumvideos = self.vkapi.video.get(
                extended=1,
                album_id=int(self.urlargs['albumid']),
                offset=int(self.urlargs['offset']),
                count=int(self.addon.getSetting('itemsperpage')),
            )
            self.log('Album videos: {0}'.format(albumvideos))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list of album videos
        self.buildlistofvideos(albumvideos)

    def communityvideos(self):
        """
        List community videos.

        :rtype: None
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        # request vk api for community videos
        try:
            communityvideos = self.vkapi.video.get(
                extended=1,
                owner_id=int(self.urlargs['ownerid']),
                offset=int(self.urlargs['offset']),
                count=int(self.addon.getSetting('itemsperpage')),
            )
            self.log('Community videos: {0}'.format(communityvideos))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list of community videos
        self.buildlistofvideos(communityvideos)

    def buildlistofvideos(self, listdata):
        """
        Build list of videos.

        :param dict listdata: videos data
        :rtype: None
        """
        # list types ['/searchvideos', '/videos', '/likedvideos', '/albumvideos', '/communityvideos']
        listtype = self.urlpath
        listitems = []
        for video in listdata['items']:
            # create video item
            li = xbmcgui.ListItem(video['title'])
            # playable
            li.setProperty('IsPlayable', 'true')
            # infolabels
            li.setInfo(
                'video',
                {
                    'title': video['title'],
                    'plot': video['description'],
                    'duration': video['duration'],
                    'date': datetime.datetime.fromtimestamp(video['date']).strftime('%d.%m.%Y')
                }
            )
            # stream infolabels
            li.addStreamInfo(
                'video',
                {
                    'width': video.get('width', None),
                    'height': video.get('height', None)
                }
            )
            # art
            if 'photo_800' in video:
                maxthumb = video['photo_800']
            elif 'photo_640' in video:
                maxthumb = video['photo_640']
            else:
                maxthumb = video['photo_320']
            li.setArt({'thumb': maxthumb})
            # context menu
            cmi = []
            if (listtype == '/likedvideos') or ('likes' in video and video['likes']['user_likes'] == 1):  # isliked
                # unlike video
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30054), color=ALT_COLOR), 'Container.Update({0})'.format(
                    self.buildurl('/unlikevideo', {'ownerid': video['owner_id'], 'videoid': video['id']}))))
            else:
                # like video
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30053), color=ALT_COLOR), 'Container.Update({0})'.format(
                    self.buildurl('/likevideo', {'ownerid': video['owner_id'], 'videoid': video['id']}))))
            # add video to albums
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30055), color=ALT_COLOR), 'Container.Update({0})'.format(
                self.buildurl('/addvideotoalbums', {'ownerid': video['owner_id'], 'videoid': video['id']}))))
            # search similar
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30080), color=ALT_COLOR), 'Container.Update({0})'.format(
                self.buildurl('/searchvideos', {'qdef': video['title']}))))
            li.addContextMenuItems(cmi)
            listitems.append(
                (self.buildurl('/playvideo', {'ownerid': video['owner_id'], 'videoid': video['id']}), li, NOT_FOLDER)
            )
        # paginator item
        if int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')) < listdata['count']:
            urlargsnext = dict(self.urlargs, offset=int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')))
            listitems.append(
                (self.buildurl(self.urlpath, urlargsnext), xbmcgui.ListItem('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30050), color=ALT_COLOR)), FOLDER)
            )
        # force custom view mode for videos, if enabled
        if self.addon.getSetting('forcevideoviewmode') == 'true':  # case sens!
            xbmc.executebuiltin('Container.SetViewMode({0})'.format(int(self.addon.getSetting('forcevideoviewmodeid'))))
        # show video list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'videos')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def playvideo(self):
        """
        Play video.

        :rtype: None
        """
        # get urlargs
        ownerid = int(self.urlargs.get('ownerid'))
        videoid = int(self.urlargs.get('videoid'))
        oidid = '{0}_{1}'.format(ownerid, videoid)
        # resolve playable streams via vk videoinfo api (hack)
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
        # resolved, use max quality stream
        self.log('Resolved playable streams: {0}'.format(playables))
        maxqual = max(playables.keys())
        # create playable item for kodi player
        xbmcplugin.setContent(self.handle, 'videos')
        li = xbmcgui.ListItem(path=playables[maxqual])
        xbmcplugin.setResolvedUrl(self.handle, True, li)

    def likevideo(self):
        """
        Like video.

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

    def unlikevideo(self):
        """
        Unlike video.

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

    def addvideotoalbums(self):
        """
        Add video to albums.

        :rtype: None
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
                count=100,  # todo: pageable multiselect dialog for adding video to albums?
            )
            # get album ids for video
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
            # remove sel album ids from video (if any)
            if len(albumids) > 0:
                self.vkapi.video.removeFromAlbum(
                    owner_id=ownerid,
                    video_id=videoid,
                    album_ids=albumids
                )
            # add new sel album ids for video (if any)
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

    # ----- video albums -----

    def albums(self):
        """
        List video albums.

        :rtype: None
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        # workaround due api's max=100
        albumsperpage = int(self.addon.getSetting('itemsperpage')) if int(self.addon.getSetting('itemsperpage')) <= 100 else 100
        # request vk api for albums
        try:
            albums = self.vkapi.video.getAlbums(
                extended=1,
                offset=int(self.urlargs['offset']),
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
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30061), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'beforeid': beforeid}))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30062), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'afterid': afterid}))),
                    # rename album
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30060), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/renamealbum', {'albumid': album['id']}))),
                    # delete album
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30063), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/deletealbum', {'albumid': album['id']}))),
                    # create new album
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30065), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/createalbum'))),
                ]
            )
            listitems.append(
                (self.buildurl('/albumvideos', {'albumid': album['id']}), li, FOLDER)
            )
        # paginator item, modded w albumsperpage
        if int(self.urlargs['offset']) + albumsperpage < albums['count']:
            urlargsnext = dict(self.urlargs, offset=int(self.urlargs['offset']) + albumsperpage)
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

    def renamealbum(self):
        """
        Rename album.

        :rtype: None
        """
        # get urlargs
        albumid = int(self.urlargs.get('albumid'))
        # request vk api
        try:
            # request for album data
            album = self.vkapi.video.getAlbumById(
                album_id=albumid
            )
            # ask user for editing current title
            newtitle = xbmcgui.Dialog().input(self.addon.getLocalizedString(30060), defaultt=album['title'])
            if not newtitle or newtitle == album['title']:
                return
            # title has changed
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

    def deletealbum(self):
        """
        Delete album.

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

    def createalbum(self):
        """
        Create album.

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

    # ----- communities -----

    def communities(self):
        """
        List communities.

        :rtype: None
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        # request vk api for communities data
        try:
            communities = self.vkapi.groups.get(
                extended=1,
                offset=int(self.urlargs['offset']),
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

        :rtype: None
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        # request vk api
        try:
            likedcommunities = self.vkapi.fave.getLinks(
                offset=int(self.urlargs['offset']),
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

        :param dict listdata: communities data
        :rtype: None
        """
        # list types ['/communities', '/likedcommunities']
        listtype = self.urlpath
        listitems = []
        _namekey = 'title' if listtype == '/likedcommunities' else 'name'
        for community in listdata['items']:
            if listtype == '/likedcommunities':
                community['id'] = community['id'].split('_')[2]
            # create community item
            li = xbmcgui.ListItem(community[_namekey])
            # art
            li.setArt({'thumb': community['photo_200']})
            # context menu
            cmi = []
            if listtype == '/likedcommunities':
                # unlike community
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30071), color=ALT_COLOR), 'Container.Update({0})'.format(
                    self.buildurl('/unlikecommunity', {'communityid': community['id']}))))
            else:
                # like community
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30070), color=ALT_COLOR), 'Container.Update({0})'.format(
                    self.buildurl('/likecommunity', {'communityid': community['id']}))))
            # unfollor community
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30072), color=ALT_COLOR), 'Container.Update({0})'.format(
                self.buildurl('/unfollowcommunity', {'communityid': community['id']}))))
            li.addContextMenuItems(cmi)
            listitems.append(
                (self.buildurl('/communityvideos', {'ownerid': '-{0}'.format(community['id'])}), li, FOLDER)  # negative id required
            )
        # paginator item
        if int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')) < listdata['count']:
            urlargsnext = dict(self.urlargs, offset=int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')))
            listitems.append(
                (self.buildurl(self.urlpath, urlargsnext), xbmcgui.ListItem('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30050), color=ALT_COLOR)), FOLDER)
            )
        # show community list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def likecommunity(self):
        """
        Like community.

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

    def unlikecommunity(self):
        """
        Unlike community.

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

    def unfollowcommunity(self):
        """
        Unfollow community.

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

    # ----- search history -----

    def searchhistory(self):
        """
        List search history.

        :rtype: None
        """
        # retrieve search history data from db, or empty list if no data
        searchhistory = self.db.table(TABLE_SEARCH_HISTORY).all()
        self.log('Search history: {0}'.format(searchhistory))
        # create list sorted by last used item reversed
        listitems = []
        for search in sorted(searchhistory, key=lambda x: x['lastUsed'], reverse=True):
            # create search item
            li = xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(search['q'], search['resultsCount'], color=ALT_COLOR))
            # context menu
            li.addContextMenuItems(
                [
                    # delete search
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30081), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/deletesearch', {'q': search['q']}))),
                    # search similar
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30080), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/searchvideos', {'qdef': search['q']}))),
                ]
            )
            listitems.append(
                (self.buildurl('/searchvideos', {'q': search['q']}), li, FOLDER)
            )
        # show search history list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def deletesearch(self):
        """
        Delete search from search history.

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


class VKAddonError(Exception):

    """Exception type for addon errors."""

    pass


if __name__ == '__main__':
    VKAddon()
