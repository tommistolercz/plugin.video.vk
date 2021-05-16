# coding=utf-8

__all__ = []

import datetime
import HTMLParser
import math
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


# db table names
DBT_ADDONREQUESTS = 'addonRequests'
DBT_PLAYEDVIDEOS = 'playedVideos'
DBT_SEARCHHISTORY = 'searchHistory'
DBT_WATCHLIST = 'watchlist'

# error msg ids
ERR_VKAUTH = 30020
ERR_VKAPI = 30021
ERR_ROUTING = 30022
ERR_DATAFILE = 30023
ERR_RESOLVING = 30024

# file names
FILENAME_DB = 'db.json'
FILENAME_SESSION = 'session.txt'

# content types
CONTENTTYPE_GENERALFILES = 'files'
CONTENTTYPE_VIDEOS = 'videos'

# item types
ITEMTYPE_FOLDER = True
ITEMTYPE_NOTFOLDER = False

# url paths
URLPATH_ADDVIDEOTOALBUMS = '/addvideotoalbums'
URLPATH_ADDVIDEOTOWATCHLIST = '/addvideotowatchlist'
URLPATH_CLEARPLAYEDVIDEOS = '/clearplayedvideos'
URLPATH_CLEARSEARCHHISTORY = '/clearsearchhistory'
URLPATH_CLEARWATCHLIST = '/clearwatchlist'
URLPATH_CREATEALBUM = '/createalbum'
URLPATH_DELETEALBUM = '/deletealbum'
URLPATH_DELETESEARCH = '/deletesearch'
URLPATH_DELETEVIDEOFROMWATCHLIST = '/deletevideofromwatchlist'
URLPATH_FOLLOWCOMMUNITY = '/followcommunity'
URLPATH_LIKECOMMUNITY = '/likecommunity'
URLPATH_LIKEVIDEO = '/likevideo'
URLPATH_LISTADDONMENU = '/'
URLPATH_LISTALBUMS = '/albums'
URLPATH_LISTCOMMUNITIES = '/communities'
URLPATH_LISTLIKEDCOMMUNITIES = '/likedcommunities'
URLPATH_LISTLIKEDVIDEOS = '/likedvideos'
URLPATH_LISTPLAYEDVIDEOS = '/playedvideos'
URLPATH_LISTSEARCHHISTORY = '/searchhistory'
URLPATH_LISTSEARCHEDVIDEOS = '/searchedvideos'
URLPATH_LISTVIDEOS = '/videos'
URLPATH_LISTWATCHLIST = '/watchlist'
URLPATH_LOGOUT = '/logout'
URLPATH_PLAYVIDEO = '/playvideo'
URLPATH_RENAMEALBUM = '/renamealbum'
URLPATH_REORDERALBUM = '/reorderalbum'
URLPATH_SEARCHVIDEOS = '/searchvideos'
URLPATH_SKIPTOPAGE = '/skiptopage'
URLPATH_UNFOLLOWCOMMUNITY = '/unfollowcommunity'
URLPATH_UNLIKECOMMUNITY = '/unlikecommunity'
URLPATH_UNLIKEVIDEO = '/unlikevideo'

# vk api config
VKAPI_APPID = '6432748'
VKAPI_LANG = 'en'
VKAPI_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VKAPI_VERSION = '5.95'

# global vars
ADDON = None
ROUTING = {}


# -----


class AddonError(Exception):
    """
    Exception class for add-on errors.
    """

    def __init__(self, errid):  # type: (int) -> None
        self.errid = errid


class KodiList(object):
    """
    List class.
    """

    def __init__(self, **kwargs):  # type: (dict) -> None
        self.content = kwargs.get('content', CONTENTTYPE_GENERALFILES)
        self.sortmethod = kwargs.get('sortmethod', xbmcplugin.SORT_METHOD_NONE)
        self.items = []

    def buildlist(self):  # type: () -> None
        sysargv = parsesysargv()
        xbmcplugin.setContent(sysargv['handle'], self.content)
        xbmcplugin.addSortMethod(sysargv['handle'], self.sortmethod)
        xbmcplugin.addDirectoryItems(sysargv['handle'], self.items, len(self.items))
        xbmcplugin.endOfDirectory(sysargv['handle'])


class PaginableKodiList(KodiList):  # todo
    """
    Paginable list class.
    """

    def __init__(self, **kwargs):  # type: (dict) -> None
        super(PaginableKodiList, self).__init__(**kwargs)
        self.nextpagenr = kwargs.get('nextpagenr')
        self.lastpagenr = kwargs.get('lastpagenr')

    def buildlist(self):  # type: () -> None
        super(PaginableKodiList, self).buildlist()

    def nextpage(self):  # type: () -> None
        pass


# -----


def initaddon():  # type: () -> xbmcaddon.Addon
    """
    Initialize add-on.
    """
    return xbmcaddon.Addon()


def initvkauthsession():  # type: () -> vk.api.AuthSession
    """
    Initialize VK auth session.
    """
    if not ADDON.getSetting('vkuseraccesstoken'):
        # create a new vk auth session, ask user for vk credentials
        login = xbmcgui.Dialog().input(
            ADDON.getLocalizedString(30030).encode('utf-8'),
            defaultt=ADDON.getSetting('vkuserlogin')
        )
        pswd = xbmcgui.Dialog().input(
            ADDON.getLocalizedString(30031).encode('utf-8'),
            defaultt=ADDON.getSetting('vkuserpswd'),
            option=xbmcgui.ALPHANUM_HIDE_INPUT
        )
        if not login or not pswd:
            xbmc.log('plugin.video.vk: VK auth error!', level=xbmc.LOGERROR)
            raise AddonError(ERR_VKAUTH)
        try:
            vkauthsession = vk.api.AuthSession(VKAPI_APPID, login, pswd, VKAPI_SCOPE)
        except vk.exceptions.VkAuthError:
            xbmc.log('plugin.video.vk: VK auth error!', level=xbmc.LOGERROR)
            raise AddonError(ERR_VKAUTH)
        savesession(vkauthsession)
        ADDON.setSetting('vkuserlogin', login)
        ADDON.setSetting('vkuserpswd', pswd)
        ADDON.setSetting('vkuseraccesstoken', vkauthsession.access_token)
    else:
        # restore vk auth session
        vkauthsession = loadsession()
    return vkauthsession


def initvkapi(vkauthsession=None):  # type: (vk.api.AuthSession) -> vk.api.API
    """
    Initialize VK API.
    """
    if not vkauthsession:
        vkauthsession = initvkauthsession()
    try:
        vkapi = vk.api.API(vkauthsession, v=VKAPI_VERSION, lang=VKAPI_LANG)
        vkapi.stats.trackVisitor()
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    return vkapi


def initvkresolver(vkauthsession=None):  # type: (vk.api.AuthSession) -> vk.utils.LoggingSession
    """
    Initialize VK video resolver.
    """
    if not vkauthsession:
        vkauthsession = initvkauthsession()
    return vkauthsession.auth_session


def savesession(obj):  # type: (object) -> None
    """
    Save session object to add-on data file.
    """
    fp = buildfp(FILENAME_SESSION)
    try:
        with open(fp, 'wb') as f:  # truncate if exists
            pickle.dump(obj, f, pickle.HIGHEST_PROTOCOL)
    except IOError:
        xbmc.log('plugin.video.vk: Data file error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_DATAFILE)


def loadsession():  # type: () -> object
    """
    Load session object from add-on data file.
    """
    fp = buildfp(FILENAME_SESSION)
    try:
        with open(fp, 'rb') as f:  # must exist since auth
            obj = pickle.load(f)
    except IOError:
        xbmc.log('plugin.video.vk: Data file error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_DATAFILE)
    return obj


def deletesession():  # type: () -> None
    """
    Delete session object / add-on data file.
    """
    fp = buildfp(FILENAME_SESSION)
    try:
        os.remove(fp)
    except os.error:
        pass


def buildfp(filename):  # type: (str) -> str
    """
    Build add-on data file path.
    """
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), filename))
    return fp


def buildurl(urlpath, urlargs=None):  # type: (str, dict) -> str
    """
    Build add-on url.
    """
    url = 'plugin://' + ADDON.getAddonInfo('id') + urlpath
    if urlargs:
        url += '?' + urllib.urlencode(urlargs)
    return url


def parsesysargv():  # type: () -> dict
    """
    Parse sys.argv passed from Kodi.
    """
    sysargv = {
        'path': str(sys.argv[0]),
        'handle': int(sys.argv[1]),
        'qs': str(sys.argv[2]),
    }
    return sysargv


def parseurl():  # type: () -> tuple
    """
    Parse add-on url.
    """
    sysargv = parsesysargv()
    urlpath = str(urlparse.urlsplit(sysargv['path'])[2])
    urlargs = {}
    if sysargv['qs'].startswith('?'):
        urlargs = dict(urlparse.parse_qsl(sysargv['qs'].lstrip('?')))
    return urlpath, urlargs


def route(urlpath):  # type: (str) -> callable(object)
    """
    Register add-on route (set callable handler for urlpath).
    """

    def sethandler(handler):
        ROUTING.update({urlpath: handler})
        return handler

    return sethandler


def dispatch():  # type: () -> None
    """
    Dispatch add-on routing.
    """
    # parse add-on url
    urlpath, urlargs = parseurl()
    # keep addon request history, if enabled in settings
    if ADDON.getSetting('keepaddonrequesthistory') == 'true':
        lastrequest = {
            'dt': datetime.datetime.now().isoformat(),
            'urlpath': urlpath,
            'urlargs': urlargs,
        }
        db = tinydb.TinyDB(buildfp(FILENAME_DB))
        db.table(DBT_ADDONREQUESTS).insert(lastrequest)
    # call handler
    try:
        handler = ROUTING[urlpath]
    except KeyError:
        xbmc.log('plugin.video.vk: Routing error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_ROUTING)
    handler(**urlargs)


# general -----


@route(URLPATH_LISTADDONMENU)
def listaddonmenu():  # type: () -> None
    """
    List add-on menu.
    """
    # collect menu counters from db and vkapi
    db = tinydb.TinyDB(buildfp(FILENAME_DB))
    counters = {
        'searchhistory': len(db.table(DBT_SEARCHHISTORY)),
        'playedvideos': len(db.table(DBT_PLAYEDVIDEOS)),
        'watchlist': len(db.table(DBT_WATCHLIST)),
    }
    vkapi = initvkapi()
    try:
        counters.update(vkapi.execute.getMenuCounters())
    except vk.exceptions.VkAuthError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # build menu list
    menu = KodiList()
    menu.items += [
        (
            # search videos
            buildurl(URLPATH_SEARCHVIDEOS),
            xbmcgui.ListItem(
                ADDON.getLocalizedString(30040).encode('utf-8')
            ),
            ITEMTYPE_NOTFOLDER
        ),
        (
            # search history
            buildurl(URLPATH_LISTSEARCHHISTORY),
            xbmcgui.ListItem(
                '{} [COLOR blue]({})[/COLOR]'.format(
                    ADDON.getLocalizedString(30041).encode('utf-8'),
                    counters['searchhistory']
                )
            ),
            ITEMTYPE_FOLDER
        ),
    ]
    if ADDON.getSetting('keepplayedvideohistory') == 'true':
        menu.items += [
            (
                # played videos
                buildurl(URLPATH_LISTPLAYEDVIDEOS),
                xbmcgui.ListItem(
                    '{} [COLOR blue]({})[/COLOR]'.format(
                        ADDON.getLocalizedString(30047).encode('utf-8'),
                        counters['playedvideos']
                    )
                ),
                ITEMTYPE_FOLDER
            ),
        ]
    menu.items += [
        (
            # watchlist
            buildurl(URLPATH_LISTWATCHLIST),
            xbmcgui.ListItem(
                '{} [COLOR blue]({})[/COLOR]'.format(
                    ADDON.getLocalizedString(30048).encode('utf-8'),
                    counters['watchlist']
                )
            ),
            ITEMTYPE_FOLDER
        ),
        (
            # my videos
            buildurl(URLPATH_LISTVIDEOS),
            xbmcgui.ListItem(
                '{} [COLOR blue]({})[/COLOR]'.format(
                    ADDON.getLocalizedString(30042).encode('utf-8'),
                    counters['videos']
                )
            ),
            ITEMTYPE_FOLDER
        ),
        (
            # my liked videos
            buildurl(URLPATH_LISTLIKEDVIDEOS),
            xbmcgui.ListItem(
                '{} [COLOR blue]({})[/COLOR]'.format(
                    ADDON.getLocalizedString(30043).encode('utf-8'),
                    counters['likedvideos']
                )
            ),
            ITEMTYPE_FOLDER
        ),
        (
            # my video albums
            buildurl(URLPATH_LISTALBUMS),
            xbmcgui.ListItem(
                '{} [COLOR blue]({})[/COLOR]'.format(
                    ADDON.getLocalizedString(30044).encode('utf-8'),
                    counters['albums']
                )
            ),
            ITEMTYPE_FOLDER
        ),
        (
            # my communities
            buildurl(URLPATH_LISTCOMMUNITIES),
            xbmcgui.ListItem(
                '{} [COLOR blue]({})[/COLOR]'.format(
                    ADDON.getLocalizedString(30045).encode('utf-8'),
                    counters['communities']
                )
            ),
            ITEMTYPE_FOLDER
        ),
        (
            # my liked communities
            buildurl(URLPATH_LISTLIKEDCOMMUNITIES),
            xbmcgui.ListItem(
                '{} [COLOR blue]({})[/COLOR]'.format(
                    ADDON.getLocalizedString(30046).encode('utf-8'),
                    counters['likedcommunities']
                )
            ),
            ITEMTYPE_FOLDER
        ),
    ]
    menu.buildlist()


@route(URLPATH_SKIPTOPAGE)
def skiptopage(page, lastpage, urlpath, urlargs):  # type: (int, int, str, str) -> None
    """
    Skip to page.
    """
    page = int(page)
    lastpage = int(lastpage)
    urlargs = eval(urlargs)  # ugly!
    # ask user for entering page nr.
    topage = xbmcgui.Dialog().input(
        '{} ({}-{})'.format(
            ADDON.getLocalizedString(30035).encode('utf-8'),
            1,
            lastpage
        ),
        defaultt=str(page),
        type=xbmcgui.INPUT_NUMERIC
    )
    if not topage or not (1 <= int(topage) <= lastpage) or int(topage) == page:
        return
    # update content with url to skip to
    xbmc.executebuiltin(
        'Container.Update({})'.format(
            buildurl(urlpath, urlargs.update({'offset': (int(topage) - 1) * int(ADDON.getSetting('itemsperpage'))}))
        )
    )


@route(URLPATH_LOGOUT)
def logout():  # type: () -> None
    """
    Logout user.
    """
    deletesession()
    ADDON.setSetting('vkuseraccesstoken', '')
    xbmcgui.Dialog().notification(
        ADDON.getAddonInfo('name'),
        ADDON.getLocalizedString(30032).encode('utf-8')
    )


# search -----


@route(URLPATH_LISTSEARCHHISTORY)
def listsearchhistory(offset=0):  # type: (int) -> None
    """
    List search history.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # query db
    db = tinydb.TinyDB(buildfp(FILENAME_DB))
    searchhistory = {
        'count': len(db.table(DBT_SEARCHHISTORY)),
        'items': db.table(DBT_SEARCHHISTORY).all()[offset:offset + itemsperpage]
    }
    kodilist = []
    # create pagination item
    if searchhistory['count'] > offset + itemsperpage:
        pi = xbmcgui.ListItem(
            '[COLOR blue]{} ({}/{})[/COLOR]'.format(
                ADDON.getLocalizedString(30034).encode('utf-8'),
                int(offset / itemsperpage) + 1 + 1,  # nextpage
                int(math.ceil(float(searchhistory['count']) / itemsperpage))  # lastpage
            )
        )
        pi.addContextMenuItems(
            [
                # skip to page
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30035).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(
                            URLPATH_SKIPTOPAGE,
                            {
                                'page': int(offset / itemsperpage) + 1,
                                'lastpage': int(math.ceil(float(searchhistory['count']) / itemsperpage)),
                                'urlpath': URLPATH_LISTSEARCHHISTORY,
                                'urlargs': str({}),  # ugly!
                            }
                        )
                    )
                )
            ]
        )
        kodilist.append(
            (
                buildurl(URLPATH_LISTSEARCHHISTORY, {'offset': offset + itemsperpage}),
                pi,
                ITEMTYPE_FOLDER
            )
        )
    # create list items
    for search in sorted(searchhistory['items'], key=lambda x: x['lastUsed'], reverse=True):
        # create search history item
        li = xbmcgui.ListItem(
            '{} [COLOR blue]({})[/COLOR]'.format(
                search['q'].encode('utf-8'),
                int(search['resultsCount'])
            )
        )
        # create context menu
        cmi = [
            # delete search
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30081).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_DELETESEARCH, {'searchid': search.doc_id})
                )
            ),
            # clear search history
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30082).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_CLEARSEARCHHISTORY)
                )
            ),
            # search videos
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30083).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_SEARCHVIDEOS)
                )
            ),
            # search videos by similar title
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30085).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_SEARCHVIDEOS, {'defq': search['q'].encode('utf-8')})
                )
            ),
        ]
        li.addContextMenuItems(cmi)
        kodilist.append(
            (
                buildurl(URLPATH_LISTSEARCHEDVIDEOS, {'q': search['q'].encode('utf-8')}),
                li,
                ITEMTYPE_FOLDER
            )
        )
    # set displaying in Kodi
    sysargv = parsesysargv()
    xbmcplugin.setContent(sysargv['handle'], 'files')
    xbmcplugin.addSortMethod(sysargv['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(sysargv['handle'], kodilist, len(kodilist))
    xbmcplugin.endOfDirectory(sysargv['handle'])


@route(URLPATH_DELETESEARCH)
def deletesearch(searchid):  # type: (int) -> None
    """
    Delete search from search history.
    """
    searchid = int(searchid)
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(
        ADDON.getLocalizedString(30081).encode('utf-8'),
        ADDON.getLocalizedString(30033).encode('utf-8')
    ):
        return
    # query db for deleting
    db = tinydb.TinyDB(buildfp(FILENAME_DB))
    db.table(DBT_SEARCHHISTORY).remove(doc_ids=[searchid])
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_CLEARSEARCHHISTORY)
def clearsearchhistory():  # type: () -> None
    """
    Clear search history.
    """
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(
            ADDON.getLocalizedString(30082).encode('utf-8'),
            ADDON.getLocalizedString(30033).encode('utf-8')
    ):
        return
    # purge db table
    db = tinydb.TinyDB(buildfp(FILENAME_DB))
    db.purge_table(DBT_SEARCHHISTORY)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_SEARCHVIDEOS)
def searchvideos(defq=''):  # type: (str) -> None
    """
    Search videos.
    """
    # ask user for entering/editing a new query
    q = xbmcgui.Dialog().input(ADDON.getLocalizedString(30083).encode('utf-8'), defaultt=defq)
    if not q:
        return
    # update content with searched videos
    xbmc.executebuiltin(
        'Container.Update({})'.format(
            buildurl(URLPATH_LISTSEARCHEDVIDEOS, {'q': q})
        )
    )


# videos -----


@route(URLPATH_LISTPLAYEDVIDEOS)
def listplayedvideos(offset=0):  # type: (int) -> None
    """
    List played videos.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # query db
    db = tinydb.TinyDB(buildfp(FILENAME_DB))
    playedvideos = {
        'count': len(db.table(DBT_PLAYEDVIDEOS)),
        'items': db.table(DBT_PLAYEDVIDEOS).all()[offset:offset + itemsperpage]
    }
    # pagination data
    if playedvideos['count'] > offset + itemsperpage:
        playedvideos['pagination'] = {
            'urlpath': URLPATH_LISTPLAYEDVIDEOS,
            'urlargs': {},
            'nexturl': buildurl(URLPATH_LISTPLAYEDVIDEOS, {'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(playedvideos['count']) / itemsperpage)),
        }
    # build list
    buildvideolist(URLPATH_LISTPLAYEDVIDEOS, playedvideos)


@route(URLPATH_LISTWATCHLIST)
def listwatchlist(offset=0):  # type: (int) -> None
    """
    List watchlist.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # query db
    db = tinydb.TinyDB(buildfp(FILENAME_DB))
    watchlist = {
        'count': len(db.table(DBT_WATCHLIST)),
        'items': db.table(DBT_WATCHLIST).all()[offset:offset + itemsperpage]
    }
    # pagination data
    if watchlist['count'] > offset + itemsperpage:
        watchlist['pagination'] = {
            'urlpath': URLPATH_LISTWATCHLIST,
            'urlargs': {},
            'nexturl': buildurl(URLPATH_LISTWATCHLIST, {'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(watchlist['count']) / itemsperpage)),
        }
    # build list
    buildvideolist(URLPATH_LISTWATCHLIST, watchlist)


@route(URLPATH_LISTSEARCHEDVIDEOS)
def listsearchedvideos(q, offset=0):  # type: (str, int) -> None
    """
    List searched videos.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    vkapi = initvkapi()
    kwargs = {
        'extended': 1,
        'hd': 1,
        'adult': 1 if ADDON.getSetting('searchadult') == 'true' else 0,  # case sens.!
        'search_own': 1 if ADDON.getSetting('searchown') == 'true' else 0,  # case sens.!
        'sort': int(ADDON.getSetting('searchsort')),
        'q': q,
        'offset': offset,
        'count': itemsperpage,
    }
    if ADDON.getSetting('searchduration') == '1':
        kwargs['longer'] = int(ADDON.getSetting('searchdurationmins')) * 60
    elif ADDON.getSetting('searchduration') == '2':
        kwargs['shorter'] = int(ADDON.getSetting('searchdurationmins')) * 60
    try:
        searchedvideos = vkapi.video.search(**kwargs)
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if searchedvideos['count'] > offset + itemsperpage:
        searchedvideos['pagination'] = {
            'urlpath': URLPATH_LISTSEARCHEDVIDEOS,
            'urlargs': {'q': q},
            'nexturl': buildurl(URLPATH_LISTSEARCHEDVIDEOS, {'q': q, 'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(searchedvideos['count']) / itemsperpage)),
        }
    if not offset:
        # update search history db
        lastsearch = {
            'q': q.lower(),
            'resultsCount': int(searchedvideos['count']),
            'lastUsed': datetime.datetime.now().isoformat(),
        }
        db = tinydb.TinyDB(buildfp(FILENAME_DB))
        db.table(DBT_SEARCHHISTORY).upsert(
            lastsearch,
            tinydb.where('q') == lastsearch['q']
        )
        # notify search results count
        xbmcgui.Dialog().notification(
            ADDON.getAddonInfo('name'),
            ADDON.getLocalizedString(30084).encode('utf-8').format(searchedvideos['count'])
        )
    # build list
    buildvideolist(URLPATH_LISTSEARCHEDVIDEOS, searchedvideos)


@route(URLPATH_LISTVIDEOS)
def listvideos(ownerid=0, albumid=0, offset=0):  # type: (int, int, int) -> None
    """
    List videos, album videos, community videos.
    """
    ownerid = int(ownerid)
    albumid = int(albumid)
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    vkapi = initvkapi()
    kwargs = {
        'extended': 1,
        'offset': offset,
        'count': itemsperpage,
    }
    if ownerid:
        kwargs['owner_id'] = ownerid  # negative id for communities
    if albumid:
        kwargs['album_id'] = albumid
    try:
        videos = vkapi.video.get(**kwargs)
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if videos['count'] > offset + itemsperpage:
        videos['pagination'] = {
            'urlpath': URLPATH_LISTVIDEOS,
            'urlargs': {'ownerid': ownerid, 'albumid': albumid},
            'nexturl': buildurl(URLPATH_LISTVIDEOS, {'ownerid': ownerid, 'albumid': albumid, 'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(videos['count']) / itemsperpage)),
        }
    # build list
    buildvideolist(URLPATH_LISTVIDEOS, videos)


@route(URLPATH_LISTLIKEDVIDEOS)
def listlikedvideos(offset=0):  # type: (int) -> None
    """
    List liked videos.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    vkapi = initvkapi()
    try:
        likedvideos = vkapi.fave.getVideos(
            extended=1,
            offset=offset,
            count=itemsperpage,
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if likedvideos['count'] > offset + itemsperpage:
        likedvideos['pagination'] = {
            'urlpath': URLPATH_LISTLIKEDVIDEOS,
            'urlargs': {},
            'nexturl': buildurl(URLPATH_LISTLIKEDVIDEOS, {'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(likedvideos['count']) / itemsperpage)),
        }
    # build list
    buildvideolist(URLPATH_LISTLIKEDVIDEOS, likedvideos)


def buildvideolist(listtype, listdata):  # type: (str, dict) -> None
    """
    Build video list.
    """
    listitems = []
    thumbsizes = ['photo_800', 'photo_640', 'photo_320']  # 'photo_1280'
    if 'groups' in listdata:
        # list => dict searchable by video's owner_id, negative!
        listdata['groups'] = {str(-group['id']): group for group in listdata['groups']}
    # create pagination item
    if 'pagination' in listdata:
        pi = xbmcgui.ListItem(
            '[COLOR blue]{} ({}/{})[/COLOR]'.format(
                ADDON.getLocalizedString(30034).encode('utf-8'),
                listdata['pagination']['page'] + 1,
                listdata['pagination']['lastpage']
            )
        )
        pi.addContextMenuItems(
            [
                # skip to page
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30035).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(
                            URLPATH_SKIPTOPAGE,
                            {
                                'page': listdata['pagination']['page'],
                                'lastpage': listdata['pagination']['lastpage'],
                                'urlpath': listdata['pagination']['urlpath'],
                                'urlargs': str(listdata['pagination']['urlargs']),  # ugly!
                            }
                        )
                    )
                )
            ]
        )
        listitems.append(
            (
                listdata['pagination']['nexturl'],
                pi,
                ITEMTYPE_FOLDER
            )
        )
    # create list items
    for video in listdata['items']:
        # create video item
        videotitle = video['title'].encode('utf-8').replace('.', ' ').replace('_', ' ')  # wrapable
        li = xbmcgui.ListItem(videotitle)
        # set isplayable
        li.setProperty('IsPlayable', 'true')
        # set infolabels
        li.setInfo(
            'video',
            {
                'title': videotitle,
                'plot': video.get('description', '').encode('utf-8'),
                'duration': video['duration'],
                'date': datetime.datetime.fromtimestamp(video['date']).strftime('%d.%m.%Y'),
            }
        )
        # set art
        try:
            maxthumb = [video[thumbsize] for thumbsize in thumbsizes if thumbsize in video][0]
            li.setArt({'thumb': maxthumb})
        except IndexError:
            pass
        # set stream infolabels
        li.addStreamInfo('video', {'width': video.get('width', None), 'height': video.get('height', None)})
        # create context menu
        cmi = []
        if not video.get('added_to_watchlist'):  # non-vkapi!
            cmi += [
                # add video to watchlist
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30056).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(
                            URLPATH_ADDVIDEOTOWATCHLIST,
                            {'ownerid': video['owner_id'], 'videoid': video['id']}
                        )
                    )
                )
            ]
        elif video.get('added_to_watchlist'):  # non-vkapi!
            cmi += [
                # delete video from watchlist
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30057).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(
                            URLPATH_DELETEVIDEOFROMWATCHLIST,
                            {'ownerid': video['owner_id'], 'videoid': video['id']}
                        )
                    )
                )
            ]
        if not video.get('is_favorite'):
            cmi += [
                # like video
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30053).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(
                            URLPATH_LIKEVIDEO,
                            {'ownerid': video['owner_id'], 'videoid': video['id']}
                        )
                    )
                )
            ]
        elif video.get('is_favorite'):
            cmi += [
                # unlike video
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30054).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(
                            URLPATH_UNLIKEVIDEO,
                            {'ownerid': video['owner_id'], 'videoid': video['id']}
                        )
                    )
                )
            ]
        cmi += [
            # set albums for video
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30055).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(
                        URLPATH_ADDVIDEOTOALBUMS,
                        {'ownerid': video['owner_id'], 'videoid': video['id']}
                    )
                )
            ),
            # create album
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30064).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_CREATEALBUM)
                )
            ),
        ]
        if listtype == URLPATH_LISTWATCHLIST:
            cmi += [
                # clear watchlist
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30058).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(URLPATH_CLEARWATCHLIST)
                    )
                )
            ]
        elif listtype == URLPATH_LISTPLAYEDVIDEOS:
            cmi += [
                # clear played videos
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30059).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(URLPATH_CLEARPLAYEDVIDEOS)
                    )
                )
            ]
        if video['owner_id'] < 0 and 'groups' in listdata:
            cmi += [
                # go to owning community (list community videos)
                (
                    '[COLOR blue]{} {}[/COLOR]'.format(
                        ADDON.getLocalizedString(30036).encode('utf-8'),
                        listdata['groups'][str(video['owner_id'])]['name'].encode('utf-8')
                    ),
                    'Container.Update({})'.format(
                        buildurl(URLPATH_LISTVIDEOS, {'ownerid': video['owner_id']})
                    )
                )
            ]
            if not listdata['groups'][str(video['owner_id'])]['is_member']:
                cmi += [
                    # follow owning community
                    (
                        '[COLOR blue]{} {}[/COLOR]'.format(
                            ADDON.getLocalizedString(30037).encode('utf-8'),
                            listdata['groups'][str(video['owner_id'])]['name'].encode('utf-8')
                        ),
                        'RunPlugin({})'.format(
                            buildurl(URLPATH_FOLLOWCOMMUNITY, {'communityid': video['owner_id']})
                        )
                    )
                ]
        cmi += [
            # search videos
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30083).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_SEARCHVIDEOS)
                )
            ),
            # search videos by similar title
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30085).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_SEARCHVIDEOS, {'defq': videotitle})
                )
            ),
        ]
        li.addContextMenuItems(cmi)
        listitems.append(
            (
                buildurl(URLPATH_PLAYVIDEO, {'ownerid': video['owner_id'], 'videoid': video['id']}),
                li,
                ITEMTYPE_NOTFOLDER
            )
        )
    # force custom view mode for videos if enabled
    if ADDON.getSetting('forcevideoviewmode') == 'true':  # case sens!
        xbmc.executebuiltin(
            'Container.SetViewMode({})'.format(
                int(ADDON.getSetting('forcevideoviewmodeid'))
            )
        )
    # set displaying in kodi
    sysargv = parsesysargv()
    xbmcplugin.setContent(sysargv['handle'], 'videos')
    xbmcplugin.addSortMethod(sysargv['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(sysargv['handle'], listitems, len(listitems))
    xbmcplugin.endOfDirectory(sysargv['handle'])


@route(URLPATH_PLAYVIDEO)
def playvideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Play video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{}_{}'.format(ownerid, videoid))
    # resolve playable streams + find best quality
    vkr = initvkresolver()
    r = vkr.get('https://vk.com/al_video.php?act=show_inline&al=1&video={}'.format(oidid))
    cnt = r.text.encode('utf-8').replace('\\', '')
    resolvedpath = None
    if ADDON.getSetting('preferhls') == 'true':
        # hls - if enabled in settings
        try:
            resolvedpath = HTMLParser.HTMLParser().unescape(urllib.unquote(
                re.compile(r'src="([^"]+video_hls\.php[^"]+)"').findall(cnt)[0]
            )).encode('utf-8')
        except IndexError:
            pass
    if not resolvedpath:
        # mp4
        try:
            srcs = {m[1]: m[0] for m in re.compile(r'src="([^"]+\.(\d+)\.mp4[^"]+)"').findall(cnt)}
            bestq = sorted(srcs.keys(), key=lambda k: int(k), reverse=True)[0]
            resolvedpath = srcs[bestq]
        except IndexError:
            xbmc.log('plugin.video.vk: Video resolving error!', level=xbmc.LOGERROR)
            raise AddonError(ERR_RESOLVING)
    # update played video history - if enabled in settings
    if ADDON.getSetting('keepplayedvideohistory') == 'true':
        # request vk api
        vkapi = initvkapi()
        try:
            video = vkapi.video.get(extended=1, videos=oidid)['items'][0]
        except vk.exceptions.VkAPIError:
            xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
            raise AddonError(ERR_VKAPI)
        video.update(
            {
                'oidid': oidid,
                'lastPlayed': datetime.datetime.now().isoformat(),
            }
        )
        db = tinydb.TinyDB(buildfp(FILENAME_DB))
        db.table(DBT_PLAYEDVIDEOS).upsert(
            video,
            tinydb.where('oidid') == oidid
        )
    # create playable item for kodi player
    sysargv = parsesysargv()
    xbmcplugin.setResolvedUrl(sysargv['handle'], True, xbmcgui.ListItem(path=resolvedpath))


@route(URLPATH_LIKEVIDEO)
def likevideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Like video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.likes.add(
            type='video',
            owner_id=ownerid,
            item_id=videoid,
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_UNLIKEVIDEO)
def unlikevideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Unlike video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.likes.delete(
            type='video',
            owner_id=ownerid,
            item_id=videoid,
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_ADDVIDEOTOALBUMS)
def addvideotoalbums(ownerid, videoid):  # type: (int, int) -> None
    """
    Add video to albums.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    # request vk api
    vkapi = initvkapi()
    try:
        # get user albums
        albums = vkapi.video.getAlbums(
            need_system=0,
            offset=0,
            count=100,
        )
        # get album ids for video
        albumids = vkapi.video.getAlbumsByVideo(
            owner_id=ownerid,
            video_id=videoid,
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # create dialog w current albums selected
    opts = []
    sel = []
    for i, album in enumerate(albums['items']):
        opts.append(album['title'])
        if album['id'] in albumids:
            sel.append(i)
    newsel = xbmcgui.Dialog().multiselect(ADDON.getLocalizedString(30055).encode('utf-8'), opts, preselect=sel)
    if newsel is None or newsel == sel:
        return
    # selected albums changed
    newalbumids = []
    for i in newsel:
        newalbumids.append(albums['items'][i]['id'])
    # request vk api
    try:
        # remove selected album ids if any
        if len(albumids) > 0:
            vkapi.video.removeFromAlbum(
                owner_id=ownerid,
                video_id=videoid,
                album_ids=albumids
            )
        # add newly selected album ids if any
        if len(newalbumids) > 0:
            vkapi.video.addToAlbum(
                owner_id=ownerid,
                video_id=videoid,
                album_ids=newalbumids
            )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_ADDVIDEOTOWATCHLIST)
def addvideotowatchlist(ownerid, videoid):  # type: (int, int) -> None
    """
    Add video to watchlist.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{}_{}'.format(ownerid, videoid))
    # request vk api for video
    vkapi = initvkapi()
    try:
        video = vkapi.video.get(extended=1, videos=oidid)['items'].pop()
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # store video into db
    video.update(
        {
            'oidid': oidid,
            'added_to_watchlist': datetime.datetime.now().isoformat(),
        }
    )
    db = tinydb.TinyDB(buildfp(FILENAME_DB))
    db.table(DBT_WATCHLIST).upsert(
        video,
        tinydb.where('oidid') == oidid
    )
    # refresh content not needed


@route(URLPATH_DELETEVIDEOFROMWATCHLIST)
def deletevideofromwatchlist(ownerid, videoid):  # type: (int, int) -> None
    """
    Delete video from watchlist.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{}_{}'.format(ownerid, videoid))
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(
            ADDON.getLocalizedString(30057).encode('utf-8'),
            ADDON.getLocalizedString(30033).encode('utf-8')
    ):
        return
    # query db for deleting
    db = tinydb.TinyDB(buildfp(FILENAME_DB))
    db.table(DBT_WATCHLIST).remove(
        tinydb.where('oidid') == oidid
    )
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_CLEARWATCHLIST)
def clearwatchlist():  # type: () -> None
    """
    Clear watchlist.
    """
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(
            ADDON.getLocalizedString(30058).encode('utf-8'),
            ADDON.getLocalizedString(30033).encode('utf-8')
    ):
        return
    # purge db table
    db = tinydb.TinyDB(buildfp(FILENAME_DB))
    db.purge_table(DBT_WATCHLIST)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_CLEARPLAYEDVIDEOS)
def clearplayedvideos():  # type: () -> None
    """
    Clear played videos.
    """
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(
            ADDON.getLocalizedString(30059).encode('utf-8'),
            ADDON.getLocalizedString(30033).encode('utf-8')
    ):
        return
    # purge db table
    db = tinydb.TinyDB(buildfp(FILENAME_DB))
    db.purge_table(DBT_PLAYEDVIDEOS)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


# video albums -----


@route(URLPATH_LISTALBUMS)
def listalbums(offset=0):  # type: (int) -> None
    """
    List video albums.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    if itemsperpage > 100:
        itemsperpage = 100  # api's max for albums
    # request vk api
    vkapi = initvkapi()
    try:
        albums = vkapi.video.getAlbums(
            extended=1,
            offset=offset,
            count=itemsperpage,
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    listitems = []
    thumbsizes = ['photo_320', 'photo_160']
    # create pagination item
    if albums['count'] > offset + itemsperpage:
        pi = xbmcgui.ListItem(
            '[COLOR blue]{} ({}/{})[/COLOR]'.format(
                ADDON.getLocalizedString(30034).encode('utf-8'),
                int(offset / itemsperpage) + 1 + 1,  # nextpage
                int(math.ceil(float(albums['count']) / itemsperpage))  # lastpage
            )
        )
        pi.addContextMenuItems(
            [
                # skip to page
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30035).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(
                            URLPATH_SKIPTOPAGE,
                            {
                                'page': int(offset / itemsperpage) + 1,
                                'lastpage': int(math.ceil(float(albums['count']) / itemsperpage)),
                                'urlpath': URLPATH_LISTALBUMS,
                                'urlargs': str({}),  # ugly!
                            }
                        )
                    )
                )
            ]
        )
        listitems.append(
            (
                buildurl(URLPATH_LISTALBUMS, {'offset': offset + itemsperpage}),
                pi,
                ITEMTYPE_FOLDER
            )
        )
    # create list items
    for i, album in enumerate(albums['items']):
        # create album item
        li = xbmcgui.ListItem(
            '{} [COLOR blue]({})[/COLOR]'.format(
                album['title'].encode('utf-8'),
                int(album['count'])
            )
        )
        # set art
        try:
            maxthumb = [album[thumbsize] for thumbsize in thumbsizes if thumbsize in album][0]
            li.setArt({'thumb': maxthumb})
        except IndexError:
            pass
        # before/after album ids for reordering
        beforeid = albums['items'][i - 1]['id'] if i > 0 else None
        afterid = albums['items'][i + 1]['id'] if i < len(albums['items']) - 1 else None
        # create context menu
        cmi = [
            # reorder album up
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30061).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_REORDERALBUM, {'albumid': album['id'], 'beforeid': beforeid})
                )
            ),
            # reorder album down
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30062).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_REORDERALBUM, {'albumid': album['id'], 'afterid': afterid})
                )
            ),
            # rename album
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30060).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_RENAMEALBUM, {'albumid': album['id']})
                )
            ),
            # delete album
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30063).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_DELETEALBUM, {'albumid': album['id']})
                )
            ),
            # create new album
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30064).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_CREATEALBUM)
                )
            ),
            # search videos
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30083).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_SEARCHVIDEOS)
                )
            ),
            # search videos by similar title (album title)
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30085).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_SEARCHVIDEOS, {'defq': album['title'].encode('utf-8')})
                )
            ),
        ]
        li.addContextMenuItems(cmi)
        listitems.append(
            (
                buildurl(URLPATH_LISTVIDEOS, {'albumid': album['id']}),
                li,
                ITEMTYPE_FOLDER
            )
        )
    # set displaying in kodi
    sysargv = parsesysargv()
    xbmcplugin.setContent(sysargv['handle'], 'files')
    xbmcplugin.addSortMethod(sysargv['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(sysargv['handle'], listitems, len(listitems))
    xbmcplugin.endOfDirectory(sysargv['handle'])


@route(URLPATH_REORDERALBUM)
def reorderalbum(albumid, beforeid=None, afterid=None):  # type: (int, int, int) -> None
    """
    Reorder album.
    """
    albumid = int(albumid)
    reorder = {}
    if beforeid:
        reorder['before'] = int(beforeid)
    elif afterid:
        reorder['after'] = int(afterid)
    # request vk api
    try:
        vkapi = initvkapi()
        vkapi.video.reorderAlbums(
            album_id=albumid,
            **reorder
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_RENAMEALBUM)
def renamealbum(albumid):  # type: (int) -> None
    """
    Rename album.
    """
    albumid = int(albumid)
    # request vk api
    vkapi = initvkapi()
    try:
        album = vkapi.video.getAlbumById(
            album_id=albumid
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # ask user for editing current album title
    newtitle = xbmcgui.Dialog().input(
        ADDON.getLocalizedString(30060).encode('utf-8'),
        defaultt=album['title']
    )
    if not newtitle or newtitle == album['title']:
        return
    # request vk api for renaming album
    try:
        vkapi.video.editAlbum(
            album_id=albumid,
            title=newtitle,
            privacy=3  # 3=onlyme
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_DELETEALBUM)
def deletealbum(albumid):  # type: (int) -> None
    """
    Delete album.
    """
    albumid = int(albumid)
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(
            ADDON.getLocalizedString(30063).encode('utf-8'),
            ADDON.getLocalizedString(30033).encode('utf-8')
    ):
        return
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.video.deleteAlbum(
            album_id=albumid,
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_CREATEALBUM)
def createalbum():  # type: () -> None
    """
    Create album.
    """
    # ask user for new album title
    albumtitle = xbmcgui.Dialog().input(
        ADDON.getLocalizedString(30064).encode('utf-8')
    )
    if not albumtitle:
        return
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.video.addAlbum(
            title=albumtitle,
            privacy=3,  # 3=onlyme
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


# communities -----


@route(URLPATH_LISTCOMMUNITIES)
def listcommunities(offset=0):  # type: (int) -> None
    """
    List communities.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    vkapi = initvkapi()
    try:
        communities = vkapi.groups.get(
            extended=1,
            offset=offset,
            count=itemsperpage,
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if communities['count'] > offset + itemsperpage:
        communities['pagination'] = {
            'urlpath': URLPATH_LISTCOMMUNITIES,
            'urlargs': {},
            'nexturl': buildurl(URLPATH_LISTCOMMUNITIES, {'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(communities['count']) / itemsperpage)),
        }
    # build list
    buildcommunitylist(URLPATH_LISTCOMMUNITIES, communities)


@route(URLPATH_LISTLIKEDCOMMUNITIES)
def listlikedcommunities(offset=0):  # type: (int) -> None
    """
    List liked communities.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    vkapi = initvkapi()
    try:
        likedcommunities = vkapi.fave.getPages(
            type='groups',
            offset=offset,
            count=itemsperpage,
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if likedcommunities['count'] > offset + itemsperpage:
        likedcommunities['pagination'] = {
            'urlpath': URLPATH_LISTLIKEDCOMMUNITIES,
            'urlargs': {},
            'nexturl': buildurl(URLPATH_LISTLIKEDCOMMUNITIES, {'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(likedcommunities['count']) / itemsperpage)),
        }
    # build list
    buildcommunitylist(URLPATH_LISTLIKEDCOMMUNITIES, likedcommunities)


def buildcommunitylist(listtype, listdata):  # type: (str, dict) -> None
    """
    Build community list.``
    """
    listitems = []
    thumbsizes = ['photo_200', 'photo_100']
    # create pagination item
    if 'pagination' in listdata:
        pi = xbmcgui.ListItem(
            '[COLOR blue]{} ({}/{})[/COLOR]'.format(
                ADDON.getLocalizedString(30034).encode('utf-8'),
                listdata['pagination']['page'] + 1,
                listdata['pagination']['lastpage']
            )
        )
        pi.addContextMenuItems(
            [
                # skip to page
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30035).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(
                            URLPATH_SKIPTOPAGE,
                            {
                                'page': listdata['pagination']['page'],
                                'lastpage': listdata['pagination']['lastpage'],
                                'urlpath': listdata['pagination']['urlpath'],
                                'urlargs': str(listdata['pagination']['urlargs']),  # ugly!
                            }
                        )
                    )
                )
            ]
        )
        listitems.append(
            (
                listdata['pagination']['nexturl'],
                pi,
                ITEMTYPE_FOLDER
            )
        )
    # create list items
    for item in listdata['items']:
        community = item['group'] if listtype == URLPATH_LISTLIKEDCOMMUNITIES else item
        # create community item
        li = xbmcgui.ListItem(label=community['name'].encode('utf-8'))
        # set art
        try:
            maxthumb = [community[thumbsize] for thumbsize in thumbsizes if thumbsize in community][0]
            li.setArt({'thumb': maxthumb})
        except IndexError:
            pass
        # create context menu
        cmi = []
        if listtype == URLPATH_LISTCOMMUNITIES:
            cmi += [
                # like community
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30070).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(URLPATH_LIKECOMMUNITY, {'communityid': community['id']})
                    )
                )
            ]
        elif listtype == URLPATH_LISTLIKEDCOMMUNITIES:
            cmi += [
                # unlike community
                (
                    '[COLOR blue]{}[/COLOR]'.format(
                        ADDON.getLocalizedString(30071).encode('utf-8')
                    ),
                    'RunPlugin({})'.format(
                        buildurl(URLPATH_UNLIKECOMMUNITY, {'communityid': community['id']})
                    )
                )
            ]
        cmi += [
            # unfollow community
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30072).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_UNFOLLOWCOMMUNITY, {'communityid': community['id']})
                )
            ),
            # search videos
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30083).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(URLPATH_SEARCHVIDEOS)
                )
            ),
            # search videos by similar title (community name)
            (
                '[COLOR blue]{}[/COLOR]'.format(
                    ADDON.getLocalizedString(30085).encode('utf-8')
                ),
                'RunPlugin({})'.format(
                    buildurl(
                        URLPATH_SEARCHVIDEOS,
                        {'defq': community['name'].encode('utf-8')}
                    )
                )
            ),
        ]
        li.addContextMenuItems(cmi)
        listitems.append(
            (
                buildurl(URLPATH_LISTVIDEOS, {'ownerid': -community['id']}),  # negative id required!
                li,
                ITEMTYPE_FOLDER
            )
        )
    # set displaying in kodi
    sysargv = parsesysargv()
    xbmcplugin.setContent(sysargv['handle'], 'files')
    xbmcplugin.addSortMethod(sysargv['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(sysargv['handle'], listitems, len(listitems))
    xbmcplugin.endOfDirectory(sysargv['handle'])


@route(URLPATH_LIKECOMMUNITY)
def likecommunity(communityid):  # type: (int) -> None
    """
    Like community.
    """
    communityid = abs(int(communityid))  # positive id!
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.fave.addGroup(
            group_id=communityid
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_UNLIKECOMMUNITY)
def unlikecommunity(communityid):  # type: (int) -> None
    """
    Unlike community.
    """
    communityid = abs(int(communityid))  # positive id!
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.fave.removeGroup(
            group_id=communityid
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_FOLLOWCOMMUNITY)
def followcommunity(communityid):  # type: (int) -> None
    """
    Follow community.
    """
    communityid = abs(int(communityid))  # positive id!
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.groups.join(
            group_id=communityid
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_UNFOLLOWCOMMUNITY)
def unfollowcommunity(communityid):  # type: (int) -> None
    """
    Unfollow community.
    """
    communityid = abs(int(communityid))  # positive id!
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(
            ADDON.getLocalizedString(30072).encode('utf-8'),
            ADDON.getLocalizedString(30033).encode('utf-8')
    ):
        return
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.groups.leave(
            group_id=communityid
        )
    except vk.exceptions.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


# -----


if __name__ == '__main__':
    try:
        ADDON = initaddon()
        dispatch()
    except AddonError as e:
        xbmcgui.Dialog().notification(
            ADDON.getAddonInfo('name'),
            ADDON.getLocalizedString(e.errid).encode('utf-8'),
            icon=xbmcgui.NOTIFICATION_ERROR
        )
