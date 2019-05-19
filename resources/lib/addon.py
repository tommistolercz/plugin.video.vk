# coding=utf-8

__all__ = []
__version__ = "1.4.0-dev"

import datetime
import math
import os
import pickle
import re
import sys
import time  # debug
import urllib  # py2
import urlparse  # py2

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

import tinydb
import vk


# error ids
ERR_VK_AUTH = 30020
ERR_VK_API = 30021
ERR_ROUTING = 30022
ERR_DATA_FILE = 30023
ERR_RESOLVING = 30024

# file names
FILENAME_DB = 'db.json'
FILENAME_COOKIES = 'cookiejar.txt'

# db table names
DB_TABLE_ADDONREQUESTS = 'addonRequests'
DB_TABLE_PLAYEDVIDEOS = 'playedVideos'
DB_TABLE_SEARCHHISTORY = 'searchHistory'
DB_TABLE_WATCHLIST = 'watchlist'

# vk api
VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_LANG = 'ru'
VK_API_VERSION = '5.95'
VK_VI_UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.1.1 Safari/605.1.15'

# etc
ALT_COLOR = 'blue'

# url paths
URLPATH_LISTADDONMENU = '/'
URLPATH_LOGOUT = '/logout'
URLPATH_SKIPTOPAGE = '/skiptopage'
URLPATH_LISTSEARCHHISTORY = '/searchhistory'
URLPATH_CLEARSEARCHHISTORY = '/clearsearchhistory'
URLPATH_DELETESEARCH = '/deletesearch'
URLPATH_LISTSEARCHEDVIDEOS = '/searchvideos'
URLPATH_LISTPLAYEDVIDEOS = '/playedvideos'
URLPATH_LISTWATCHLIST = '/watchlist'
URLPATH_LISTVIDEOS = '/videos'
URLPATH_LISTLIKEDVIDEOS = '/likedvideos'
URLPATH_LISTALBUMVIDEOS = '/albumvideos'
URLPATH_LISTCOMMUNITYVIDEOS = '/communityvideos'
URLPATH_CLEARPLAYEDVIDEOS = '/clearplayedvideos'
URLPATH_CLEARWATCHLIST = '/clearwatchlist'
URLPATH_PLAYVIDEO = '/playvideo'
URLPATH_LIKEVIDEO = '/likevideo'
URLPATH_UNLIKEVIDEO = '/unlikevideo'
URLPATH_ADDVIDEOTOWATCHLIST = '/addvideotowatchlist'
URLPATH_DELETEVIDEOFROMWATCHLIST = '/deletevideofromwatchlist'
URLPATH_ADDVIDEOTOALBUMS = '/addvideotoalbums'
URLPATH_LISTALBUMS = '/albums'
URLPATH_REORDERALBUM = '/reorderalbum'
URLPATH_RENAMEALBUM = '/renamealbum'
URLPATH_CREATEALBUM = '/createalbum'
URLPATH_DELETEALBUM = '/deletealbum'
URLPATH_LISTCOMMUNITIES = '/communities'
URLPATH_LISTLIKEDCOMMUNITIES = '/likedcommunities'
URLPATH_LIKECOMMUNITY = '/likecommunity'
URLPATH_UNLIKECOMMUNITY = '/unlikecommunity'
URLPATH_FOLLOWCOMMUNITY = '/followcommunity'
URLPATH_UNFOLLOWCOMMUNITY = '/unfollowcommunity'


# global vars
ADDON = None
ROUTING = {}
SYSARGV = {}


class AddonError(Exception):
    """
    Exception class for add-on errors.
    """

    def __init__(self, errid):  # type: (int) -> None
        self.errid = errid


def initaddon():  # type: () -> xbmcaddon.Addon
    """
    Initialize add-on.
    """
    return xbmcaddon.Addon()


def initvksession():  # type: () -> vk.Session
    """
    Initialize VK session.
    """
    if ADDON.getSetting('vkuseraccesstoken') == '':
        # ask user for entering vk credentials for authorizing add-on
        login = xbmcgui.Dialog().input(
            ADDON.getLocalizedString(30030).encode('utf-8'),
            defaultt=ADDON.getSetting('vkuserlogin')
        )
        pswd = xbmcgui.Dialog().input(
            ADDON.getLocalizedString(30031).encode('utf-8'),
            option=xbmcgui.ALPHANUM_HIDE_INPUT
        )
        if not login or not pswd:
            xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK authorization error!'), level=xbmc.LOGERROR)
            raise AddonError(ERR_VK_AUTH)
        # create a new vk session
        try:
            vksession = vk.AuthSession(VK_API_APP_ID, login, pswd, VK_API_SCOPE)
        except vk.VkAuthError:
            xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK authorization error!'), level=xbmc.LOGERROR)
            raise AddonError(ERR_VK_AUTH)
        xbmc.log('{0}: VK session created.'.format(ADDON.getAddonInfo('id')))
        # save login + obtained token
        ADDON.setSetting('vkuserlogin', login)
        ADDON.setSetting('vkuseraccesstoken', vksession.access_token)
        # save cookies
        savecookies(vksession.auth_session.cookies)
    else:
        # restore existing vk session sending a token
        try:
            vksession = vk.Session(ADDON.getSetting('vkuseraccesstoken'))
        except vk.VkAuthError:
            xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK authorization error!'), level=xbmc.LOGERROR)
            raise AddonError(ERR_VK_AUTH)
        xbmc.log('{0}: VK session restored using token.'.format(ADDON.getAddonInfo('id')))
        # load cookies
        vksession.requests_session.cookies = loadcookies()
    return vksession


def initvkapi(vksession=None):  # type: (vk.Session) -> vk.API
    """
    Initialize VK API.
    """
    if not vksession:
        vksession = initvksession()
    try:
        vkapi = vk.API(vksession, v=VK_API_VERSION, lang=VK_API_LANG)
        vkapi.stats.trackVisitor()
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: VK API initialized.'.format(ADDON.getAddonInfo('id')))
    return vkapi


def savecookies(cookiejar):  # type: (object) -> None
    """
    Save cookiejar object to add-on data file, truncate if exists.
    """
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_COOKIES))
    try:
        with open(fp, 'wb') as f:
            pickle.dump(cookiejar, f)
    except IOError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'Data file error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_DATA_FILE)
    xbmc.log('{0}: Cookies saved: {1}'.format(ADDON.getAddonInfo('id'), fp))


def loadcookies():  # type: () -> object
    """
    Load cookiejar object from add-on data file, must exist since auth.
    """
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_COOKIES))
    try:
        with open(fp, 'rb') as f:
            cookiejar = pickle.load(f)
    except IOError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'Data file error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_DATA_FILE)
    xbmc.log('{0}: Cookies loaded: {1}'.format(ADDON.getAddonInfo('id'), fp))
    return cookiejar


def deletecookies():  # type: () -> None
    """
    Delete cookies add-on data file.
    """
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_COOKIES))
    try:
        os.remove(fp)
    except os.error:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'Data file error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_DATA_FILE)
    xbmc.log('{0}: Cookies deleted: {1}'.format(ADDON.getAddonInfo('id'), fp))


def buildurl(urlpath, urlargs=None):  # type: (str, dict) -> str
    """
    Build add-on url.
    """
    url = 'plugin://' + ADDON.getAddonInfo('id') + urlpath
    if urlargs:
        url += '?' + urllib.urlencode(urlargs)
    return url


def parseurl():  # type: () -> tuple
    """
    Parse add-on url.
    """
    urlpath = str(urlparse.urlsplit(SYSARGV['path'])[2])
    urlargs = {}
    if SYSARGV['qs'].startswith('?'):
        urlargs = urlparse.parse_qs(SYSARGV['qs'].lstrip('?'))
        for k, v in list(urlargs.items()):
            urlargs[k] = v.pop()
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
        fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
        db = tinydb.TinyDB(fp)
        db.table(DB_TABLE_ADDONREQUESTS).insert(lastrequest)
        xbmc.log('{0}: Addon requests db updated: {1}'.format(ADDON.getAddonInfo('id'), lastrequest))
    # call handler
    try:
        handler = ROUTING[urlpath]
    except KeyError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'Routing error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_ROUTING)
    xbmc.log('{0}: Routing dispatched: {1}'.format(ADDON.getAddonInfo('id'), handler.__name__))
    t1 = time.clock()
    handler(**urlargs)
    t2 = time.clock()
    xbmc.log('{0}: Handler runtime: {1} sec.'.format(ADDON.getAddonInfo('id'), t2 - t1))


# common -----


@route(URLPATH_LOGOUT)
def logout():  # type: () -> None
    """
    Logout user.
    """
    # delete cookies + reset user access token
    deletecookies()
    ADDON.setSetting('vkuseraccesstoken', '')
    xbmc.log('{0}: User logged out.'.format(ADDON.getAddonInfo('id')))
    xbmcgui.Dialog().notification(ADDON.getAddonInfo('name'), ADDON.getLocalizedString(30032).encode('utf-8'))


@route(URLPATH_LISTADDONMENU)
def listaddonmenu():  # type: () -> None
    """
    List add-on menu.
    """
    # collect menu counters from db...
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    counters = {
        'searchhistory': len(db.table(DB_TABLE_SEARCHHISTORY)),
        'playedvideos': len(db.table(DB_TABLE_PLAYEDVIDEOS)),
        'watchlist': len(db.table(DB_TABLE_WATCHLIST)),
    }
    # ...and from vkapi
    vkapi = initvkapi()
    try:
        counters.update(vkapi.execute.getMenuCounters())
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Counters: {1}'.format(ADDON.getAddonInfo('id'), counters))
    # create kodi list
    isfolder = True
    kodilist = [
        # search videos
        (
            buildurl(URLPATH_LISTSEARCHEDVIDEOS),
            xbmcgui.ListItem(
                ADDON.getLocalizedString(30040).encode('utf-8')
            ),
            isfolder
        ),
        # search history
        (
            buildurl(URLPATH_LISTSEARCHHISTORY),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30041).encode('utf-8'), ALT_COLOR, counters['searchhistory']
                )
            ),
            isfolder
        ),
    ]
    if ADDON.getSetting('keepplayedvideohistory') == 'true':
        kodilist += [
            # played videos
            (
                buildurl(URLPATH_LISTPLAYEDVIDEOS),
                xbmcgui.ListItem(
                    '{0} [COLOR {1}]({2})[/COLOR]'.format(
                        ADDON.getLocalizedString(30047).encode('utf-8'), ALT_COLOR, counters['playedvideos']
                    )
                ),
                isfolder
            )
        ]
    kodilist += [
        # watchlist
        (
            buildurl(URLPATH_LISTWATCHLIST),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30048).encode('utf-8'), ALT_COLOR, counters['watchlist']
                )
            ),
            isfolder
        ),
        # videos
        (
            buildurl(URLPATH_LISTVIDEOS),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30042).encode('utf-8'), ALT_COLOR, counters['videos']
                )
            ),
            isfolder
        ),
        # liked videos
        (
            buildurl(URLPATH_LISTLIKEDVIDEOS),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30043).encode('utf-8'), ALT_COLOR, counters['likedvideos']
                )
            ),
            isfolder
        ),
        # albums
        (
            buildurl(URLPATH_LISTALBUMS),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30044).encode('utf-8'), ALT_COLOR, counters['albums']
                )
            ),
            isfolder
        ),
        # communities
        (
            buildurl(URLPATH_LISTCOMMUNITIES),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30045).encode('utf-8'), ALT_COLOR, counters['communities']
                )
            ),
            isfolder
        ),
        # liked communities
        (
            buildurl(URLPATH_LISTLIKEDCOMMUNITIES),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30046).encode('utf-8'), ALT_COLOR, counters['likedcommunities']
                )
            ),
            isfolder
        ),
    ]
    # set displaying in Kodi
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], kodilist, len(kodilist))
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route(URLPATH_SKIPTOPAGE)
def skiptopage(listtype):  # type: (str) -> None
    """
    Skip to page.
    """
    # ask user for entering page to skip to.
    page = int(
        xbmcgui.Dialog().input(
            ADDON.getLocalizedString(30035).encode('utf-8'),
            type=xbmcgui.INPUT_ALPHANUM,
            defaultt='',
        )
    )
    if not page:
        return
    # refresh content
    xbmc.executebuiltin(
        'Container.Update({0})'.format(
            buildurl(listtype, {'offset': (page-1) * int(ADDON.getSetting('itemsperpage'))})
        )
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
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    searchhistory = {
        'count': len(db.table(DB_TABLE_SEARCHHISTORY)),
        'items': db.table(DB_TABLE_SEARCHHISTORY).all()[offset:offset + itemsperpage]
    }
    xbmc.log('{0}: Search history: {1}'.format(ADDON.getAddonInfo('id'), searchhistory))
    # create kodi list
    isfolder = True
    kodilist = []
    # search history items
    for search in sorted(searchhistory['items'], key=lambda x: x['lastUsed'], reverse=True):
        li = xbmcgui.ListItem(
            '{0} [COLOR {1}]({2})[/COLOR]'.format(
                search['q'].encode('utf-8'), ALT_COLOR, int(search['resultsCount'])
            )
        )
        li.addContextMenuItems(
            [
                # delete search
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30081).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_DELETESEARCH, {'searchid': search.doc_id})
                    )
                ),
                # clear search history
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30082).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_CLEARSEARCHHISTORY)
                    )
                ),
                # search videos
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30083).encode('utf-8')),
                    'Container.Update({0})'.format(
                        buildurl(URLPATH_LISTSEARCHEDVIDEOS)
                    )
                ),
                # search similar title
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30085).encode('utf-8')),
                    'Container.Update({0})'.format(
                        buildurl(URLPATH_LISTSEARCHEDVIDEOS, {'similarq': search['q'].encode('utf-8')})
                    )
                ),
            ]
        )
        kodilist.append(
            (
                buildurl(URLPATH_LISTSEARCHEDVIDEOS, {'q': search['q'].encode('utf-8')}),
                li,
                isfolder
            )
        )
    # pagination item
    if searchhistory['count'] > offset + itemsperpage:
        kodilist.append(
            (
                buildurl(URLPATH_LISTSEARCHHISTORY, {'offset': offset + itemsperpage}),
                xbmcgui.ListItem(
                    '[COLOR {0}]{1} ({2}/{3})[/COLOR]'.format(
                        ALT_COLOR,
                        ADDON.getLocalizedString(30034).encode('utf-8'),
                        int(offset / itemsperpage) + 1 + 1,  # nextpage
                        int(math.ceil(float(searchhistory['count']) / itemsperpage))  # lastpage
                    )
                ),
                True
            )
        )
    # set displaying in Kodi
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], kodilist, len(kodilist))
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


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
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    db.table(DB_TABLE_SEARCHHISTORY).remove(doc_ids=[searchid])
    xbmc.log('{0}: Search deleted: {1}'.format(ADDON.getAddonInfo('id'), searchid))
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
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    tinydb.TinyDB(fp).purge_table(DB_TABLE_SEARCHHISTORY)
    xbmc.log('{0}: Search history cleared.'.format(ADDON.getAddonInfo('id')))
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


# videos -----


@route(URLPATH_LISTSEARCHEDVIDEOS)
def listsearchedvideos(q='', similarq='', offset=0):  # type: (str, str, int) -> None
    """
    List searched videos.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # if q not passed, ask user for entering a new query / editing similar one
    if not q:
        q = xbmcgui.Dialog().input(ADDON.getLocalizedString(30083).encode('utf-8'), defaultt=similarq)
        if not q:
            return
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
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if searchedvideos['count'] > offset + itemsperpage:
        searchedvideos['pagination'] = {
            'nexturl': buildurl(URLPATH_LISTSEARCHEDVIDEOS, {'q': q, 'offset': offset + itemsperpage}),
            'nextpage': int(offset / itemsperpage) + 1 + 1,
            'lastpage': int(math.ceil(float(searchedvideos['count']) / itemsperpage))
        }
    xbmc.log('{0}: Searched videos: {1}'.format(ADDON.getAddonInfo('id'), searchedvideos))
    # only once
    if offset == 0:
        # update search history db with the last search
        lastsearch = {
            'q': q.lower(),
            'resultsCount': int(searchedvideos['count']),
            'lastUsed': datetime.datetime.now().isoformat()
        }
        fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
        db = tinydb.TinyDB(fp)
        db.table(DB_TABLE_SEARCHHISTORY).upsert(
            lastsearch,
            tinydb.where('q') == lastsearch['q']
        )
        xbmc.log('{0}: Search history db updated: {1}'.format(ADDON.getAddonInfo('id'), lastsearch))
        # notify search results count
        xbmcgui.Dialog().notification(
            ADDON.getAddonInfo('name'),
            ADDON.getLocalizedString(30084).encode('utf-8').format(searchedvideos['count'])
        )
    # build list
    buildvideolist(URLPATH_LISTSEARCHEDVIDEOS, searchedvideos)


@route(URLPATH_LISTPLAYEDVIDEOS)
def listplayedvideos(offset=0):  # type: (int) -> None
    """
    List played videos.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # query db
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    playedvideos = {
        'count': len(db.table(DB_TABLE_PLAYEDVIDEOS)),
        'items': db.table(DB_TABLE_PLAYEDVIDEOS).all()[offset:offset + itemsperpage]
    }
    # pagination data
    if playedvideos['count'] > offset + itemsperpage:
        playedvideos['pagination'] = {
            'nexturl': buildurl(URLPATH_LISTPLAYEDVIDEOS, {'offset': offset + itemsperpage}),
            'nextpage': int(offset / itemsperpage) + 1 + 1,
            'lastpage': int(math.ceil(float(playedvideos['count']) / itemsperpage))
        }
    xbmc.log('{0}: Played videos: {1}'.format(ADDON.getAddonInfo('id'), playedvideos))
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
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    watchlist = {
        'count': len(db.table(DB_TABLE_WATCHLIST)),
        'items': db.table(DB_TABLE_WATCHLIST).all()[offset:offset + itemsperpage]
    }
    # pagination data
    if watchlist['count'] > offset + itemsperpage:
        watchlist['pagination'] = {
            'nexturl': buildurl(URLPATH_LISTWATCHLIST, {'offset': offset + itemsperpage}),
            'nextpage': int(offset / itemsperpage) + 1 + 1,
            'lastpage': int(math.ceil(float(watchlist['count']) / itemsperpage))
        }
    xbmc.log('{0}: Watchlist: {1}'.format(ADDON.getAddonInfo('id'), watchlist))
    # build list
    buildvideolist(URLPATH_LISTWATCHLIST, watchlist)


@route(URLPATH_LISTVIDEOS)
def listvideos(ownerid=None, offset=0):  # type: (int, int) -> None
    """
    List videos.
    """
    ownerid = int(ownerid) if ownerid else None
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
        kwargs['owner_id'] = ownerid
    try:
        videos = vkapi.video.get(**kwargs)
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if videos['count'] > offset + itemsperpage:
        videos['pagination'] = {
            'nexturl': buildurl(URLPATH_LISTVIDEOS, {'ownerid': ownerid, 'offset': offset + itemsperpage}),
            'nextpage': int(offset / itemsperpage) + 1 + 1,
            'lastpage': int(math.ceil(float(videos['count']) / itemsperpage))
        }
    xbmc.log('{0}: Videos: {1}'.format(ADDON.getAddonInfo('id'), videos))
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
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if likedvideos['count'] > offset + itemsperpage:
        likedvideos['pagination'] = {
            'nexturl': buildurl(URLPATH_LISTLIKEDVIDEOS, {'offset': offset + itemsperpage}),
            'nextpage': int(offset / itemsperpage) + 1 + 1,
            'lastpage': int(math.ceil(float(likedvideos['count']) / itemsperpage))
        }
    xbmc.log('{0}: Liked videos: {1}'.format(ADDON.getAddonInfo('id'), likedvideos))
    # build list
    buildvideolist(URLPATH_LISTLIKEDVIDEOS, likedvideos)


@route(URLPATH_LISTALBUMVIDEOS)
def listalbumvideos(albumid, offset=0):  # type: (int, int) -> None
    """
    List album videos.
    """
    albumid = int(albumid)
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    vkapi = initvkapi()
    try:
        albumvideos = vkapi.video.get(
            extended=1,
            album_id=albumid,
            offset=offset,
            count=itemsperpage,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if albumvideos['count'] > offset + itemsperpage:
        albumvideos['pagination'] = {
            'nexturl': buildurl(URLPATH_LISTALBUMVIDEOS, {'albumid': albumid, 'offset': offset + itemsperpage}),
            'nextpage': int(offset / itemsperpage) + 1 + 1,
            'lastpage': int(math.ceil(float(albumvideos['count']) / itemsperpage))
        }
    xbmc.log('{0}: Album videos: {1}'.format(ADDON.getAddonInfo('id'), albumvideos))
    # build list
    buildvideolist(URLPATH_LISTALBUMVIDEOS, albumvideos)


@route(URLPATH_LISTCOMMUNITYVIDEOS)
def listcommunityvideos(communityid, offset=0):  # type: (int, int) -> None
    """
    List community videos.
    """
    communityid = int(communityid)
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    vkapi = initvkapi()
    try:
        communityvideos = vkapi.video.get(
            extended=1,
            owner_id=(-1 * communityid),  # neg.id required!
            offset=offset,
            count=itemsperpage,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if communityvideos['count'] > offset + itemsperpage:
        communityvideos['pagination'] = {
            'nexturl': buildurl(URLPATH_LISTCOMMUNITYVIDEOS, {'communityid': communityid, 'offset': offset + itemsperpage}),
            'nextpage': int(offset / itemsperpage) + 1 + 1,
            'lastpage': int(math.ceil(float(communityvideos['count']) / itemsperpage))
        }
    xbmc.log('{0}: Community videos: {1}'.format(ADDON.getAddonInfo('id'), communityvideos))
    # build list
    buildvideolist(URLPATH_LISTCOMMUNITYVIDEOS, communityvideos)


def buildvideolist(listtype, listdata):  # type: (str, dict) -> None
    """
    Build video list.
    """
    # create list
    listitems = []
    isfolder = False
    thumbsizes = ['photo_1280', 'photo_800', 'photo_640', 'photo_320']
    ownernames = {}
    if 'groups' in listdata:
        ownernames.update({str(-g['id']): g['screen_name'].encode('utf-8') for g in listdata['groups']})
    if 'profiles' in listdata:
        ownernames.update({str(p['id']): '{0} {1}'.format(p['first_name'].encode('utf-8'), p['last_name'].encode('utf-8')) for p in listdata['profiles']})
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
                'plot': video['description'].encode('utf-8'),
                'duration': video['duration'],
                'date': datetime.datetime.fromtimestamp(video['date']).strftime('%d.%m.%Y'),
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
        maxthumb = [video[thumbsize] for thumbsize in thumbsizes if thumbsize in video][0]
        li.setArt(
            {
                'thumb': maxthumb
            }
        )
        # create context menu
        cmi = []
        # like video
        if not video['is_favorite']:
            cmi += [
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30053).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_LIKEVIDEO, {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            ]
        # unlike video
        else:
            cmi += [
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30054).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_UNLIKEVIDEO, {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            ]
        # set albums
        cmi += [
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30055).encode('utf-8')),
                'RunPlugin({0})'.format(
                    buildurl(URLPATH_ADDVIDEOTOALBUMS, {'ownerid': video['owner_id'], 'videoid': video['id']})
                )
            )
        ]
        # add video to watchlist
        if 'added_to_watchlist' not in video:
            cmi += [
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30056).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_ADDVIDEOTOWATCHLIST, {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            ]
        # delete video from watchlist
        else:
            cmi += [
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30057).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_DELETEVIDEOFROMWATCHLIST, {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            ]
        # clear watchlist
        if listtype == URLPATH_LISTWATCHLIST:
            cmi += [
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30058).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_CLEARWATCHLIST)
                    )
                )
            ]
        # clear played videos
        elif listtype == URLPATH_LISTPLAYEDVIDEOS:
            cmi += [
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30059).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_CLEARPLAYEDVIDEOS)
                    )
                )
            ]
        if listtype in [URLPATH_LISTSEARCHEDVIDEOS, URLPATH_LISTLIKEDVIDEOS] and str(video['owner_id']) in ownernames:
            cmi += [
                # go to owner
                (
                    '[COLOR {0}]{1} {2}[/COLOR]'.format(
                        ALT_COLOR,
                        ADDON.getLocalizedString(30036).encode('utf-8'),
                        ownernames[str(video['owner_id'])]
                    ),
                    'Container.Update({0})'.format(
                        buildurl(URLPATH_LISTVIDEOS, {'ownerid': video['owner_id']})
                    )
                ),
                # follow owner
                (
                    '[COLOR {0}]{1} {2}[/COLOR]'.format(
                        ALT_COLOR,
                        ADDON.getLocalizedString(30037).encode('utf-8'),
                        ownernames[str(video['owner_id'])]
                    ),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_FOLLOWCOMMUNITY, {'communityid': video['owner_id']})
                    )
                ),
            ]
        cmi += [
            # skip to page
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30035).encode('utf-8')),
                'RunPlugin({0})'.format(
                    buildurl(URLPATH_SKIPTOPAGE, {'listtype': listtype})
                )
            ),
            # search videos
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30083).encode('utf-8')),
                'Container.Update({0})'.format(
                    buildurl(URLPATH_LISTSEARCHEDVIDEOS)
                )
            ),
            # search by similar title
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30085).encode('utf-8')),
                'Container.Update({0})'.format(
                    buildurl(URLPATH_LISTSEARCHEDVIDEOS, {'similarq': videotitle})
                )
            ),
        ]
        li.addContextMenuItems(cmi)
        listitems.append(
            (
                buildurl(URLPATH_PLAYVIDEO, {'ownerid': video['owner_id'], 'videoid': video['id']}),
                li,
                isfolder
            )
        )
    # pagination item
    if 'pagination' in listdata:
        listitems.append(
            (
                listdata['pagination']['nexturl'],
                xbmcgui.ListItem(
                    '[COLOR {0}]{1} ({2}/{3})[/COLOR]'.format(
                        ALT_COLOR,
                        ADDON.getLocalizedString(30034).encode('utf-8'),
                        listdata['pagination']['nextpage'],
                        listdata['pagination']['lastpage']
                    )
                ),
                True
            )
        )
    # force custom view mode for videos if enabled
    if ADDON.getSetting('forcevideoviewmode') == 'true':  # case sens!
        xbmc.executebuiltin('Container.SetViewMode({0})'.format(int(ADDON.getSetting('forcevideoviewmodeid'))))
    # show list in kodi, even if empty
    xbmcplugin.setContent(SYSARGV['handle'], 'videos')
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route(URLPATH_PLAYVIDEO)
def playvideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Play video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # resolve playable streams via vk videoinfo url
    vksession = initvksession()
    vi = vksession.requests_session.get(
        url='https://vk.com/al_video.php?act=show_inline&al=1&video={0}'.format(oidid),
        headers={'User-Agent': VK_VI_UA}
    )
    xbmc.log('{0}: vi.content: {1}'.format(ADDON.getAddonInfo('id'), vi.content))
    try:
        resolvedstreams = {m[0]: m[1] for m in re.findall(r'"url(\d+)":"([^"]+)"', vi.content.replace('\\', ''))}
        bestquality = sorted(resolvedstreams.keys(), key=lambda k: int(k)).pop()
    except IndexError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'Video resolving error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_RESOLVING)
    xbmc.log('{0}: Playable streams resolved: {1}. Best quality: {2}'.format(ADDON.getAddonInfo('id'), resolvedstreams, bestquality))
    # keep played video history, if enabled in settings
    if ADDON.getSetting('keepplayedvideohistory') == 'true':
        # request vk api
        vkapi = initvkapi(vksession)
        try:
            video = vkapi.video.get(extended=1, videos=oidid)['items'].pop()
        except vk.VkAPIError:
            xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
            raise AddonError(ERR_VK_API)
        video.update(
            {
                'oidid': oidid,
                'lastPlayed': datetime.datetime.now().isoformat(),
            }
        )
        fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
        db = tinydb.TinyDB(fp)
        db.table(DB_TABLE_PLAYEDVIDEOS).upsert(
            video,
            tinydb.where('oidid') == oidid
        )
        xbmc.log('{0}: Played videos db updated: {1}'.format(ADDON.getAddonInfo('id'), video))
    # create playable item for kodi player
    xbmcplugin.setResolvedUrl(SYSARGV['handle'], True, xbmcgui.ListItem(path=resolvedstreams[bestquality]))


@route(URLPATH_LIKEVIDEO)
def likevideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Like video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.likes.add(
            type='video',
            owner_id=ownerid,
            item_id=videoid,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Video liked: {1}'.format(ADDON.getAddonInfo('id'), oidid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_UNLIKEVIDEO)
def unlikevideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Unlike video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.likes.delete(
            type='video',
            owner_id=ownerid,
            item_id=videoid,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Video unliked: {1}'.format(ADDON.getAddonInfo('id'), oidid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_ADDVIDEOTOALBUMS)
def addvideotoalbums(ownerid, videoid):  # type: (int, int) -> None
    """
    Add video to albums.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # request vk api
    vkapi = initvkapi()
    try:
        # get user albums
        albums = vkapi.video.getAlbums(
            need_system=0,
            offset=0,
            count=100,
        )
        # get list of album ids for video
        albumids = vkapi.video.getAlbumsByVideo(
            owner_id=ownerid,
            video_id=videoid,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # create and show dialog w current sel
    opts = []
    sel = []
    for i, album in enumerate(albums['items']):
        opts.append(album['title'])
        if album['id'] in albumids:
            sel.append(i)
    newsel = xbmcgui.Dialog().multiselect(ADDON.getLocalizedString(30055).encode('utf-8'), opts, preselect=sel)
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
            vkapi.video.removeFromAlbum(
                owner_id=ownerid,
                video_id=videoid,
                album_ids=albumids
            )
        # add new sel album ids if any
        if len(newalbumids) > 0:
            vkapi.video.addToAlbum(
                owner_id=ownerid,
                video_id=videoid,
                album_ids=newalbumids
            )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Video added to albums: {1}'.format(ADDON.getAddonInfo('id'), oidid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_ADDVIDEOTOWATCHLIST)
def addvideotowatchlist(ownerid, videoid):  # type: (int, int) -> None
    """
    Add video to watchlist.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # request vk api for video
    vkapi = initvkapi()
    try:
        video = vkapi.video.get(
            extended=1,
            videos=oidid,
        )['items'].pop()
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # store video into db
    video.update(
        {
            'oidid': oidid,
            'added_to_watchlist': datetime.datetime.now().isoformat(),
        }
    )
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    db.table(DB_TABLE_WATCHLIST).upsert(
        video,
        tinydb.where('oidid') == oidid
    )
    xbmc.log('{0}: Video added to watchlist: {1}'.format(ADDON.getAddonInfo('id'), oidid))
    # refresh content - not needed


@route(URLPATH_DELETEVIDEOFROMWATCHLIST)
def deletevideofromwatchlist(ownerid, videoid):  # type: (int, int) -> None
    """
    Delete video from watchlist.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(
            ADDON.getLocalizedString(30057).encode('utf-8'),
            ADDON.getLocalizedString(30033).encode('utf-8')
    ):
        return
    # query db for deleting
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    db.table(DB_TABLE_WATCHLIST).remove(
        tinydb.where('oidid') == oidid
    )
    xbmc.log('{0}: Video deleted from watchlist: {1}'.format(ADDON.getAddonInfo('id'), oidid))
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
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    tinydb.TinyDB(fp).purge_table(DB_TABLE_WATCHLIST)
    xbmc.log('{0}: Watchlist cleared.'.format(ADDON.getAddonInfo('id')))
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
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    tinydb.TinyDB(fp).purge_table(DB_TABLE_PLAYEDVIDEOS)
    xbmc.log('{0}: Played videos cleared.'.format(ADDON.getAddonInfo('id')))
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
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Albums: {1}'.format(ADDON.getAddonInfo('id'), albums))
    # create list
    listitems = []
    isfolder = True
    for i, album in enumerate(albums['items']):
        # create album item
        li = xbmcgui.ListItem(
            '{0} [COLOR {1}]({2})[/COLOR]'.format(album['title'].encode('utf-8'), ALT_COLOR, int(album['count'])))
        # art, if any
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
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30061).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl(URLPATH_REORDERALBUM, {'albumid': album['id'], 'beforeid': beforeid}))
                ),
                # reorder album down
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30062).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl(URLPATH_REORDERALBUM, {'albumid': album['id'], 'afterid': afterid}))
                ),
                # rename album
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30060).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl(URLPATH_RENAMEALBUM, {'albumid': album['id']}))
                ),
                # delete album
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30063).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl(URLPATH_DELETEALBUM, {'albumid': album['id']}))
                ),
                # create new album
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30064).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl(URLPATH_CREATEALBUM))
                ),
                # search videos
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30083).encode('utf-8')),
                    'Container.Update({0})'.format(buildurl(URLPATH_LISTSEARCHEDVIDEOS))  # cnt.upd!
                ),
            ]
        )
        listitems.append(
            (
                buildurl(URLPATH_LISTALBUMVIDEOS, {'albumid': album['id']}),
                li,
                isfolder
            )
        )
    # pagination item
    if albums['count'] > offset + itemsperpage:
        listitems.append(
            (
                buildurl(URLPATH_LISTALBUMS, {'offset': offset + itemsperpage}),
                xbmcgui.ListItem(
                    '[COLOR {0}]{1} ({2}/{3})[/COLOR]'.format(
                        ALT_COLOR,
                        ADDON.getLocalizedString(30034).encode('utf-8'),
                        int(offset / itemsperpage) + 1 + 1,  # nextpage
                        int(math.ceil(float(albums['count']) / itemsperpage))  # lastpage
                    )
                ),
                True
            )
        )
    # show album list in kodi, even if empty
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


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
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Album reordered: {1}'.format(ADDON.getAddonInfo('id'), albumid))
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
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # ask user for editing current album title
    newtitle = xbmcgui.Dialog().input(ADDON.getLocalizedString(30060).encode('utf-8'), defaultt=album['title'])
    if not newtitle or newtitle == album['title']:
        return
    # request vk api for renaming album
    try:
        vkapi.video.editAlbum(
            album_id=albumid,
            title=newtitle,
            privacy=3  # 3=onlyme
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Album renamed: {1}'.format(ADDON.getAddonInfo('id'), albumid))
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
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Album deleted: {1}'.format(ADDON.getAddonInfo('id'), albumid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_CREATEALBUM)
def createalbum():  # type: () -> None
    """
    Create album.
    """
    # ask user for new album title
    albumtitle = xbmcgui.Dialog().input(ADDON.getLocalizedString(30064).encode('utf-8'))
    if not albumtitle:
        return
    # request vk api
    vkapi = initvkapi()
    try:
        album = vkapi.video.addAlbum(
            title=albumtitle,
            privacy=3,  # 3=onlyme
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Album created: {1}'.format(ADDON.getAddonInfo('id'), album))
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
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if communities['count'] > offset + itemsperpage:
        communities['pagination'] = {
            'nexturl': buildurl(URLPATH_LISTCOMMUNITIES, {'offset': offset + itemsperpage}),
            'nextpage': int(offset / itemsperpage) + 1 + 1,
            'lastpage': int(math.ceil(float(communities['count']) / itemsperpage))
        }
    xbmc.log('{0}: Communities: {1}'.format(ADDON.getAddonInfo('id'), communities))
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
        likedcommunities = vkapi.fave.getLinks(
            offset=offset,
            count=itemsperpage,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if likedcommunities['count'] > offset + itemsperpage:
        likedcommunities['pagination'] = {
            'nexturl': buildurl(URLPATH_LISTLIKEDCOMMUNITIES, {'offset': offset + itemsperpage}),
            'nextpage': int(offset / itemsperpage) + 1 + 1,
            'lastpage': int(math.ceil(float(likedcommunities['count']) / itemsperpage))
        }
    xbmc.log('{0}: Liked communities: {1}'.format(ADDON.getAddonInfo('id'), likedcommunities))
    # build list
    buildcommunitylist(URLPATH_LISTLIKEDCOMMUNITIES, likedcommunities)


def buildcommunitylist(listtype, listdata):  # type: (str, dict) -> None
    """
    Build community list.``
    """
    # create list
    listitems = []
    isfolder = True
    namekey = 'title' if listtype == URLPATH_LISTLIKEDCOMMUNITIES else 'name'
    for community in listdata['items']:
        if listtype == URLPATH_LISTLIKEDCOMMUNITIES:
            community['id'] = community['id'].split('_')[2]
        # create community item
        li = xbmcgui.ListItem(community[namekey].encode('utf-8'))
        # set art
        li.setArt(
            {
                'thumb': community['photo_200']
            }
        )
        # create context menu
        cmi = []
        # unlike community
        if listtype == URLPATH_LISTLIKEDCOMMUNITIES:
            cmi += [
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30071).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl(URLPATH_UNLIKECOMMUNITY, {'communityid': community['id']}))
                )
            ]
        # like community
        else:
            cmi += [
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30070).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl(URLPATH_LIKECOMMUNITY, {'communityid': community['id']}))
                )
            ]
        cmi += [
            # unfollow community
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30072).encode('utf-8')),
                'RunPlugin({0})'.format(buildurl(URLPATH_UNFOLLOWCOMMUNITY, {'communityid': community['id']}))
            ),
            # search videos
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30083).encode('utf-8')),
                'Container.Update({0})'.format(buildurl(URLPATH_LISTSEARCHEDVIDEOS))  # cnt.upd!
            ),
        ]
        li.addContextMenuItems(cmi)
        # add item to list
        listitems.append(
            (
                buildurl(URLPATH_LISTCOMMUNITYVIDEOS, {'communityid': '{0}'.format(community['id'])}),
                li,
                isfolder
            )
        )
    # pagination item
    if 'pagination' in listdata:
        listitems.append(
            (
                listdata['pagination']['nexturl'],
                xbmcgui.ListItem(
                    '[COLOR {0}]{1} ({2}/{3})[/COLOR]'.format(
                        ALT_COLOR,
                        ADDON.getLocalizedString(30034).encode('utf-8'),
                        listdata['pagination']['nextpage'],
                        listdata['pagination']['lastpage']
                    )
                ),
                True
            )
        )
    # show list in kodi, even if empty
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route(URLPATH_LIKECOMMUNITY)
def likecommunity(communityid):  # type: (int) -> None
    """
    Like community.
    """
    communityid = int(communityid)  # positive id
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.fave.addGroup(
            group_id=communityid
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Community liked: {1}'.format(ADDON.getAddonInfo('id'), communityid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_UNLIKECOMMUNITY)
def unlikecommunity(communityid):  # type: (int) -> None
    """
    Unlike community.
    """
    communityid = int(communityid)  # positive id
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.fave.removeGroup(
            group_id=communityid
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Community unliked: {1}'.format(ADDON.getAddonInfo('id'), communityid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_FOLLOWCOMMUNITY)
def followcommunity(communityid):  # type: (int) -> None
    """
    Follow community.
    """
    communityid = int(communityid)  # positive id
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.groups.join(
            group_id=communityid
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!', level=xbmc.LOGERROR))
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Community followed: {1}'.format(ADDON.getAddonInfo('id'), communityid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_UNFOLLOWCOMMUNITY)
def unfollowcommunity(communityid):  # type: (int) -> None
    """
    Unfollow community.
    """
    communityid = int(communityid)  # positive id
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.groups.leave(
            group_id=communityid
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Community unfollowed: {1}'.format(ADDON.getAddonInfo('id'), communityid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


# -----


if __name__ == '__main__':
    SYSARGV = {
        'path': str(sys.argv[0]),
        'handle': int(sys.argv[1]),
        'qs': str(sys.argv[2]),
    }
    try:
        ADDON = initaddon()
        dispatch()
    except AddonError as e:
        xbmcgui.Dialog().notification(
            ADDON.getAddonInfo('name'),
            ADDON.getLocalizedString(e.errid).encode('utf-8'),
            icon=xbmcgui.NOTIFICATION_ERROR
        )
