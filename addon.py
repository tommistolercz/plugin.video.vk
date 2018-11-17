#!/usr/bin/env python
# coding=utf-8

"""
VK for Kodi (plugin.video.vk)
v1.1.0
https://github.com/tommistolercz/plugin.video.vk
"""


import datetime
import json
import os
import pickle
import re
import sys
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


PY2, PY3 = ((sys.version_info[0] == 2), (sys.version_info[0] == 3))  # not used
FOLDER, NOT_FOLDER = (True, False)

VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_VERSION = '5.87'
VK_API_LANG = 'ru'
VK_VIDEOINFO_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0.1 Safari/605.1.15'
ADDON_DATA_FILE_COOKIEJAR = '.cookiejar'
ADDON_DATA_FILE_SEARCH_HISTORY = 'searchhistory.json'
COLOR_ALT = 'blue'


class VKAddon():
    """
    Addon class.
    """
    def __init__(self):
        """
        Initialize addon and manage all that controlling stuff at runtime ;-)
        """
        self.addon = xbmcaddon.Addon()
        self.handle = int(sys.argv[1])
        self.vkapi = self.createvkapi()
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
        # dispatch addon routing by calling a handler for respective user action
        self.routing = {
            '/': self.listmainmenu,
            '/addalbum': self.addalbum,
            '/albums': self.listalbums,
            '/albumvideos': self.listalbumvideos,
            '/communities': self.listcommunities,
            '/communityvideos': self.listcommunityvideos,
            '/deletealbum': self.deletealbum,
            '/deletesearch': self.deletesearch,
            '/leavecommunity': self.leavecommunity,
            '/likecommunity': self.likecommunity,
            '/likevideo': self.likevideo,
            '/likedcommunities': self.listlikedcommunities,
            '/likedvideos': self.listlikedvideos,
            '/logout': self.logout,
            '/play': self.playvideo,
            '/renamealbum': self.renamealbum,
            '/reorderalbum': self.reorderalbum,
            '/search': self.searchvideos,
            '/searchhistory': self.listsearchhistory,
            '/searchsimilar': self.searchvideos,  # reuse!
            '/setalbumsforvideo': self.setalbumsforvideo,
            '/stats': self.liststats,
            '/unlikecommunity': self.unlikecommunity,
            '/unlikevideo': self.unlikevideo,
            '/videos': self.listvideos,
        }
        try:
            handler = self.routing[self.urlpath]
            self.log('Routing dispatched by calling handler: {0}'.format(handler.__name__))
            handler()
        except KeyError:
            self.log('Routing error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30202), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def buildoidid(self, ownerid, id):
        """
        Build a full video identifier, aka oidid.
        (helper)
        :param ownerid: int; video owner id
        :param id: int; video id
        :returns: string; video oidid
        """
        return '{0}_{1}'.format(ownerid, id)

    def buildurl(self, urlpath, urlargs=None):
        """
        Build addon url.
        (helper)
        :param urlpath: string; action name
        :param urlargs: dict; action params, default=None
        :returns: string; addon url (plugin://...)
        """
        url = self.urlbase + urlpath
        if urlargs is not None and len(list(urlargs)) > 0:
            url += '?' + urllib.urlencode(urlargs)
        return url

    def createvkapi(self):
        """
        Create VK API object.
        (helper)
        :returns: obj
        """
        try:
            # obtain new user access token by authorizing addon using user credentials
            if self.addon.getSetting('vkuseraccesstoken') == '':
                credentials = {
                    'login': xbmcgui.Dialog().input(self.addon.getLocalizedString(30020)),
                    'password': xbmcgui.Dialog().input(self.addon.getLocalizedString(30021), option=xbmcgui.ALPHANUM_HIDE_INPUT)
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
            self.notify(self.addon.getLocalizedString(30200), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        try:
            # create api
            vkapi = vk.API(self.vksession, v=VK_API_VERSION, lang=VK_API_LANG)
            istracked = vkapi.stats.trackVisitor()  # noqa
            self.log('VK API object created.')
            return vkapi
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def loadcookiejar(self):
        """
        Load cookiejar object from addon data file.
        (helper)
        :returns: obj
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_COOKIEJAR)
        try:
            with open(fp, 'rb') as f:
                cookiejar = pickle.load(f)
            self.log('Cookiejar data file loaded: {0}'.format(cookiejar))
            return cookiejar
        except OSError:
            # file not exists
            self.log('Missing data file: {0}'.format(ADDON_DATA_FILE_COOKIEJAR), level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30203), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def loadsearchhistory(self):
        """
        load search history from addon data file.
        (helper)
        :returns: dict
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_SEARCH_HISTORY)
        try:
            with open(fp) as f:
                searchhistory = json.load(f)
        except OSError:  # file not exists
            searchhistory = {u'count': 0, u'items': []}
        self.log('Search history data file loaded: {0}'.format(searchhistory))
        return searchhistory

    def log(self, msg, level=xbmc.LOGDEBUG):
        """
        Log message into default Kodi.log using an uniform style.
        (helper)
        :param msg: string
        :param level: xbmc.LOGDEBUG (default)
        """
        msg = '{0}: {1}'.format(self.addon.getAddonInfo('id'), msg)
        xbmc.log(msg, level)

    def notify(self, msg, icon=xbmcgui.NOTIFICATION_INFO):
        """
        Notify user using uniform style.
        (helper)
        :param msg: string
        :param icon: int; xbmcgui.NOTIFICATION_INFO (default)
        """
        heading = '{0}'.format(self.addon.getAddonInfo('name'))
        xbmcgui.Dialog().notification(heading, msg, icon)

    def savecookiejar(self, cookiejar):
        """
        Save cookiejar object into addon data file.
        (helper)
        :param cookiejar: obj
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_COOKIEJAR)
        with open(fp, 'wb') as f:
            pickle.dump(cookiejar, f)
        self.log('Cookiejar data file saved: {0}'.format(cookiejar))

    def savesearchhistory(self, searchhistory):
        """
        Save search history into addon data file.
        (helper)
        :param searchhistory: dict
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_SEARCH_HISTORY)
        with open(fp, 'w') as f:
            json.dump(searchhistory, f, indent=4)
        self.log('Search history data file saved: {0}'.format(searchhistory))

    def updatesearchhistory(self, search):
        """
        Append search to search history if query is unique, else re-append updated one.
        (helper)
        :param search: dict(query=string, resultsCount=int)
        """
        searchhistory = self.loadsearchhistory()
        existing = None
        for i, item in enumerate(searchhistory['items']):
            if item['query'].lower() == search['query'].lower():
                existing = searchhistory['items'].pop(i)
                break
        search['usesCount'] = 1 if not existing else existing['usesCount'] + 1
        search['lastUsed'] = datetime.datetime.now().isoformat()
        searchhistory['items'].append(search)
        self.log('Search history updated: {0}'.format(search))
        if not existing:
            searchhistory['count'] += 1
        self.savesearchhistory(searchhistory)

    # ===== Action handlers =====

    def addalbum(self):
        """
        Add new album.
        (contextmenu action handler)
        """
        albumtitle = xbmcgui.Dialog().input(self.addon.getLocalizedString(30110))
        if not albumtitle:
            return
        try:
            album = self.vkapi.video.addAlbum(
                title=albumtitle,
                privacy=3,  # 3=onlyme
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        self.log('Album added: {0}'.format(album['album_id']))
        self.notify(self.addon.getLocalizedString(30111))

    def buildlistofcommunities(self, listdata):
        """
        Build list of communities.
        (handler helper)
        :param listdata: dict
        """
        # list type: /communities, /likedcommunities
        listtype = self.urlpath
        # create list items for communities
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
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30054), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/unlikecommunity', {'communityid': community['id']}))))
            else:
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30055), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/likecommunity', {'communityid': community['id']}))))
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30056), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/leavecommunity', {'communityid': community['id']}))))
            li.addContextMenuItems(cmi)
            listitems.append(
                (self.buildurl('/communityvideos', {'ownerid': '-{0}'.format(community['id'])}), li, FOLDER)  # negative id required
            )
        # paginator item
        if int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')) < listdata['count']:
            self.urlargs['offset'] = int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage'))
            listitems.append(
                (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30190), color=COLOR_ALT)), FOLDER)
            )
        # show community list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def buildlistofvideos(self, listdata):
        """
        Build list of videos.
        (handler helper)
        :param listdata: dict
        """
        # list type: /albumvideos, /communityvideos, /likedvideos, /search, /searchsimilar, /videos
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
            if 'photo_800' in video:
                maxthumb = video['photo_800']
            elif 'photo_640' in video:
                maxthumb = video['photo_640']
            else:
                maxthumb = video['photo_320']
            li.setArt({'thumb': maxthumb})
            # cm actions
            cmi = []
            if (listtype == '/likedvideos') or ('likes' in video and video['likes']['user_likes'] == 1):  # isliked
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30050), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/unlikevideo', {'ownerid': video['owner_id'], 'id': video['id']}))))
            else:
                cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30051), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/likevideo', {'ownerid': video['owner_id'], 'id': video['id']}))))
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30052), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/setalbumsforvideo', {'ownerid': video['owner_id'], 'id': video['id']}))))
            cmi.append(('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30053), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/searchsimilar', {'qdef': video['title']}))))
            li.addContextMenuItems(cmi)
            listitems.append(
                (self.buildurl('/play', {'ownerid': video['owner_id'], 'id': video['id']}), li, NOT_FOLDER)
            )
        # paginator item
        if int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')) < listdata['count']:
            self.urlargs['offset'] = int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage'))
            listitems.append(
                (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30190), color=COLOR_ALT)), FOLDER)
            )
        # if enabled, force custom view mode for videos
        if self.addon.getSetting('forcevideoviewmode') == 'true':
            xbmc.executebuiltin('Container.SetViewMode({0})'.format(int(self.addon.getSetting('forcevideoviewmodeid'))))
        # show video list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'videos')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def deletealbum(self):
        """
        Delete album.
        (contextmenu action handler)
        """
        if not xbmcgui.Dialog().yesno(self.addon.getLocalizedString(30112), self.addon.getLocalizedString(30113)):
            return
        try:
            self.vkapi.video.deleteAlbum(
                album_id=int(self.urlargs['albumid']),
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        self.log('Album deleted: {0}'.format(self.urlargs['albumid']))
        self.notify(self.addon.getLocalizedString(30114))

    def deletesearch(self):
        """
        Delete search from history.
        (contextmenu action handler)
        """
        searchhistory = self.loadsearchhistory()
        for i, item in enumerate(searchhistory['items']):
            if item['query'] == self.urlargs['q']:
                searchhistory['items'].pop(i)
                break
        searchhistory['count'] -= 1
        self.savesearchhistory(searchhistory)
        self.log('Search deleted: {0}'.format(self.urlargs['q']))
        self.notify(self.addon.getLocalizedString(30092))

    def leavecommunity(self):
        """
        Leave community.
        (contextmenu action handler)
        """
        try:
            self.vkapi.groups.leave(
                group_id=int(self.urlargs['communityid'])
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        self.log('Community was left: {0}'.format(self.urlargs['communityid']))
        self.notify(self.addon.getLocalizedString(30140))

    def likecommunity(self):
        """
        Like community.
        (contextmenu action handler)
        """
        try:
            self.vkapi.fave.addGroup(
                group_id=int(self.urlargs['communityid'])
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        self.log('Community liked: {0}'.format(self.urlargs['communityid']))
        self.notify(self.addon.getLocalizedString(30132))

    def likevideo(self):
        """
        Like video.
        (contextmenu action handler)
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        try:
            self.vkapi.likes.add(
                type='video',
                owner_id=int(self.urlargs['ownerid']),
                item_id=int(self.urlargs['id']),
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        self.log('Video liked: {0}'.format(oidid))
        self.notify(self.addon.getLocalizedString(30130))

    def listalbums(self):
        """
        List user's albums.
        (menu action handler)
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
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # create list items for albums
        listitems = []
        for i, album in enumerate(albums['items']):
            li = xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(album['title'], int(album['count']), color=COLOR_ALT))
            if album['count'] > 0:
                li.setArt({'thumb': album['photo_320']})
            # before/after album ids for reordering
            beforeid = albums['items'][i - 1]['id'] if i > 0 else None
            afterid = albums['items'][i + 1]['id'] if i < len(albums['items']) - 1 else None
            li.addContextMenuItems(
                [
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30058), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/renamealbum', {'albumid': album['id']}))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30059), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'beforeid': beforeid}))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30060), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'afterid': afterid}))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30062), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/addalbum'))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30061), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/deletealbum', {'albumid': album['id']}))),
                ]
            )
            listitems.append(
                (self.buildurl('/albumvideos', {'albumid': album['id']}), li, FOLDER)
            )
        # paginator item
        if int(self.urlargs['offset']) + albumsperpage < albums['count']:
            self.urlargs['offset'] = int(self.urlargs['offset']) + albumsperpage
            listitems.append(
                (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30190), color=COLOR_ALT)), FOLDER)
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
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list of album videos
        self.buildlistofvideos(albumvideos)

    def listcommunities(self):
        """
        List user's communities.
        (menu action handler)
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
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list of communities
        self.buildlistofcommunities(communities)

    def listcommunityvideos(self):
        """
        List user's community videos.
        (menu action handler)
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
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list of community videos
        self.buildlistofvideos(communityvideos)

    def listlikedcommunities(self):
        """
        List user's liked communities.
        (menu action handler)
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        # request vk api for liked communities data
        try:
            likedcommunities = self.vkapi.fave.getLinks(
                offset=int(self.urlargs['offset']),
                count=int(self.addon.getSetting('itemsperpage')),
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list of liked communities
        self.buildlistofcommunities(likedcommunities)

    def listlikedvideos(self):
        """
        List user's liked videos.
        (menu action handler)
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
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list of liked videos
        self.buildlistofvideos(likedvideos)

    def listmainmenu(self):
        """
        List main menu.
        (menu action handler)
        """
        # request vk api for menu counters (stored function)
        try:
            counters = self.vkapi.execute.getMenuCounters()
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # create list items for main menu
        listitems = [
            (self.buildurl('/search'), xbmcgui.ListItem('{0}'.format(self.addon.getLocalizedString(30030))), FOLDER),
            (self.buildurl('/searchhistory'), xbmcgui.ListItem('{0}'.format(self.addon.getLocalizedString(30031))), FOLDER),
            (self.buildurl('/videos'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30032), counters['videos'], color=COLOR_ALT)), FOLDER),
            (self.buildurl('/albums'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30034), counters['albums'], color=COLOR_ALT)), FOLDER),
            (self.buildurl('/communities'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30035), counters['communities'], color=COLOR_ALT)), FOLDER),
            (self.buildurl('/likedvideos'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30033), counters['likedvideos'], color=COLOR_ALT)), FOLDER),
            (self.buildurl('/likedcommunities'), xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(self.addon.getLocalizedString(30036), counters['likedcommunities'], color=COLOR_ALT)), FOLDER),
            (self.buildurl('/stats'), xbmcgui.ListItem('{0}'.format(self.addon.getLocalizedString(30037))), FOLDER),
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
        # create list items for search history sorted by lastUsed reversed
        listitems = []
        for search in sorted(searchhistory['items'], key=lambda x: x['lastUsed'], reverse=True):
            li = xbmcgui.ListItem('{0} [COLOR {color}]({1})[/COLOR]'.format(search['query'], search['resultsCount'], color=COLOR_ALT))
            li.addContextMenuItems(
                [
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30053), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/searchsimilar', {'qdef': search['query']}))),
                    ('[COLOR {color}]{0}[/COLOR]'.format(self.addon.getLocalizedString(30063), color=COLOR_ALT), 'Container.Update({0})'.format(self.buildurl('/deletesearch', {'q': search['query']}))),
                ]
            )
            listitems.append(
                (self.buildurl('/search', {'q': search['query']}), li, FOLDER)
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
        """
        pass  # todo: [feat] list usage stats

    def listvideos(self):
        """
        List user's videos.
        (menu action handler)
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
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # build list of videos
        self.buildlistofvideos(videos)

    def logout(self):
        """
        Logout user.
        (settings action handler)
        """
        # reset user access token
        self.addon.setSetting('vkuseraccesstoken', '')
        # delete cookiejar data file
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_COOKIEJAR)
        if os.path.isfile(fp):
            os.remove(fp)
        self.log('User logged out by resetting access token and deleting cookiejar data file.')
        self.notify(self.addon.getLocalizedString(30025))

    def playvideo(self):
        """
        Play video.
        (menu action handler)
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        # resolve playable streams via vk videoinfo api (hack)
        try:
            vi = self.vksession.requests_session.get(
                url='https://vk.com/al_video.php?act=show_inline&al=1&video={0}'.format(oidid),
                headers={'User-Agent': VK_VIDEOINFO_UA},
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
            self.log('Resolving error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30204), icon=xbmcgui.NOTIFICATION_ERROR)
            return
        # create item for kodi player (using max quality stream)
        self.log('Resolved playable stream/s: {0}'.format(playables))
        maxqual = max(playables.keys())
        self.log('Playing started: {0}'.format(playables[maxqual]))
        xbmcplugin.setContent(self.handle, 'videos')
        li = xbmcgui.ListItem(path=playables[maxqual])
        xbmcplugin.setResolvedUrl(self.handle, True, li)

    def renamealbum(self):
        """
        Rename album.
        (contextmenu action handler)
        """
        try:
            album = self.vkapi.video.getAlbumById(
                album_id=int(self.urlargs['albumid'])
            )
            albumtitle = xbmcgui.Dialog().input(self.addon.getLocalizedString(30115), defaultt=album['title'])
            if not albumtitle:
                return
            self.vkapi.video.editAlbum(
                album_id=int(self.urlargs['albumid']),
                title=albumtitle,
                privacy=3  # 3=onlyme
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        self.log('Album renamed: {0}'.format(self.urlargs['albumid']))
        self.notify(self.addon.getLocalizedString(30116))

    def reorderalbum(self):
        """
        Reorder album.
        (contextmenu action handler)
        """
        try:
            params = {'album_id': int(self.urlargs['albumid'])}
            if 'beforeid' in self.urlargs:
                params['before'] = int(self.urlargs['beforeid'])
            elif 'afterid' in self.urlargs:
                params['after'] = int(self.urlargs['afterid'])
            self.vkapi.video.reorderAlbums(**params)
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        self.log('Album reordered: {0}'.format(self.urlargs['albumid']))

    def searchvideos(self):
        """
        Search videos.
        (menu action handler)
        """
        # paging offset (default=0)
        self.urlargs['offset'] = self.urlargs.get('offset', 0)
        if int(self.urlargs['offset']) == 0:  # only once!
            # if not in urlargs, ask user for entering a search query (or editing one passed from /searchsimilar)
            if 'q' not in self.urlargs:
                self.urlargs['q'] = xbmcgui.Dialog().input(self.addon.getLocalizedString(30090), defaultt=self.urlargs.get('qdef', ''))
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
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        if int(self.urlargs['offset']) == 0:  # only once!
            # update search history
            lastsearch = {'query': self.urlargs['q'], 'resultsCount': int(searchedvideos['count'])}
            self.updatesearchhistory(lastsearch)
            # notify user of search results count
            self.notify(self.addon.getLocalizedString(30091).format(searchedvideos['count']))
        # build list of searched videos
        self.buildlistofvideos(searchedvideos)

    def setalbumsforvideo(self):
        """
        Set album/s for video.
        (contextmenu action handler)
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        try:
            # get user albums
            albums = self.vkapi.video.getAlbums(
                need_system=0,
                count=100  # ugly! todo: [feat] pageable multiselect dialog for /setalbumsforvideo?
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
            optionssel = xbmcgui.Dialog().multiselect(self.addon.getLocalizedString(30117), options, preselect=optionspre)
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
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        self.log('Albums set for video: {0} {1}=>{2}'.format(oidid, albumidspre, albumidssel))
        self.notify(self.addon.getLocalizedString(30118))

    def unlikecommunity(self):
        """
        Unlike community.
        (contextmenu action handler)
        """
        try:
            self.vkapi.fave.removeGroup(
                group_id=int(self.urlargs['communityid'])
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        self.log('Community unliked: {0}'.format(self.urlargs['communityid']))
        self.notify(self.addon.getLocalizedString(30133))

    def unlikevideo(self):
        """
        Unlike video.
        (contextmenu action handler)
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        try:
            self.vkapi.likes.delete(
                type='video',
                owner_id=int(self.urlargs['ownerid']),
                item_id=int(self.urlargs['id']),
            )
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30201), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        self.log('Video unliked: {0}'.format(oidid))
        self.notify(self.addon.getLocalizedString(30131))


class VKAddonError(Exception):
    """
    Exception type for addon errors.
    """
    def __init__(self, msg=None):
        self.msg = msg


if __name__ == '__main__':
    # run addon
    VKAddon()
