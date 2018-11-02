#!/usr/bin/env python
__all__ = ['VKAddon', 'VKAddonError']


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


PY2, PY3 = ((sys.version_info[0] == 2), (sys.version_info[0] == 3))
FOLDER, NOT_FOLDER = (True, False)

VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_VERSION = '5.87'
VK_API_LANG = 'ru'
VK_VIDEOINFO_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.0.1 Safari/605.1.15'
ADDON_DATA_FILE_COOKIEJAR = '.cookiejar'
ADDON_DATA_FILE_SEARCH = 'searchhistory.json'


class VKAddon():
    """
    Addon class encapsulating all its data and logic.
    """
    def __init__(self):
        """
        Initialize addon and manage all that controlling stuff at runtime ;-)
        """
        self.addon = xbmcaddon.Addon()
        self.handle = int(sys.argv[1])
        # create vk session
        try:
            # first run: authorise addon by entering user credentials and obtain new user access token
            if self.addon.getSetting('vkuseraccesstoken') == '':
                self.vksession = vk.AuthSession(
                    VK_API_APP_ID,
                    xbmcgui.Dialog().input(self.addon.getLocalizedString(30020)),
                    xbmcgui.Dialog().input(self.addon.getLocalizedString(30021), option=xbmcgui.ALPHANUM_HIDE_INPUT),
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
            self.notify(self.addon.getLocalizedString(30022), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        except VKAddonError:
            self.log('Missing data file error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30025), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()
        # create vk api, enable api usage tracking
        try:
            self.vkapi = vk.API(self.vksession, v=VK_API_VERSION, lang=VK_API_LANG)
            istracked = bool(self.vkapi.stats.trackVisitor())  # noqa
        except vk.exceptions.VkAPIError:
            self.log('VK API error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30023), icon=xbmcgui.NOTIFICATION_ERROR)
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
        # todo: pass urlargs as **kwargs?
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
            '/deletealbum': self.deletealbum,
            '/deletesearch': self.deletesearch,
            '/likecommunity': self.likecommunity,
            '/likevideo': self.likevideo,
            '/playalbum': self.playalbum,
            '/renamealbum': self.renamealbum,
            '/reorderalbum': self.reorderalbum,
            '/searchsimilar': self.searchvideos,  # reuse
            '/setalbumsforvideo': self.setalbumsforvideo,
            '/unfollowcommunity': self.unfollowcommunity,
            '/unlikecommunity': self.unlikecommunity,
            '/unlikevideo': self.unlikevideo,
        }
        try:
            self.routing[self.urlpath]()
        except KeyError:
            self.log('Addon routing error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30024), icon=xbmcgui.NOTIFICATION_ERROR)
            exit()

    def buildoidid(self, ownerid, id):
        """
        Build a full video identifier, aka oidid.
        (helper)
        :param ownerid: int; video owner id
        :param id: int; video id
        :returns: str; video oidid
        """
        return '{0}_{1}'.format(ownerid, id)

    def buildurl(self, urlpath, urlargs=None):
        """
        Build addon url.
        (helper)
        :param urlpath: str; action name
        :param urlargs: dict; action params, default=None
        :returns: str; addon url (plugin://...)
        """
        url = self.urlbase + urlpath
        if urlargs is not None and len(list(urlargs)) > 0:
            url += '?' + urllib.urlencode(urlargs)
        return url

    def loadcookies(self):
        """
        load cookiejar object from addon data file.
        (helper)
        :returns: obj
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_COOKIEJAR)
        try:
            with open(fp, 'rb') as f:
                cookiejar = pickle.load(f)
        except OSError:
            # file not exists
            raise VKAddonError('Missing data file error!')
        return cookiejar

    def loadsearchhistory(self):
        """
        load search history data from addon data file.
        (helper)
        :returns: dict
        """
        fp = os.path.join(xbmc.translatePath(self.addon.getAddonInfo('profile')), ADDON_DATA_FILE_SEARCH)
        try:
            with open(fp) as f:
                searchhistory = json.load(f)
        except OSError:
            # file not exists
            searchhistory = {'count': 0, 'items': []}
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
        :param msg: str;
        :param icon: int; xbmcgui.NOTIFICATION_INFO (default)
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
            json.dump(searchhistory, f, indent=4)

    def updatesearchhistory(self, search):
        """
        Append search to search history if query is unique, else re-append updated one.
        (helper)
        :param search: dict(query=str, resultsCount=int)
        """
        searchhistory = self.loadsearchhistory()
        existing = None
        for i, item in enumerate(searchhistory['items']):
            if item['query'] == search['query']:
                existing = searchhistory['items'].pop(i)
                break
        search['usesCount'] = 1 if not existing else existing['usesCount'] + 1
        search['lastUsed'] = datetime.datetime.now().isoformat()
        searchhistory['items'].append(search)
        if not existing:
            searchhistory['count'] += 1
        self.savesearchhistory(searchhistory)

    # ===== Menu action handlers =====

    def buildlistofcommunities(self, listdata):
        """
        Build list of communities.
        (helper)
        :param listdata: dict
        """
        # list type, one of: /communities, /likedcommunities
        listtype = self.urlpath
        # create list items for communities
        listitems = []
        _namekey = 'title' if listtype == '/likedcommunities' else 'name'
        for community in listdata['items']:
            if listtype == '/likedcommunities':
                community['id'] = community['id'].split('_')[2]
            li = xbmcgui.ListItem(label=community[_namekey])
            li.setArt({'thumb': community['photo_200']})
            # todo: use other infolabels (plot, ...) for showing community details?
            li.addContextMenuItems(
                [
                    ('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30054)), 'RunPlugin({0})'.format(self.buildurl('/unlikecommunity', {'communityid': community['id']}))),
                    ('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30055)), 'RunPlugin({0})'.format(self.buildurl('/likecommunity', {'communityid': community['id']}))),
                    ('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30056)), 'RunPlugin({0})'.format(self.buildurl('/unfollowcommunity', {'communityid': community['id']}))),
                ]
            )
            listitems.append(
                (self.buildurl('/communityvideos', {'ownerid': '-{0}'.format(community['id'])}), li, FOLDER)  # negative id required
            )
        # add paginator item  # todo: make this a method
        if int(listdata['count']) > int(self.addon.getSetting('itemsperpage')):
            if int(listdata['count']) > int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')):
                self.urlargs['offset'] = int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage'))
                listitems.append(
                    (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30200))), FOLDER)
                )
        # show community list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'files')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def buildlistofvideos(self, listdata):
        """
        Build list of videos.
        (helper)
        :param listdata: dict
        """
        # list type, one of: /videos, /searchedvideos, /albumvideos, /communityvideos, /likedvideos
        listtype = self.urlpath
        # create list items for videos
        listitems = []
        for video in listdata['items']:
            li = xbmcgui.ListItem(label=video['title'])
            li.setProperty('IsPlayable', 'true')
            li.setInfo(
                type='video',
                infoLabels={
                    'title': video['title'],
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
            # cm actions
            cmi = []
            if (listtype == '/likedvideos') or ('likes' in video and video['likes']['user_likes'] == 1):  # isliked
                cmi.append(('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30050)), 'RunPlugin({0})'.format(self.buildurl('/unlikevideo', {'ownerid': video['owner_id'], 'id': video['id']}))))
            else:
                cmi.append(('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30051)), 'RunPlugin({0})'.format(self.buildurl('/likevideo', {'ownerid': video['owner_id'], 'id': video['id']}))))
            cmi.append(('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30052)), 'RunPlugin({0})'.format(self.buildurl('/setalbumsforvideo', {'ownerid': video['owner_id'], 'id': video['id']}))))
            cmi.append(('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30053)), 'RunPlugin({0})'.format(self.buildurl('/searchsimilar', {'editq': video['title']}))))
            li.addContextMenuItems(cmi)
            listitems.append(
                (self.buildurl('/play', {'ownerid': video['owner_id'], 'id': video['id']}), li, NOT_FOLDER)
            )
        # add paginator item  # todo: lastpage limit
        if int(listdata['count']) > int(self.addon.getSetting('itemsperpage')):
            if int(listdata['count']) > int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')):
                self.urlargs['offset'] = int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage'))
                listitems.append(
                    (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30200))), FOLDER)
                )
        # if enabled, switch kodi view mode for videos
        if self.addon.getSetting('switchviewmodeforvideos') == 'true':
            xbmc.executebuiltin('Container.SetViewMode({0})'.format(int(self.addon.getSetting('viewmodeid'))))
        # show video list in kodi, even if empty
        xbmcplugin.setContent(self.handle, 'videos')
        xbmcplugin.addDirectoryItems(self.handle, listitems, len(listitems))
        xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_NONE)
        xbmcplugin.endOfDirectory(self.handle)

    def listalbums(self):
        """
        List user's albums.
        (menu action handler)
        """
        # set default paging offset
        if 'offset' not in self.urlargs:  # todo: better: int(self.urlargs.get('offset', 0))
            self.urlargs['offset'] = 0
        # request vk api for albums
        albums = self.vkapi.video.getAlbums(
            extended=1,
            offset=int(self.urlargs['offset']),
            count=100,  # todo: ugly! (api's max=100, default=50)
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
                    ('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30057)), 'RunPlugin({0})'.format(self.buildurl('/playalbum', {'albumid': album['id']}))),
                    ('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30058)), 'RunPlugin({0})'.format(self.buildurl('/renamealbum', {'albumid': album['id']}))),
                    ('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30059)), 'RunPlugin({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'beforeid': beforeid}))),
                    ('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30060)), 'RunPlugin({0})'.format(self.buildurl('/reorderalbum', {'albumid': album['id'], 'afterid': afterid}))),
                    ('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30062)), 'RunPlugin({0})'.format(self.buildurl('/addalbum'))),
                    ('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30061)), 'RunPlugin({0})'.format(self.buildurl('/deletealbum', {'albumid': album['id']}))),
                ]
            )
            listitems.append(
                (self.buildurl('/albumvideos', {'albumid': album['id']}), li, FOLDER)
            )
        # add paginator item
        if int(albums['count']) > int(self.addon.getSetting('itemsperpage')):
            if int(albums['count']) > int(self.urlargs['offset']) + int(self.addon.getSetting('itemsperpage')):
                self.urlargs['offset'] = int(self.urlargs['offset']) + self.addon.getSetting('itemsperpage')
                listitems.append(
                    (self.buildurl(self.urlpath, self.urlargs), xbmcgui.ListItem('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30200))), FOLDER)
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
        self.buildlistofvideos(albumvideos)

    def listcommunities(self):
        """
        List user's communities.
        (menu action handler)
        """
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for communities data
        communities = self.vkapi.groups.get(
            extended=1,
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
        )
        # build list of communities
        self.buildlistofcommunities(communities)

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
        self.buildlistofvideos(communityvideos)

    def listlikedcommunities(self):
        """
        List user's liked communities.
        (menu action handler)
        """
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for liked communities data
        likedcommunities = self.vkapi.fave.getLinks(
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
        )
        # build list of liked communities
        self.buildlistofcommunities(likedcommunities)

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
            counters = {'videos': '?', 'likedvideos': '?', 'albums': '?', 'communities': '?', 'likedcommunities': '?'}
        # create list items for main menu
        listitems = [
            (self.buildurl('/search'), xbmcgui.ListItem('{0}'.format(self.addon.getLocalizedString(30030))), FOLDER),
            (self.buildurl('/searchhistory'), xbmcgui.ListItem('{0}'.format(self.addon.getLocalizedString(30031))), FOLDER),
            (self.buildurl('/videos'), xbmcgui.ListItem('{0} [COLOR blue]({1})[/COLOR]'.format(self.addon.getLocalizedString(30032), counters['videos'])), FOLDER),
            (self.buildurl('/albums'), xbmcgui.ListItem('{0} [COLOR blue]({1})[/COLOR]'.format(self.addon.getLocalizedString(30034), counters['albums'])), FOLDER),
            (self.buildurl('/communities'), xbmcgui.ListItem('{0} [COLOR blue]({1})[/COLOR]'.format(self.addon.getLocalizedString(30035), counters['communities'])), FOLDER),
            (self.buildurl('/likedvideos'), xbmcgui.ListItem('{0} [COLOR blue]({1})[/COLOR]'.format(self.addon.getLocalizedString(30033), counters['likedvideos'])), FOLDER),
            (self.buildurl('/likedcommunities'), xbmcgui.ListItem('{0} [COLOR blue]({1})[/COLOR]'.format(self.addon.getLocalizedString(30036), counters['likedcommunities'])), FOLDER),
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
            li = xbmcgui.ListItem(
                label='{0} [COLOR blue]({1})[/COLOR]'.format(search['query'], search['resultsCount'])
            )
            li.addContextMenuItems(
                [
                    ('[COLOR blue]{0}[/COLOR]'.format(self.addon.getLocalizedString(30063)), 'RunPlugin({0})'.format(self.buildurl('/deletesearch', {'q': search['query']}))),
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
        self.buildlistofvideos(videos)

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
            if not playables:
                raise VKAddonError('Resolving error!')
        except VKAddonError:  # todo: [bug] also raising due to unhandled cookies expiration
            self.log('Resolving error!', level=xbmc.LOGERROR)
            self.notify(self.addon.getLocalizedString(30080), icon=xbmcgui.NOTIFICATION_ERROR)
            return
        # create item for kodi player (using max quality stream)
        self.log('Resolving ok, playable stream/s found: {0}'.format(playables))
        maxqual = max(playables.keys())
        self.log('Using max quality: {0}'.format(maxqual))
        xbmcplugin.setContent(self.handle, 'videos')
        li = xbmcgui.ListItem(path=playables[maxqual])
        xbmcplugin.setResolvedUrl(self.handle, True, li)

    def searchvideos(self):
        """
        Search videos.
        (menu action handler)
        """
        # if not passed, let user enter/edit a search query
        if 'q' not in self.urlargs:
            self.urlargs['q'] = xbmcgui.Dialog().input(self.addon.getLocalizedString(30090), defaultt=self.urlargs.get('editq', ''))  # todo: bug when cancel dialog (esc)
        # set default paging offset
        if 'offset' not in self.urlargs:
            self.urlargs['offset'] = 0
        # request vk api for searched videos
        searchedvideos = self.vkapi.video.search(
            extended=1,
            hd=1,
            q=str(self.urlargs['q']),
            adult=1 if self.addon.getSetting('searchadult') == 'true' else 0,  # case sens.!
            search_own=1 if self.addon.getSetting('searchown') == 'true' else 0,  # case sens.!
            # longer=int(self.addon.getSetting('searchlonger')) * 60,  # todo: longer or shorter, not both
            shorter=int(self.addon.getSetting('searchshorter')) * 60,
            sort=int(self.addon.getSetting('searchsort')),
            offset=int(self.urlargs['offset']),
            count=int(self.addon.getSetting('itemsperpage')),
        )
        if int(self.urlargs['offset']) == 0:  # todo: sure?
            # update search history
            self.updatesearchhistory(
                {
                    'query': str(self.urlargs['q']),
                    'resultsCount': int(searchedvideos['count']),
                }
            )
            # notify results count
            self.notify(self.addon.getLocalizedString(30091).format(searchedvideos['count']))
        # build list of searched videos
        self.buildlistofvideos(searchedvideos)

    # ===== Contextmenu action handlers =====

    def addalbum(self):
        """
        Add new album.
        (contextmenu action handler)
        """
        albumtitle = xbmcgui.Dialog().input(self.addon.getLocalizedString(30110))
        addedalbum = self.vkapi.video.addAlbum(
            title=str(albumtitle),
            privacy=['3']  # 3=onlyme  # todo: editable?
        )
        self.log('New album added: {0}'.format(addedalbum['album_id']))
        self.notify(self.addon.getLocalizedString(30111))
        xbmc.executebuiltin('Container.refresh')

    def deletealbum(self):
        """
        Delete album.
        (contextmenu action handler)
        """
        if xbmcgui.Dialog().yesno(self.addon.getLocalizedString(30112), self.addon.getLocalizedString(30113)):
            self.vkapi.video.deleteAlbum(
                album_id=int(self.urlargs['albumid']),
            )
            self.log('Album deleted: {0}'.format(self.urlargs['albumid']))
            self.notify(self.addon.getLocalizedString(30114))
            xbmc.executebuiltin('Container.refresh')

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
        xbmc.executebuiltin('Container.refresh')

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
        self.notify(self.addon.getLocalizedString(30130).format(like['likes']))
        xbmc.executebuiltin('Container.refresh')

    def playalbum(self):
        """
        Play album.
        (contextmenu action handler)
        """
        pass  # todo

    def renamealbum(self):
        """
        Rename album.
        (contextmenu action handler)
        """
        albumtitle = self.vkapi.video.getAlbumById(album_id=int(self.urlargs['albumid']))['title']
        albumtitle = xbmcgui.Dialog().input(self.addon.getLocalizedString(30115), albumtitle)
        self.vkapi.video.editAlbum(
            album_id=int(self.urlargs['albumid']),
            title=str(albumtitle),
            privacy=['3']  # 3=onlyme  # todo: editable?
        )
        self.log('Album renamed: {0}'.format(self.urlargs['albumid']))
        self.notify(self.addon.getLocalizedString(30116))
        xbmc.executebuiltin('Container.refresh')

    def reorderalbum(self):
        """
        Reorder album.
        (contextmenu action handler)
        """
        kwparams = {'album_id': int(self.urlargs['albumid'])}
        if 'beforeid' in self.urlargs:
            kwparams['before'] = int(self.urlargs['beforeid'])
        elif 'afterid' in self.urlargs:
            kwparams['after'] = int(self.urlargs['afterid'])
        self.vkapi.video.reorderAlbums(**kwparams)
        self.log('Album reordered: {0}'.format(self.urlargs['albumid']))
        xbmc.executebuiltin('Container.refresh')

    def setalbumsforvideo(self):
        """
        Set album/s for video.
        (contextmenu action handler)
        """
        oidid = self.buildoidid(self.urlargs['ownerid'], self.urlargs['id'])
        # get user albums
        albums = self.vkapi.video.getAlbums(
            count=100,  # todo: ugly! (api's max=100, default=50)
            need_system=0
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
            self.log('Albums set for video: {0} {1}=>{2}'.format(oidid, albumidspre, albumidssel))
            self.notify(self.addon.getLocalizedString(30118))
            xbmc.executebuiltin('Container.refresh')

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
        unlike = self.vkapi.likes.delete(  # noqa
            type='video',
            owner_id=int(self.urlargs['ownerid']),
            item_id=int(self.urlargs['id']),
        )
        self.log('Like deleted from video: {0}'.format(oidid))
        self.notify(self.addon.getLocalizedString(30131))
        xbmc.executebuiltin('Container.refresh')


class VKAddonError(Exception):
    """
    Exception type raised for all addon errors.
    """
    def __init__(self, errmsg):
        """
        :param errmsg: str
        """
        self.errmsg = errmsg


if __name__ == '__main__':
    # run addon
    VKAddon()
