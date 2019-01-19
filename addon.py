#!/usr/bin/env python
# coding=utf-8

"""
VK for Kodi (plugin.video.vk)
v1.1.0
https://github.com/tommistolercz/plugin.video.vk
"""

import datetime
import os
import pickle
import re
import sys
import urllib
try:
    import urlparse  # PY2
except ImportError:
    import urllib.parse as urlparse  # PY3

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

sys.path.append(os.path.join(xbmc.translatePath(xbmcaddon.Addon().getAddonInfo('path')).decode('utf-8'), 'resources', 'lib'))
import tinydb  # noqa: E402
import vk  # noqa: E402


FOLDER, NOT_FOLDER = (True, False)
ALT_COLOR = 'blue'
VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_VERSION = '5.92'  # https://vk.com/dev/versions
VK_API_LANG = 'en'
ADDON_DATA_FILE_COOKIES = 'cookiejar.txt'
ADDON_DATA_FILE_DB = 'db.json'
TBL_ADDON_REQUESTS = 'addonRequests'
TBL_SEARCH_HISTORY = 'searchHistory'


class VKAddon():
    """
    Addon class.
    """
    def __init__(self):
        """
        Initialize addon and dispatch addon routing.
        """
        # init addon/components
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
        self.log('Addon request url parsed: {0}'.format(self.url))
        # track addon requests for usage stats (future feature)
        request = {
            'dt': datetime.datetime.now().isoformat(),
            'url': self.url,
        }
        self.db.table(TBL_ADDON_REQUESTS).insert(request)
        # dispatch addon routing
        routing = {
            # common
            '/': self.listmainmenu,
            '/logout': self.logout,
            # videos
            '/searchvideos': self.listsearchedvideos,
            '/videos': self.listvideos,
            '/likedvideos': self.listlikedvideos,
            '/albumvideos': self.listalbumvideos,
            '/communityvideos': self.listcommunityvideos,
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
            # search history
            '/searchhistory': self.listsearchhistory,
            '/deletesearch': self.deletesearch,
        }
        try:
            handler = routing[self.urlpath]
            self.log('Routing dispatched using handler: {0}'.format(handler.__name__))
            handler()
        except KeyError:
            self.log('Routing error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30022), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    # ----- helpers -----

    def initdb(self):
        """
        Init TinyDB object.
        :returns: obj
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')).decode('utf-8'), ADDON_DATA_FILE_DB)
        db = tinydb.TinyDB(fp, indent=4, sort_keys=False)
        return db

    def initvkapi(self):
        """
        Init VK API object.
        :returns: obj
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
                self.savecookiejar(self.vksession.auth_session.cookies)
            # restore session by sending user access token
            else:
                self.vksession = vk.Session(self.addon.getSetting('vkuseraccesstoken'))
                self.log('VK session restored using user access token.')
                self.vksession.requests_session.cookies = self.loadcookiejar()
        except vk.exceptions.VkAuthError:
            self.log('VK authorization error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30020), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        try:
            # create api
            vkapi = vk.API(self.vksession, v=VK_API_VERSION, lang=VK_API_LANG)
            vkapi.stats.trackVisitor()
            self.log('VK API object created.')
            return vkapi
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def buildurl(self, urlpath, urlargs=None):
        """
        Build addon url.
        :param urlpath: string; action name
        :param urlargs: dict; action params, default=None
        :returns: string; addon url (plugin://...)
        """
        url = self.urlbase + urlpath
        if urlargs is not None and len(list(urlargs)) > 0:
            url += '?' + urllib.urlencode(urlargs)
        return url

    def buildoidid(self, ownerid, id):
        """
        Build a full video identifier, aka oidid.
        :param ownerid: int; video owner id
        :param id: int; video id
        :returns: string; video oidid
        """
        return '{0}_{1}'.format(ownerid, id)

    def loadcookiejar(self):
        """
        Load cookiejar object from addon data file.
        :returns: obj
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')).decode('utf-8'), ADDON_DATA_FILE_COOKIES)
        try:
            with open(fp, 'rb') as f:
                cookiejar = pickle.load(f)
            self.log('Cookiejar data file loaded: {0}'.format(cookiejar))
            return cookiejar
        except OSError:
            # file not exists
            self.log('Addon data file error: {0}'.format(ADDON_DATA_FILE_COOKIES), level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30023), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def savecookiejar(self, cookiejar):
        """
        Save cookiejar object into addon data file.
        :param cookiejar: obj
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')).decode('utf-8'), ADDON_DATA_FILE_COOKIES)
        with open(fp, 'wb') as f:
            pickle.dump(cookiejar, f)
        self.log('Cookiejar data file saved: {0}'.format(cookiejar))

    def log(self, msg, level=xbmc.LOGDEBUG):
        """
        Log message into default Kodi.log using an uniform style.
        :param msg: string
        :param level: xbmc.LOGDEBUG (default)
        """
        msg = '{0}: {1}'.format(self.addon.getAddonInfo('id'), msg)
        xbmc.log(msg, level)

    def notify(self, msg, icon=xbmcgui.NOTIFICATION_INFO):
        """
        Notify user using uniform style.
        :param msg: string
        :param icon: int; xbmcgui.NOTIFICATION_INFO (default)
        """
        heading = self.addon.getAddonInfo('name')
        xbmcgui.Dialog().notification(heading, msg, icon)

    # ----- common -----

    def listmainmenu(self):
        """
        List main menu.
        """
        # request vk api for menu counters (stored function)
        try:
            counters = self.vkapi.execute.getMenuCounters()
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # count search history
        counters['searchhistory'] = len(self.db.table(TBL_SEARCH_HISTORY))
        # create main menu list items
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

    def logout(self):
        """
        Logout user.
        """
        # reset user access token
        self.addon.setSetting('vkuseraccesstoken', '')
        # delete cookiejar data file
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')).decode('utf-8'), ADDON_DATA_FILE_COOKIES)
        if os.path.isfile(fp):
            os.remove(fp)
        self.log('User logged out by resetting access token and deleting cookiejar data file.')
        self.notify(self.addon.getLocalizedString(30032))

    # ----- videos -----

    def listsearchedvideos(self):
        """
        List searched videos.
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
            self.db.table(TBL_SEARCH_HISTORY).upsert(lastsearch, tinydb.where('q') == lastsearch['q'])
            self.log('Search history db updated: {0}'.format(lastsearch))
            # notify search results count
            self.notify(self.addon.getLocalizedString(30052).format(searchedvideos['count']))
        # build list of searched videos
        self.buildlistofvideos(searchedvideos)

    def listvideos(self):
        """
        List user's videos.
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

    def listlikedvideos(self):
        """
        List user's liked videos.
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

    def listalbumvideos(self):
        """
        List user's album videos.
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

    def listcommunityvideos(self):
        """
        List user's community videos.
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
        :param listdata: dict
        """
        # listtypes: /searchvideos, /videos, /likedvideos, /albumvideos, /communityvideos
        listtype = self.urlpath
        # create list items for videos
        listitems = []
        for video in listdata['items']:
            li = xbmcgui.ListItem(video['title'])
            li.setProperty('IsPlayable', 'true')
            li.setInfo(
                type='video',
                infoLabels={
                    'title': video['title'],
                    'plot': video['description'],
                    'duration': video['duration'],
                    'date': datetime.datetime.fromtimestamp(video['date']).strftime('%d.%m.%Y'),
                }
            )
            if 'width' in video and 'height' in video:
                li.addStreamInfo(
                    'video',
                    {
                        'width': int(video['width']),
                        'height': int(video['height']),
                    }
                )
            if 'photo_800' in video:
                maxthumb = video['photo_800']
            elif 'photo_640' in video:
                maxthumb = video['photo_640']
            else:
                maxthumb = video['photo_320']
            li.setArt({'thumb': maxthumb})
            # create contextmenu items for each video
            cmi = []
            if (listtype == '/likedvideos') or ('likes' in video and video['likes']['user_likes'] == 1):  # isliked
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30054), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/unlikevideo', {'ownerid': video['owner_id'], 'id': video['id']}))))
            else:
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30053), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/likevideo', {'ownerid': video['owner_id'], 'id': video['id']}))))
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30055), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/addvideotoalbums', {'ownerid': video['owner_id'], 'id': video['id']}))))
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30080), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/searchvideos', {'qdef': video['title']}))))
            li.addContextMenuItems(cmi)
            listitems.append(
                (self.buildurl('/playvideo', {'ownerid': video['owner_id'], 'id': video['id']}), li, NOT_FOLDER)
            )
        # paginator item
        if int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')) < listdata['count']:
            urlargsnext = dict(self.urlargs, offset=int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')))
            listitems.append(
                (self.buildurl(self.urlpath, urlargsnext), xbmcgui.ListItem('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30050), color=ALT_COLOR)), FOLDER)
            )
        # if enabled, force custom view mode for videos
        if self.addon.getSetting('forcevideoviewmode') == 'true':
            xbmc.executebuiltin('Container.SetViewMode({0})'.format(int(self.addon.getSetting('forcevideoviewmodeid'))))
        # show video list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'videos')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def playvideo(self):
        """
        Play video.
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        # resolve playable streams via vk videoinfo api (hack)
        try:
            vi = self.vksession.requests_session.get(
                url='https://vk.com/al_video.php?act=show_inline&al=1&video={0}'.format(oidid),
                headers={'User-Agent': xbmc.getUserAgent()},
                # +logged user's cookies sent autom.
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
        # create item for kodi player (using max quality stream)
        self.log('Resolved playable streams: {0}'.format(playables))
        maxqual = max(playables.keys())
        self.log('Playing started: {0}'.format(playables[maxqual]))
        xbmcplugin.setContent(self.handle, 'videos')
        li = xbmcgui.ListItem(path=playables[maxqual])
        xbmcplugin.setResolvedUrl(self.handle, True, li)

    def likevideo(self):
        """
        Like video.
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        try:
            self.vkapi.likes.add(
                type='video',
                owner_id=int(self.urlargs['ownerid']),
                item_id=int(self.urlargs['id']),
            )
            self.log('Video liked: {0}'.format(oidid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def unlikevideo(self):
        """
        Unlike video.
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        try:
            self.vkapi.likes.delete(
                type='video',
                owner_id=int(self.urlargs['ownerid']),
                item_id=int(self.urlargs['id']),
            )
            self.log('Video unliked: {0}'.format(oidid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def addvideotoalbums(self):
        """
        Add video to albums.
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        try:
            # get user albums
            albums = self.vkapi.video.getAlbums(
                need_system=0,
                count=100  # todo: pageable multiselect dialog for adding video to albums?
            )
            # get current album ids for video
            albumidspre = self.vkapi.video.getAlbumsByVideo(
                owner_id=int(self.urlargs['ownerid']),
                video_id=int(self.urlargs['id'])
            )
            # create options/preselected
            options = []
            optionspre = []
            for i, album in enumerate(albums['items']):
                options.append(album['title'])
                if album['id'] in albumidspre:
                    optionspre.append(i)
            # show dialog, get selected opts
            optionssel = xbmcgui.Dialog().multiselect(self.addon.getLocalizedString(30055), options, preselect=optionspre)
            if optionssel is not None and optionssel != optionspre:
                # get selected album ids
                albumidssel = []
                for i in optionssel:
                    albumidssel.append(albums['items'][i]['id'])
                # if any, remove current album ids for video
                if len(albumidspre) > 0:
                    self.vkapi.video.removeFromAlbum(
                        owner_id=int(self.urlargs['ownerid']),
                        video_id=int(self.urlargs['id']),
                        album_ids=albumidspre
                    )
                # if any, add selected album ids for video
                if len(albumidssel) > 0:
                    self.vkapi.video.addToAlbum(
                        owner_id=int(self.urlargs['ownerid']),
                        video_id=int(self.urlargs['id']),
                        album_ids=albumidssel
                    )
                self.log('Video added to albums: {0} {1}=>{2}'.format(oidid, albumidspre, albumidssel))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    # ----- video albums -----

    def listalbums(self):
        """
        List user's video albums.
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
        # create list items for albums
        listitems = []
        for i, album in enumerate(albums['items']):
            li = xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(album['title'], int(album['count']), color=ALT_COLOR))
            if album['count'] > 0:
                li.setArt({'thumb': album['photo_320']})
            # before/after album ids for reordering
            beforeid = albums['items'][i - 1]['id'] if i > 0 else None
            afterid = albums['items'][i + 1]['id'] if i < len(albums['items']) - 1 else None
            li.addContextMenuItems(
                [
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30060), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/renamealbum', {'albumid': album['id']}))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30061), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'beforeid': beforeid}))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30062), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'afterid': afterid}))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30063), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/deletealbum', {'albumid': album['id']}))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30065), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/createalbum'))),
                ]
            )
            listitems.append(
                (self.buildurl('/albumvideos', {'albumid': album['id']}), li, FOLDER)
            )
        # paginator item (modded w albumsperpage)
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

    def renamealbum(self):
        """
        Rename album.
        """
        try:
            album = self.vkapi.video.getAlbumById(
                album_id=int(self.urlargs['albumid'])
            )
            albumtitle = xbmcgui.Dialog().input(self.addon.getLocalizedString(30060), defaultt=album['title'])
            if not albumtitle:
                return
            self.vkapi.video.editAlbum(
                album_id=int(self.urlargs['albumid']),
                title=albumtitle,
                privacy=3  # 3=onlyme
            )
            self.log('Album renamed: {0}'.format(self.urlargs['albumid']))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def reorderalbum(self):
        """
        Reorder album (move up/down).
        """
        try:
            params = {'album_id': int(self.urlargs['albumid'])}
            if 'beforeid' in self.urlargs:
                params['before'] = int(self.urlargs['beforeid'])
            elif 'afterid' in self.urlargs:
                params['after'] = int(self.urlargs['afterid'])
            self.vkapi.video.reorderAlbums(**params)
            self.log('Album reordered: {0}'.format(self.urlargs['albumid']))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def deletealbum(self):
        """
        Delete album.
        """
        # get urlargs
        albumid = int(self.urlargs.get('albumid'))
        # ask user for confirmation
        if not xbmcgui.Dialog().yesno(self.addon.getLocalizedString(30063), self.addon.getLocalizedString(30064)):
            return
        # request vk api
        try:
            self.vkapi.video.deleteAlbum(
                album_id=albumid,
            )
            self.log('Album deleted: {0}'.format(albumid))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def createalbum(self):
        """
        Create album.
        """
        # ask user for entering a new album title
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

    def listcommunities(self):
        """
        List user's communities.
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
        # build list of communities
        self.buildlistofcommunities(communities)

    def listlikedcommunities(self):
        """
        List user's liked communities.
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        # request vk api for liked communities data
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
        # build list of liked communities
        self.buildlistofcommunities(likedcommunities)

    def buildlistofcommunities(self, listdata):
        """
        Build list of communities.
        :param listdata: dict
        """
        # listtypes: /communities, /likedcommunities
        listtype = self.urlpath
        # create list items
        listitems = []
        _namekey = 'title' if listtype == '/likedcommunities' else 'name'
        for community in listdata['items']:
            if listtype == '/likedcommunities':
                community['id'] = community['id'].split('_')[2]
            li = xbmcgui.ListItem(community[_namekey])
            li.setArt({'thumb': community['photo_200']})
            # cm actions
            cmi = []
            if listtype == '/likedcommunities':
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30071), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/unlikecommunity', {'communityid': community['id']}))))
            else:
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30070), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/likecommunity', {'communityid': community['id']}))))
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30072), color=ALT_COLOR), 'Container.Update({0})'.format(self.buildurl('/unfollowcommunity', {'communityid': community['id']}))))
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
        """
        try:
            self.vkapi.fave.addGroup(
                group_id=int(self.urlargs['communityid'])
            )
            self.log('Community liked: {0}'.format(self.urlargs['communityid']))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def unlikecommunity(self):
        """
        Unlike community.
        """
        try:
            self.vkapi.fave.removeGroup(
                group_id=int(self.urlargs['communityid'])
            )
            self.log('Community unliked: {0}'.format(self.urlargs['communityid']))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def unfollowcommunity(self):
        """
        Unfollow community.
        """
        try:
            self.vkapi.groups.leave(
                group_id=int(self.urlargs['communityid'])
            )
            self.log('Community unfollowed: {0}'.format(self.urlargs['communityid']))
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30021), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    # ----- search history -----

    def listsearchhistory(self):
        """
        List search history.
        """
        # retrieve search history from db (empty list if no data)
        searchhistory = self.db.table(TBL_SEARCH_HISTORY).all()
        self.log('Search history: {0}'.format(searchhistory))
        # create search history list items sorted by last used reversed
        listitems = []
        for search in sorted(searchhistory, key=lambda x: x['lastUsed'], reverse=True):
            li = xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(search['q'], search['resultsCount'], color=ALT_COLOR))
            # search item context menu
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
        """
        # get urlargs
        q = self.urlargs.get('q')
        # ask user for confirmation
        if not xbmcgui.Dialog().yesno(self.addon.getLocalizedString(30081), self.addon.getLocalizedString(30082)):
            return
        # query db
        self.db.table(TBL_SEARCH_HISTORY).remove(
            tinydb.where('q') == q
        )
        self.log('Search deleted: {0}'.format(q))


class VKAddonError(Exception):
    """
    Exception type for addon errors.
    """
    def __init__(self, msg=None):
        self.msg = msg


if __name__ == '__main__':
    # run addon
    VKAddon()
