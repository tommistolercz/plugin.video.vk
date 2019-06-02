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


# colors
COLOR_ALT = 'blue'  # vk blue: 4877a4

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
FILENAME_COOKIES = 'cookiejar.txt'
FILENAME_DB = 'db.json'

# item types
ITEMTYPE_FOLDER = True
ITEMTYPE_NOTFOLDER = False

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
URLPATH_LISTCOMMUNITYVIDEOS = '/communityvideos'  # todo: deprecated
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

# vk api config
VKAPI_APPID = '6432748'
VKAPI_LANG = 'en'
VKAPI_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VKAPI_VERSION = '5.95'

# vk video resolver
VKRESOLVER_UA = '{0} {1}'.format(
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_13_6)',
    'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/12.1.1 Safari/605.1.15'
)


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
            xbmc.log('plugin.video.vk: VK auth error!', level=xbmc.LOGERROR)
            raise AddonError(ERR_VKAUTH)
        # create a new vk session
        try:
            vksession = vk.AuthSession(VKAPI_APPID, login, pswd, VKAPI_SCOPE)
        except vk.VkAuthError:
            xbmc.log('plugin.video.vk: VK auth error!', level=xbmc.LOGERROR)
            raise AddonError(ERR_VKAUTH)
        xbmc.log('plugin.video.vk: VK session created.')
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
            xbmc.log('plugin.video.vk: VK auth error!', level=xbmc.LOGERROR)
            raise AddonError(ERR_VKAUTH)
        xbmc.log('plugin.video.vk: VK session restored using token.')
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
        vkapi = vk.API(vksession, v=VKAPI_VERSION, lang=VKAPI_LANG)
        vkapi.stats.trackVisitor()
    except vk.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: VK API initialized.')
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
        xbmc.log('plugin.video.vk: Data file error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_DATAFILE)
    xbmc.log('plugin.video.vk: Cookies saved: {}'.format(fp))


def loadcookies():  # type: () -> object
    """
    Load cookiejar object from add-on data file, must exist since auth.
    """
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_COOKIES))
    try:
        with open(fp, 'rb') as f:
            cookiejar = pickle.load(f)
    except IOError:
        xbmc.log('plugin.video.vk: Data file error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_DATAFILE)
    xbmc.log('plugin.video.vk: Cookies loaded: {}'.format(fp))
    return cookiejar


def deletecookies():  # type: () -> None
    """
    Delete cookies add-on data file.
    """
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_COOKIES))
    try:
        os.remove(fp)
    except os.error:
        xbmc.log('plugin.video.vk: Data file error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_DATAFILE)
    xbmc.log('plugin.video.vk: Cookies deleted: {}'.format(fp))


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
        db.table(DBT_ADDONREQUESTS).insert(lastrequest)
        xbmc.log('plugin.video.vk: Addon requests db updated: {}'.format(lastrequest))
    # call handler
    try:
        handler = ROUTING[urlpath]
    except KeyError:
        xbmc.log('plugin.video.vk: Routing error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_ROUTING)
    xbmc.log('plugin.video.vk: Routing dispatched: {}'.format(handler.__name__))
    t1 = time.clock()
    handler(**urlargs)
    t2 = time.clock()
    xbmc.log('plugin.video.vk: Handler runtime: {} sec.'.format(t2 - t1))


# auth -----


@route(URLPATH_LOGOUT)
def logout():  # type: () -> None
    """
    Logout user.
    """
    # delete cookies + reset user access token
    deletecookies()
    ADDON.setSetting('vkuseraccesstoken', '')
    xbmc.log('plugin.video.vk: User logged out.')
    xbmcgui.Dialog().notification(ADDON.getAddonInfo('name'), ADDON.getLocalizedString(30032).encode('utf-8'))


# navigation -----


@route(URLPATH_LISTADDONMENU)
def listaddonmenu():  # type: () -> None
    """
    List add-on menu.
    """
    # collect menu counters from db...
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    counters = {
        'searchhistory': len(db.table(DBT_SEARCHHISTORY)),
        'playedvideos': len(db.table(DBT_PLAYEDVIDEOS)),
        'watchlist': len(db.table(DBT_WATCHLIST)),
    }
    # ...and from vkapi
    vkapi = initvkapi()
    try:
        counters.update(vkapi.execute.getMenuCounters())
    except vk.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Counters: {}'.format(counters))
    # create kodi list
    kodilist = [
        # search videos
        (
            buildurl(URLPATH_LISTSEARCHEDVIDEOS),
            xbmcgui.ListItem(
                ADDON.getLocalizedString(30040).encode('utf-8')
            ),
            ITEMTYPE_FOLDER
        ),
        # search history
        (
            buildurl(URLPATH_LISTSEARCHHISTORY),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30041).encode('utf-8'), COLOR_ALT, counters['searchhistory']
                )
            ),
            ITEMTYPE_FOLDER
        ),
    ]
    if ADDON.getSetting('keepplayedvideohistory') == 'true':
        kodilist += [
            # played videos
            (
                buildurl(URLPATH_LISTPLAYEDVIDEOS),
                xbmcgui.ListItem(
                    '{0} [COLOR {1}]({2})[/COLOR]'.format(
                        ADDON.getLocalizedString(30047).encode('utf-8'), COLOR_ALT, counters['playedvideos']
                    )
                ),
                ITEMTYPE_FOLDER
            )
        ]
    kodilist += [
        # watchlist
        (
            buildurl(URLPATH_LISTWATCHLIST),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30048).encode('utf-8'), COLOR_ALT, counters['watchlist']
                )
            ),
            ITEMTYPE_FOLDER
        ),
        # videos
        (
            buildurl(URLPATH_LISTVIDEOS),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30042).encode('utf-8'), COLOR_ALT, counters['videos']
                )
            ),
            ITEMTYPE_FOLDER
        ),
        # liked videos
        (
            buildurl(URLPATH_LISTLIKEDVIDEOS),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30043).encode('utf-8'), COLOR_ALT, counters['likedvideos']
                )
            ),
            ITEMTYPE_FOLDER
        ),
        # albums
        (
            buildurl(URLPATH_LISTALBUMS),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30044).encode('utf-8'), COLOR_ALT, counters['albums']
                )
            ),
            ITEMTYPE_FOLDER
        ),
        # communities
        (
            buildurl(URLPATH_LISTCOMMUNITIES),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30045).encode('utf-8'), COLOR_ALT, counters['communities']
                )
            ),
            ITEMTYPE_FOLDER
        ),
        # liked communities
        (
            buildurl(URLPATH_LISTLIKEDCOMMUNITIES),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30046).encode('utf-8'), COLOR_ALT, counters['likedcommunities']
                )
            ),
            ITEMTYPE_FOLDER
        ),
    ]
    # set displaying in Kodi
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], kodilist, len(kodilist))
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route(URLPATH_SKIPTOPAGE)
def skiptopage(page, lastpage, skipurl):  # type: (int, int, str) -> None
    """
    Skip to page.
    """
    page = int(page)
    lastpage = int(lastpage)
    # ask user for entering page to skip to.
    skipto = xbmcgui.Dialog().input(
        '{0} ({1}-{2})'.format(ADDON.getLocalizedString(30035).encode('utf-8'), 1, lastpage),
        defaultt=str(page),
        type=xbmcgui.INPUT_NUMERIC
    )
    if not skipto or not (1 <= int(skipto) <= lastpage) or int(skipto) == page:
        return
    # refresh content
    xbmc.executebuiltin(
        'Container.Update({0})'.format(
            buildurl(skipurl, {'offset': (int(skipto) - 1) * int(ADDON.getSetting('itemsperpage'))})
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
        'count': len(db.table(DBT_SEARCHHISTORY)),
        'items': db.table(DBT_SEARCHHISTORY).all()[offset:offset + itemsperpage]
    }
    xbmc.log('plugin.video.vk: Search history: {}'.format(searchhistory))
    kodilist = []
    # create pagination item
    if searchhistory['count'] > offset + itemsperpage:
        pi = xbmcgui.ListItem(
            '[COLOR {0}]{1} ({2}/{3})[/COLOR]'.format(
                COLOR_ALT,
                ADDON.getLocalizedString(30034).encode('utf-8'),
                int(offset / itemsperpage) + 1 + 1,  # nextpage
                int(math.ceil(float(searchhistory['count']) / itemsperpage))  # lastpage
            )
        )
        pi.addContextMenuItems(
            [
                # skip to page
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30035).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(
                            URLPATH_SKIPTOPAGE,
                            {
                                'page': int(offset / itemsperpage) + 1,
                                'lastpage': int(math.ceil(float(searchhistory['count']) / itemsperpage)),
                                'skipurl': buildurl(URLPATH_LISTSEARCHHISTORY),
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
            '{0} [COLOR {1}]({2})[/COLOR]'.format(
                search['q'].encode('utf-8'), COLOR_ALT, int(search['resultsCount'])
            )
        )
        # create context menu
        cmi = [
            # delete search
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30081).encode('utf-8')),
                'RunPlugin({0})'.format(
                    buildurl(URLPATH_DELETESEARCH, {'searchid': search.doc_id})
                )
            ),
            # clear search history
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30082).encode('utf-8')),
                'RunPlugin({0})'.format(
                    buildurl(URLPATH_CLEARSEARCHHISTORY)
                )
            ),
            # search videos
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30083).encode('utf-8')),
                'Container.Update({0})'.format(
                    buildurl(URLPATH_LISTSEARCHEDVIDEOS)
                )
            ),
            # search similar title
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30085).encode('utf-8')),
                'Container.Update({0})'.format(
                    buildurl(URLPATH_LISTSEARCHEDVIDEOS, {'similarq': search['q'].encode('utf-8')})
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
    db.table(DBT_SEARCHHISTORY).remove(doc_ids=[searchid])
    xbmc.log('plugin.video.vk: Search deleted: {}'.format(searchid))
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
    tinydb.TinyDB(fp).purge_table(DBT_SEARCHHISTORY)
    xbmc.log('plugin.video.vk: Search history cleared.')
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if searchedvideos['count'] > offset + itemsperpage:
        searchedvideos['pagination'] = {
            'skipurl': buildurl(URLPATH_LISTSEARCHEDVIDEOS, {'q': q}),
            'nexturl': buildurl(URLPATH_LISTSEARCHEDVIDEOS, {'q': q, 'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(searchedvideos['count']) / itemsperpage)),
        }
    xbmc.log('plugin.video.vk: Searched videos: {}'.format(searchedvideos))
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
        db.table(DBT_SEARCHHISTORY).upsert(
            lastsearch,
            tinydb.where('q') == lastsearch['q']
        )
        xbmc.log('plugin.video.vk: Search history db updated: {}'.format(lastsearch))
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
        'count': len(db.table(DBT_PLAYEDVIDEOS)),
        'items': db.table(DBT_PLAYEDVIDEOS).all()[offset:offset + itemsperpage]
    }
    # pagination data
    if playedvideos['count'] > offset + itemsperpage:
        playedvideos['pagination'] = {
            'skipurl': buildurl(URLPATH_LISTPLAYEDVIDEOS),
            'nexturl': buildurl(URLPATH_LISTPLAYEDVIDEOS, {'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(playedvideos['count']) / itemsperpage))
        }
    xbmc.log('plugin.video.vk: Played videos: {}'.format(playedvideos))
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
        'count': len(db.table(DBT_WATCHLIST)),
        'items': db.table(DBT_WATCHLIST).all()[offset:offset + itemsperpage]
    }
    # pagination data
    if watchlist['count'] > offset + itemsperpage:
        watchlist['pagination'] = {
            'skipurl': buildurl(URLPATH_LISTWATCHLIST),
            'nexturl': buildurl(URLPATH_LISTWATCHLIST, {'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(watchlist['count']) / itemsperpage))
        }
    xbmc.log('plugin.video.vk: Watchlist: {}'.format(watchlist))
    # build list
    buildvideolist(URLPATH_LISTWATCHLIST, watchlist)


@route(URLPATH_LISTVIDEOS)
def listvideos(ownerid=None, offset=0):  # type: (int, int) -> None
    """
    List videos.
    """
    ownerid = int(ownerid) if ownerid is not None else None  # neg/pos!
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    vkapi = initvkapi()
    kwargs = {
        'extended': 1,
        'offset': offset,
        'count': itemsperpage,
    }
    if ownerid is not None:  # neg/pos!
        kwargs['owner_id'] = int(ownerid)
    try:
        videos = vkapi.video.get(**kwargs)
    except vk.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if videos['count'] > offset + itemsperpage:
        videos['pagination'] = {
            'skipurl': buildurl(URLPATH_LISTVIDEOS, {'ownerid': ownerid}),
            'nexturl': buildurl(URLPATH_LISTVIDEOS, {'ownerid': ownerid, 'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(videos['count']) / itemsperpage))
        }
    xbmc.log('plugin.video.vk: Videos: {}'.format(videos))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if likedvideos['count'] > offset + itemsperpage:
        likedvideos['pagination'] = {
            'skipurl': buildurl(URLPATH_LISTLIKEDVIDEOS),
            'nexturl': buildurl(URLPATH_LISTLIKEDVIDEOS, {'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(likedvideos['count']) / itemsperpage))
        }
    xbmc.log('plugin.video.vk: Liked videos: {}'.format(likedvideos))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if albumvideos['count'] > offset + itemsperpage:
        albumvideos['pagination'] = {
            'skipurl': buildurl(URLPATH_LISTALBUMVIDEOS, {'albumid': albumid}),
            'nexturl': buildurl(URLPATH_LISTALBUMVIDEOS, {'albumid': albumid, 'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(albumvideos['count']) / itemsperpage))
        }
    xbmc.log('plugin.video.vk: Album videos: {}'.format(albumvideos))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if communityvideos['count'] > offset + itemsperpage:
        communityvideos['pagination'] = {
            'skipurl': buildurl(URLPATH_LISTCOMMUNITYVIDEOS, {'communityid': communityid}),
            'nexturl': buildurl(URLPATH_LISTCOMMUNITYVIDEOS, {'communityid': communityid, 'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(communityvideos['count']) / itemsperpage))
        }
    xbmc.log('plugin.video.vk: Community videos: {}'.format(communityvideos))
    # build list
    buildvideolist(URLPATH_LISTCOMMUNITYVIDEOS, communityvideos)


def buildvideolist(listtype, listdata):  # type: (str, dict) -> None
    """
    Build video list.
    """
    listitems = []
    thumbsizes = ['photo_1280', 'photo_800', 'photo_640', 'photo_320']
    if 'groups' in listdata:
        # list => dict searchable by video's owner_id, negative!
        listdata['groups'] = {str(-group['id']): group for group in listdata['groups']}
    # create pagination item
    if 'pagination' in listdata:
        pi = xbmcgui.ListItem(
            '[COLOR {0}]{1} ({2}/{3})[/COLOR]'.format(
                COLOR_ALT,
                ADDON.getLocalizedString(30034).encode('utf-8'),
                listdata['pagination']['page'] + 1,
                listdata['pagination']['lastpage']
            )
        )
        pi.addContextMenuItems(
            [
                # skip to page
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30035).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(
                            URLPATH_SKIPTOPAGE,
                            {
                                'page': listdata['pagination']['page'],
                                'lastpage': listdata['pagination']['lastpage'],
                                'skipurl': listdata['pagination']['skipurl'],
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
        if not video['is_favorite']:
            cmi += [
                # like video
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30053).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_LIKEVIDEO, {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            ]
        else:
            cmi += [
                # unlike video
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30054).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_UNLIKEVIDEO, {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            ]
        cmi += [
            # set albums
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30055).encode('utf-8')),
                'RunPlugin({0})'.format(
                    buildurl(URLPATH_ADDVIDEOTOALBUMS, {'ownerid': video['owner_id'], 'videoid': video['id']})
                )
            )
        ]
        if 'added_to_watchlist' not in video:
            cmi += [
                # add video to watchlist
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30056).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_ADDVIDEOTOWATCHLIST, {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            ]
        else:
            cmi += [
                # delete video from watchlist
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30057).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_DELETEVIDEOFROMWATCHLIST, {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            ]
        if listtype == URLPATH_LISTWATCHLIST:
            cmi += [
                # clear watchlist
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30058).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_CLEARWATCHLIST)
                    )
                )
            ]
        elif listtype == URLPATH_LISTPLAYEDVIDEOS:
            cmi += [
                # clear played videos
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30059).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(URLPATH_CLEARPLAYEDVIDEOS)
                    )
                )
            ]
        if video['owner_id'] < 0 and 'groups' in listdata:
            cmi += [
                # go to owning community (list community videos)
                (
                    '[COLOR {0}]{1} {2}[/COLOR]'.format(
                        COLOR_ALT,
                        ADDON.getLocalizedString(30036).encode('utf-8'),
                        listdata['groups'][str(video['owner_id'])]['name'].encode('utf-8')
                    ),
                    'Container.Update({0})'.format(
                        buildurl(URLPATH_LISTVIDEOS, {'ownerid': video['owner_id']})
                    )
                )
            ]
            if not listdata['groups'][str(video['owner_id'])]['is_member']:
                cmi += [
                    # follow owning community
                    (
                        '[COLOR {0}]{1} {2}[/COLOR]'.format(
                            COLOR_ALT,
                            ADDON.getLocalizedString(30037).encode('utf-8'),
                            listdata['groups'][str(video['owner_id'])]['name'].encode('utf-8')
                        ),
                        'RunPlugin({0})'.format(
                            buildurl(URLPATH_FOLLOWCOMMUNITY, {'communityid': video['owner_id']})
                        )
                    )
                ]
        cmi += [
            # search videos
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30083).encode('utf-8')),
                'Container.Update({0})'.format(
                    buildurl(URLPATH_LISTSEARCHEDVIDEOS)
                )
            ),
            # search by similar title
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30085).encode('utf-8')),
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
                ITEMTYPE_NOTFOLDER
            )
        )
    # force custom view mode for videos if enabled
    if ADDON.getSetting('forcevideoviewmode') == 'true':  # case sens!
        xbmc.executebuiltin('Container.SetViewMode({0})'.format(int(ADDON.getSetting('forcevideoviewmodeid'))))
    # set displaying in kodi
    xbmcplugin.setContent(SYSARGV['handle'], 'videos')
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route(URLPATH_PLAYVIDEO)
def playvideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Play video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # resolve playable streams via vk videoinfo url, find the best avail. quality
    vksession = initvksession()
    vi = vksession.requests_session.get(
        url='https://vk.com/al_video.php?act=show_inline&al=1&video={0}'.format(oidid),
        headers={'User-Agent': VKRESOLVER_UA}
    )
    xbmc.log('plugin.video.vk: Resolving video info: {}'.format(vi.content))
    try:
        resolvedstreams = {m[0]: m[1] for m in re.findall(r'"url(\d+)":"([^"]+)"', vi.content.replace('\\', ''))}
        bestquality = sorted(resolvedstreams.keys(), key=lambda k: int(k)).pop()
    except IndexError:
        xbmc.log('plugin.video.vk: Video resolving error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_RESOLVING)
    xbmc.log('plugin.video.vk: Playable streams resolved: {}.'.format(resolvedstreams))
    xbmc.log('plugin.video.vk: Best quality found: {}'.format(bestquality))
    # keep played video history, if enabled in settings
    if ADDON.getSetting('keepplayedvideohistory') == 'true':
        # request vk api
        vkapi = initvkapi(vksession)
        try:
            video = vkapi.video.get(extended=1, videos=oidid)['items'].pop()
        except vk.VkAPIError:
            xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
            raise AddonError(ERR_VKAPI)
        video.update(
            {
                'oidid': oidid,
                'lastPlayed': datetime.datetime.now().isoformat(),
            }
        )
        fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
        db = tinydb.TinyDB(fp)
        db.table(DBT_PLAYEDVIDEOS).upsert(
            video,
            tinydb.where('oidid') == oidid
        )
        xbmc.log('plugin.video.vk: Played videos db updated: {}'.format(video))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Video liked: {}'.format(oidid))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Video unliked: {}'.format(oidid))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Video added to albums: {}'.format(oidid))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # store video into db
    video.update(
        {
            'oidid': oidid,
            'added_to_watchlist': datetime.datetime.now().isoformat(),
        }
    )
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    db.table(DBT_WATCHLIST).upsert(
        video,
        tinydb.where('oidid') == oidid
    )
    xbmc.log('plugin.video.vk: Video added to watchlist: {}'.format(oidid))
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
    db.table(DBT_WATCHLIST).remove(
        tinydb.where('oidid') == oidid
    )
    xbmc.log('plugin.video.vk: Video deleted from watchlist: {}'.format(oidid))
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
    tinydb.TinyDB(fp).purge_table(DBT_WATCHLIST)
    xbmc.log('plugin.video.vk: Watchlist cleared.')
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
    tinydb.TinyDB(fp).purge_table(DBT_PLAYEDVIDEOS)
    xbmc.log('plugin.video.vk: Played videos cleared.')
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Albums: {}'.format(albums))
    listitems = []
    # create pagination item
    if albums['count'] > offset + itemsperpage:
        pi = xbmcgui.ListItem(
            '[COLOR {0}]{1} ({2}/{3})[/COLOR]'.format(
                COLOR_ALT,
                ADDON.getLocalizedString(30034).encode('utf-8'),
                int(offset / itemsperpage) + 1 + 1,  # nextpage
                int(math.ceil(float(albums['count']) / itemsperpage))  # lastpage
            )
        )
        pi.addContextMenuItems(
            [
                # skip to page
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30035).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(
                            URLPATH_SKIPTOPAGE,
                            {
                                'page': int(offset / itemsperpage) + 1,
                                'lastpage': int(math.ceil(float(albums['count']) / itemsperpage)),
                                'skipurl': buildurl(URLPATH_LISTALBUMS),
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
            '{0} [COLOR {1}]({2})[/COLOR]'.format(album['title'].encode('utf-8'), COLOR_ALT, int(album['count'])))
        # set art, if any
        if album['count'] > 0:
            li.setArt({'thumb': album['photo_320']})
        # before/after album ids for reordering
        beforeid = albums['items'][i - 1]['id'] if i > 0 else None
        afterid = albums['items'][i + 1]['id'] if i < len(albums['items']) - 1 else None
        # create context menu
        cmi = [
            # reorder album up
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30061).encode('utf-8')),
                'RunPlugin({0})'.format(buildurl(URLPATH_REORDERALBUM, {'albumid': album['id'], 'beforeid': beforeid}))
            ),
            # reorder album down
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30062).encode('utf-8')),
                'RunPlugin({0})'.format(buildurl(URLPATH_REORDERALBUM, {'albumid': album['id'], 'afterid': afterid}))
            ),
            # rename album
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30060).encode('utf-8')),
                'RunPlugin({0})'.format(buildurl(URLPATH_RENAMEALBUM, {'albumid': album['id']}))
            ),
            # delete album
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30063).encode('utf-8')),
                'RunPlugin({0})'.format(buildurl(URLPATH_DELETEALBUM, {'albumid': album['id']}))
            ),
            # create new album
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30064).encode('utf-8')),
                'RunPlugin({0})'.format(buildurl(URLPATH_CREATEALBUM))
            ),
            # search videos
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30083).encode('utf-8')),
                'Container.Update({0})'.format(buildurl(URLPATH_LISTSEARCHEDVIDEOS))  # cnt.upd!
            ),
        ]
        li.addContextMenuItems(cmi)
        listitems.append(
            (
                buildurl(URLPATH_LISTALBUMVIDEOS, {'albumid': album['id']}),
                li,
                ITEMTYPE_FOLDER
            )
        )
    # set displaying in kodi
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Album reordered: {}'.format(albumid))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Album renamed: {}'.format(albumid))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Album deleted: {}'.format(albumid))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Album created: {}'.format(album))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if communities['count'] > offset + itemsperpage:
        communities['pagination'] = {
            'skipurl': buildurl(URLPATH_LISTCOMMUNITIES),
            'nexturl': buildurl(URLPATH_LISTCOMMUNITIES, {'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(communities['count']) / itemsperpage))
        }
    xbmc.log('plugin.video.vk: Communities: {}'.format(communities))
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
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    # pagination data
    if likedcommunities['count'] > offset + itemsperpage:
        likedcommunities['pagination'] = {
            'skipurl': buildurl(URLPATH_LISTLIKEDCOMMUNITIES),
            'nexturl': buildurl(URLPATH_LISTLIKEDCOMMUNITIES, {'offset': offset + itemsperpage}),
            'page': int(offset / itemsperpage) + 1,
            'lastpage': int(math.ceil(float(likedcommunities['count']) / itemsperpage))
        }
    xbmc.log('plugin.video.vk: Liked communities: {}'.format(likedcommunities))
    # build list
    buildcommunitylist(URLPATH_LISTLIKEDCOMMUNITIES, likedcommunities)


def buildcommunitylist(listtype, listdata):  # type: (str, dict) -> None
    """
    Build community list.``
    """
    listitems = []
    # create pagination item
    if 'pagination' in listdata:
        pi = xbmcgui.ListItem(
            '[COLOR {0}]{1} ({2}/{3})[/COLOR]'.format(
                COLOR_ALT,
                ADDON.getLocalizedString(30034).encode('utf-8'),
                listdata['pagination']['page'] + 1,
                listdata['pagination']['lastpage']
            )
        )
        pi.addContextMenuItems(
            [
                # skip to page
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30035).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl(
                            URLPATH_SKIPTOPAGE,
                            {
                                'page': listdata['pagination']['page'],
                                'lastpage': listdata['pagination']['lastpage'],
                                'skipurl': listdata['pagination']['skipurl'],
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
    for community in listdata['items']:
        if listtype == URLPATH_LISTLIKEDCOMMUNITIES:
            community['id'] = community['id'].split('_')[2]
        # create community item
        li = xbmcgui.ListItem(
            label=community['title' if listtype == URLPATH_LISTLIKEDCOMMUNITIES else 'name'].encode('utf-8')
        )
        # set art
        li.setArt(
            {
                'thumb': community['photo_200']
            }
        )
        # create context menu
        cmi = []
        if listtype == URLPATH_LISTLIKEDCOMMUNITIES:
            cmi += [
                # unlike community
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30071).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl(URLPATH_UNLIKECOMMUNITY, {'communityid': community['id']}))
                )
            ]
        else:
            cmi += [
                # like community
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30070).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl(URLPATH_LIKECOMMUNITY, {'communityid': community['id']}))
                )
            ]
        cmi += [
            # unfollow community
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30072).encode('utf-8')),
                'RunPlugin({0})'.format(buildurl(URLPATH_UNFOLLOWCOMMUNITY, {'communityid': community['id']}))
            ),
            # search videos
            (
                '[COLOR {0}]{1}[/COLOR]'.format(COLOR_ALT, ADDON.getLocalizedString(30083).encode('utf-8')),
                'Container.Update({0})'.format(buildurl(URLPATH_LISTSEARCHEDVIDEOS))  # cnt.upd!
            ),
        ]
        li.addContextMenuItems(cmi)
        listitems.append(
            (
                buildurl(URLPATH_LISTCOMMUNITYVIDEOS, {'communityid': community['id']}),
                li,
                ITEMTYPE_FOLDER
            )
        )
    # set displaying in kodi
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


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
    except vk.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Community liked: {}'.format(communityid))
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
    except vk.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Community unliked: {}'.format(communityid))
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
    except vk.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Community followed: {}'.format(communityid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route(URLPATH_UNFOLLOWCOMMUNITY)
def unfollowcommunity(communityid):  # type: (int) -> None
    """
    Unfollow community.
    """
    communityid = abs(int(communityid))  # positive id!
    # request vk api
    vkapi = initvkapi()
    try:
        vkapi.groups.leave(
            group_id=communityid
        )
    except vk.VkAPIError:
        xbmc.log('plugin.video.vk: VK API error!', level=xbmc.LOGERROR)
        raise AddonError(ERR_VKAPI)
    xbmc.log('plugin.video.vk: Community unfollowed: {}'.format(communityid))
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
