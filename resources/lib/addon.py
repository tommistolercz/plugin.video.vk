# coding=utf-8

__all__ = []
__version__ = "1.3.0-dev"

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
VK_API_VERSION = '5.92'

# etc
ALT_COLOR = 'blue'

# global vars
ROUTING = {}
SYSARGV = {}
ADDON = None
VKSESSION = None
VKAPI = None


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


def initvksession():  # type: () -> vk.AuthSession
    """
    Initialize VK session.
    """
    if ADDON.getSetting('vkuseraccesstoken') == '':
        # ask user for entering vk credentials for authorizing add-on
        login = xbmcgui.Dialog().input(ADDON.getLocalizedString(30030).encode('utf-8'))
        pswd = xbmcgui.Dialog().input(ADDON.getLocalizedString(30031).encode('utf-8'),
                                      option=xbmcgui.ALPHANUM_HIDE_INPUT)
        if not login or not pswd:
            xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK authorization error!'), level=xbmc.LOGERROR)
            raise AddonError(ERR_VK_AUTH)
        # create a new vk session
        try:
            vksession = vk.AuthSession(VK_API_APP_ID, login, pswd, VK_API_SCOPE)
        except vk.VkAuthError:
            xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK authorization error!'), level=xbmc.LOGERROR)
            raise AddonError(ERR_VK_AUTH)
        # save obtained token + cookies
        ADDON.setSetting('vkuseraccesstoken', vksession.access_token)
        savecookies(vksession.auth_session.cookies)
    else:
        # restore existing vk session (using token)
        try:
            vksession = vk.Session(ADDON.getSetting('vkuseraccesstoken'))
        except vk.VkAuthError:
            xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK authorization error!'), level=xbmc.LOGERROR)
            raise AddonError(ERR_VK_AUTH)
        # load cookies
        vksession.requests_session.cookies = loadcookies()
    return vksession


def initvkapi():  # type: () -> vk.API
    """
    Initialize VK API.
    """
    try:
        vkapi = vk.API(VKSESSION, v=VK_API_VERSION, lang=VK_API_LANG)
        vkapi.stats.trackVisitor()
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
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
    # call handler
    try:
        handler = ROUTING[urlpath]
    except KeyError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'Routing error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_ROUTING)
    handler(**urlargs)


def beautify(text):  # type: (str) -> str
    """
    Beautify text for output.
    """
    # make it wrapable
    text = text.replace('.', ' ').replace('_', ' ')
    return text


# common


@route('/')
def listaddonmenu():  # type: () -> None
    """
    List add-on menu.
    """
    # collect menu counters from db and vkapi
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    counters = {
        'searchhistory': len(db.table(DB_TABLE_SEARCHHISTORY)),
        'playedvideos': len(db.table(DB_TABLE_PLAYEDVIDEOS)),
        'watchlist': len(db.table(DB_TABLE_WATCHLIST)),
    }
    try:
        counters.update(VKAPI.execute.getMenuCounters())
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # create kodi list
    isfolder = True
    kodilist = [
        (
            buildurl('/searchvideos'),
            xbmcgui.ListItem(
                ADDON.getLocalizedString(30040).encode('utf-8')
            ),
            isfolder
        ),
        (
            buildurl('/searchhistory'),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30041).encode('utf-8'), ALT_COLOR, counters['searchhistory']
                )
            ),
            isfolder
        ),
        (
            buildurl('/playedvideos'),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30047).encode('utf-8'), ALT_COLOR, counters['playedvideos']
                )
            ),
            isfolder
        ),
        (
            buildurl('/watchlist'),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30048).encode('utf-8'), ALT_COLOR, counters['watchlist']
                )
            ),
            isfolder
        ),
        (
            buildurl('/videos'),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30042).encode('utf-8'), ALT_COLOR, counters['videos']
                )
            ),
            isfolder
        ),
        (
            buildurl('/likedvideos'),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30043).encode('utf-8'), ALT_COLOR, counters['likedvideos']
                )
            ),
            isfolder
        ),
        (
            buildurl('/albums'),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30044).encode('utf-8'), ALT_COLOR, counters['albums']
                )
            ),
            isfolder
        ),
        (
            buildurl('/communities'),
            xbmcgui.ListItem(
                '{0} [COLOR {1}]({2})[/COLOR]'.format(
                    ADDON.getLocalizedString(30045).encode('utf-8'), ALT_COLOR, counters['communities']
                )
            ),
            isfolder
        ),
        (
            buildurl('/likedcommunities'),
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


@route('/logout')
def logout():  # type: () -> None
    """
    Logout user.
    """
    # delete cookies + reset user access token
    deletecookies()
    ADDON.setSetting('vkuseraccesstoken', '')
    xbmcgui.Dialog().notification(ADDON.getAddonInfo('id'), ADDON.getLocalizedString(30032).encode('utf-8'))


# search history


@route('/searchhistory')
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
                        buildurl('/deletesearch', {'searchid': search.doc_id})
                    )
                ),
                # search videos
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051).encode('utf-8')),
                    'Container.Update({0})'.format(
                        buildurl('/searchvideos')
                    )
                ),
                # search similar
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30080).encode('utf-8')),
                    'Container.Update({0})'.format(
                        buildurl('/searchvideos', {'similarq': search['q'].encode('utf-8')})
                    )
                ),
            ]
        )
        kodilist.append(
            (
                buildurl('/searchvideos', {'q': search['q'].encode('utf-8')}),
                li,
                isfolder
            )
        )
    # paginator item
    if int(searchhistory['count']) > offset + itemsperpage:
        kodilist.append(
            (
                buildurl('/searchhistory', {'offset': offset + itemsperpage}),
                xbmcgui.ListItem(
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30050).encode('utf-8'))
                ),
                True
            )
        )
    # set displaying in Kodi
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], kodilist, len(kodilist))
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route('/deletesearch')
def deletesearch(searchid):  # type: (int) -> None
    """
    Delete search from search history.
    """
    searchid = int(searchid)
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(
        ADDON.getLocalizedString(30081).encode('utf-8'),
        ADDON.getLocalizedString(30082).encode('utf-8')
    ):
        return
    # query db for deleting
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    db.table(DB_TABLE_SEARCHHISTORY).remove(doc_ids=[searchid])
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route('/clearsearchhistory')
def clearsearchhistory():  # type: () -> None
    """
    Clear search history.
    """
    pass


# videos


def buildvideolist(listdata):  # type: (dict) -> None
    """
    Build video list:

    - ``/searchvideos``
    - ``/videos``
    - ``/likedvideos``
    - ``/albumvideos``
    - ``/communityvideos``
    - ``/playedvideos``
    - ``/watchlist``
    """
    # create list
    listitems = []
    beautified = {}
    isfolder = False
    for video in listdata['items']:
        # create video item
        beautified['title'] = beautify(video['title'].encode('utf-8'))
        li = xbmcgui.ListItem(beautified['title'])
        # set isplayable
        li.setProperty('IsPlayable', 'true')
        # set infolabels
        li.setInfo(
            'video',
            {
                'title': beautified['title'],
                'plot': video['description'].encode('utf-8'),
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
        # like video / unlike video
        if not video['is_favorite']:
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30053).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl('/likevideo', {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            )
        else:
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30054).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl('/unlikevideo', {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            )
        # add video to watchlist / delete video from watchlist
        if 'added_to_watchlist' not in video:
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30056).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl('/addvideotowatchlist', {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            )
        else:
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30057).encode('utf-8')),
                    'RunPlugin({0})'.format(
                        buildurl('/deletevideofromwatchlist', {'ownerid': video['owner_id'], 'videoid': video['id']})
                    )
                )
            )
        # add video to albums
        cmi.append(
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30055).encode('utf-8')),
                'RunPlugin({0})'.format(
                    buildurl('/addvideotoalbums', {'ownerid': video['owner_id'], 'videoid': video['id']})
                )
            )
        )
        # search videos
        cmi.append(
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051).encode('utf-8')),
                'Container.Update({0})'.format(
                    buildurl('/searchvideos')
                )  # cnt.upd!
            )
        )
        # search similar
        cmi.append(
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30080).encode('utf-8')),
                'Container.Update({0})'.format(
                    buildurl('/searchvideos', {'similarq': beautified['title']})
                )  # cnt.upd!
            )
        )
        li.addContextMenuItems(cmi)
        # add video item to list
        listitems.append(
            (
                buildurl('/playvideo', {'ownerid': video['owner_id'], 'videoid': video['id']}),
                li,
                isfolder
            )
        )
    # paginator item
    if 'next' in listdata:
        listitems.append(
            (
                listdata['next']['url'],
                xbmcgui.ListItem(
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30050).encode('utf-8'))),
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


@route('/searchvideos')
def listsearchedvideos(q='', similarq='', offset=0):  # type: (str, str, int) -> None
    """
    List searched videos.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # if q not passed, ask user for entering a new query / editing similar one
    if not q:
        q = xbmcgui.Dialog().input(ADDON.getLocalizedString(30051).encode('utf-8'), defaultt=similarq)
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
        'count': itemsperpage,
    }
    if ADDON.getSetting('searchduration') == '1':
        kwargs['longer'] = int(ADDON.getSetting('searchdurationmins')) * 60
    elif ADDON.getSetting('searchduration') == '2':
        kwargs['shorter'] = int(ADDON.getSetting('searchdurationmins')) * 60
    try:
        searchedvideos = VKAPI.video.search(**kwargs)
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(searchedvideos['count']) > offset + itemsperpage:
        searchedvideos['next'] = {
            'url': buildurl('/searchvideos', {'q': q, 'offset': offset + itemsperpage}),
        }
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
        # notify search results count
        xbmcgui.Dialog().notification(
            ADDON.getAddonInfo('id'),
            ADDON.getLocalizedString(30052).encode('utf-8').format(searchedvideos['count'])
        )
    # build list
    buildvideolist(searchedvideos)


@route('/playedvideos')
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
    if int(playedvideos['count']) > offset + itemsperpage:
        playedvideos['next'] = {
            'url': buildurl('/playedvideos', {'offset': offset + itemsperpage}),
        }
    # build list
    buildvideolist(playedvideos)


@route('/watchlist')
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
    if int(watchlist['count']) > offset + itemsperpage:
        watchlist['next'] = {
            'url': buildurl('/watchlist', {'offset': offset + itemsperpage}),
        }
    # build list
    buildvideolist(watchlist)


@route('/videos')
def listvideos(offset=0):  # type: (int) -> None
    """
    List videos.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    try:
        videos = VKAPI.video.get(
            extended=1,
            offset=offset,
            count=itemsperpage,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(videos['count']) > offset + itemsperpage:
        videos['next'] = {
            'url': buildurl('/videos', {'offset': offset + itemsperpage}),
        }
    # build list
    buildvideolist(videos)


@route('/likedvideos')
def listlikedvideos(offset=0):  # type: (int) -> None
    """
    List liked videos.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    try:
        likedvideos = VKAPI.fave.getVideos(
            extended=1,
            offset=offset,
            count=itemsperpage,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(likedvideos['count']) > offset + itemsperpage:
        likedvideos['next'] = {
            'url': buildurl('/likedvideos', {'offset': offset + itemsperpage}),
        }
    # build list
    buildvideolist(likedvideos)


@route('/albumvideos')
def listalbumvideos(albumid, offset=0):  # type: (int, int) -> None
    """
    List album videos.
    """
    albumid = int(albumid)
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    try:
        albumvideos = VKAPI.video.get(
            extended=1,
            album_id=albumid,
            offset=offset,
            count=itemsperpage,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(albumvideos['count']) > offset + itemsperpage:
        albumvideos['next'] = {
            'url': buildurl('/albumvideos', {'albumid': albumid, 'offset': offset + itemsperpage}),
        }
    # build list
    buildvideolist(albumvideos)


@route('/communityvideos')
def listcommunityvideos(communityid, offset=0):  # type: (int, int) -> None
    """
    List community videos.
    """
    communityid = int(communityid)
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    try:
        communityvideos = VKAPI.video.get(
            extended=1,
            owner_id=(-1 * communityid),  # neg.id required!
            offset=offset,
            count=itemsperpage,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(communityvideos['count']) > offset + itemsperpage:
        communityvideos['next'] = {
            'url': buildurl('/communityvideos', {'communityid': communityid, 'offset': offset + itemsperpage}),
        }
    # build list
    buildvideolist(communityvideos)


@route('/playvideo')
def playvideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Play video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # request vk api for video
    try:
        video = VKAPI.video.get(extended=1, videos=oidid)['items'].pop()
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # resolve playable streams via vk videoinfo url
    vi = VKSESSION.requests_session.get(
        url='https://vk.com/al_video.php?act=show_inline&al=1&video={0}'.format(oidid),
        headers={'User-Agent': xbmc.getUserAgent()},  # +cookies required (sent autom.)
    )
    matches = re.findall(r'"url(\d+)":"([^"]+)"', vi.text.replace('\\', ''))
    playables = {}
    for m in matches:
        qual = int(m[0])
        playables[qual] = m[1]
    if playables:
        # streams resolved, use one of best quality
        maxqual = max(playables.keys())
    else:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'Video resolving error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_RESOLVING)
    # keep played video history, if enabled in settings
    if ADDON.getSetting('keepplayedvideohistory') == 'true':
        video.update(
            {
                'oidid': oidid,
                'lastPlayed': datetime.datetime.now().isoformat(),
            }
        )
        fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
        db = tinydb.TinyDB(fp)
        db.table(DB_TABLE_PLAYEDVIDEOS).upsert(video, tinydb.where('oidid') == oidid)
    # create playable item for kodi player
    li = xbmcgui.ListItem(path=playables[maxqual])
    xbmcplugin.setContent(SYSARGV['handle'], 'videos')
    xbmcplugin.setResolvedUrl(SYSARGV['handle'], True, li)


@route('/likevideo')
def likevideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Like video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    # request vk api
    try:
        VKAPI.likes.add(
            type='video',
            owner_id=ownerid,
            item_id=videoid,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route('/unlikevideo')
def unlikevideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Unlike video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    # request vk api
    try:
        VKAPI.likes.delete(
            type='video',
            owner_id=ownerid,
            item_id=videoid,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route('/addvideotoalbums')
def addvideotoalbums(ownerid, videoid):  # type: (int, int) -> None
    """
    Add video to albums.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    # request vk api
    try:
        # get user albums
        albums = VKAPI.video.getAlbums(
            need_system=0,
            offset=0,
            count=100,
        )
        # get list of album ids for video
        albumids = VKAPI.video.getAlbumsByVideo(
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
            VKAPI.video.removeFromAlbum(
                owner_id=ownerid,
                video_id=videoid,
                album_ids=albumids
            )
        # add new sel album ids if any
        if len(newalbumids) > 0:
            VKAPI.video.addToAlbum(
                owner_id=ownerid,
                video_id=videoid,
                album_ids=newalbumids
            )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route('/addvideotowatchlist')
def addvideotowatchlist(ownerid, videoid):  # type: (int, int) -> None
    """
    Add video to watchlist.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # request vk api for video
    try:
        video = VKAPI.video.get(
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


@route('/deletevideofromwatchlist')
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
            ADDON.getLocalizedString(30058).encode('utf-8')
    ):
        return
    # query db for deleting
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp)
    db.table(DB_TABLE_WATCHLIST).remove(
        tinydb.where('oidid') == oidid
    )
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route('/clearplayedvideos')
def clearplayedvideos():  # type: () -> None
    """
    Clear played videos.
    """
    pass


@route('/clearwatchlist')
def clearwatchlist():  # type: () -> None
    """
    Clear watchlist.
    """
    pass


# video albums


@route('/albums')
def listalbums(offset=0):  # type: (int) -> None
    """
    List albums.
    """
    offset = int(offset)
    # workaround due api's maxperpage=100
    albumsperpage = int(ADDON.getSetting('itemsperpage')) if int(ADDON.getSetting('itemsperpage')) <= 100 else 100
    # request vk api for albums
    try:
        albums = VKAPI.video.getAlbums(
            extended=1,
            offset=offset,
            count=albumsperpage,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
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
                    'RunPlugin({0})'.format(buildurl('/reorderalbum', {'albumid': album['id'], 'beforeid': beforeid}))
                ),
                # reorder album down
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30062).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl('/reorderalbum', {'albumid': album['id'], 'afterid': afterid}))
                ),
                # rename album
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30060).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl('/renamealbum', {'albumid': album['id']}))
                ),
                # delete album
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30063).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl('/deletealbum', {'albumid': album['id']}))
                ),
                # create new album
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30065).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl('/createalbum'))
                ),
                # search videos
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051).encode('utf-8')),
                    'Container.Update({0})'.format(buildurl('/searchvideos'))  # cnt.upd!
                ),
            ]
        )
        listitems.append(
            (
                buildurl('/albumvideos', {'albumid': album['id']}),
                li,
                isfolder
            )
        )
    # paginator item
    if offset + albumsperpage < albums['count']:
        listitems.append(
            (
                buildurl('/albums', {'offset': offset + albumsperpage}),
                xbmcgui.ListItem(
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30050).encode('utf-8'))),
                True
            )
        )
    # show album list in kodi, even if empty
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route('/reorderalbum')
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
        VKAPI.video.reorderAlbums(
            album_id=albumid,
            **reorder
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route('/renamealbum')
def renamealbum(albumid):  # type: (int) -> None
    """
    Rename album.
    """
    albumid = int(albumid)
    # request vk api for album data
    try:
        album = VKAPI.video.getAlbumById(
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
        VKAPI.video.editAlbum(
            album_id=albumid,
            title=newtitle,
            privacy=3  # 3=onlyme
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route('/deletealbum')
def deletealbum(albumid):  # type: (int) -> None
    """
    Delete album.
    """
    albumid = int(albumid)
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(
            ADDON.getLocalizedString(30063).encode('utf-8'),
            ADDON.getLocalizedString(30064).encode('utf-8')
    ):
        return
    # request vk api
    try:
        VKAPI.video.deleteAlbum(
            album_id=albumid,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route('/createalbum')
def createalbum():  # type: () -> None
    """
    Create album.
    """
    # ask user for new album title
    albumtitle = xbmcgui.Dialog().input(ADDON.getLocalizedString(30065).encode('utf-8'))
    if not albumtitle:
        return
    # request vk api
    try:
        VKAPI.video.addAlbum(
            title=albumtitle,
            privacy=3,  # 3=onlyme
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


# communities


def buildcommunitylist(listtype, listdata):  # type: (str, dict) -> None
    """
    Build community list:

    - ``/communities``
    - ``/likedcommunities``
    """
    # create list
    listitems = []
    isfolder = True
    namekey = 'title' if listtype == '/likedcommunities' else 'name'
    for community in listdata['items']:
        if listtype == '/likedcommunities':
            community['id'] = community['id'].split('_')[2]
        # create community item
        li = xbmcgui.ListItem(community[namekey].encode('utf-8'))
        # set art
        li.setArt({'thumb': community['photo_200']})
        # create context menu
        cmi = []
        # unlike/like community
        if listtype == '/likedcommunities':
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30071).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl('/unlikecommunity', {'communityid': community['id']}))
                )
            )
        else:
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30070).encode('utf-8')),
                    'RunPlugin({0})'.format(buildurl('/likecommunity', {'communityid': community['id']}))
                )
            )
        # unfollow community
        cmi.append(
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30072).encode('utf-8')),
                'RunPlugin({0})'.format(buildurl('/unfollowcommunity', {'communityid': community['id']}))
            )
        )
        # search videos
        cmi.append(
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051).encode('utf-8')),
                'Container.Update({0})'.format(buildurl('/searchvideos'))  # cnt.upd!
            )
        )
        li.addContextMenuItems(cmi)
        # add item to list
        listitems.append(
            (
                buildurl('/communityvideos', {'communityid': '{0}'.format(community['id'])}),
                li,
                isfolder
            )
        )
    # paginator item
    if 'next' in listdata:
        listitems.append(
            (
                listdata['next']['url'],
                xbmcgui.ListItem(
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30050).encode('utf-8'))),
                True
            )
        )
    # show list in kodi, even if empty
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route('/communities')
def listcommunities(offset=0):  # type: (int) -> None
    """
    List communities.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    try:
        communities = VKAPI.groups.get(
            extended=1,
            offset=offset,
            count=itemsperpage,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(communities['count']) > offset + itemsperpage:
        communities['next'] = {
            'url': buildurl('/communities', {'offset': offset + itemsperpage}),
        }
    # build list
    buildcommunitylist('/communities', communities)


@route('/likedcommunities')
def listlikedcommunities(offset=0):  # type: (int) -> None
    """
    List liked communities.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # request vk api
    try:
        likedcommunities = VKAPI.fave.getLinks(
            offset=offset,
            count=itemsperpage,
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(likedcommunities['count']) > offset + itemsperpage:
        likedcommunities['next'] = {
            'url': buildurl('/likedcommunities', {'offset': offset + itemsperpage}),
        }
    # build list
    buildcommunitylist('/likedcommunities', likedcommunities)


@route('/likecommunity')
def likecommunity(communityid):  # type: (int) -> None
    """
    Like community.
    """
    communityid = int(communityid)
    # request vk api
    try:
        VKAPI.fave.addGroup(
            group_id=communityid
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route('/unlikecommunity')
def unlikecommunity(communityid):  # type: (int) -> None
    """
    Unlike community.
    """
    communityid = int(communityid)
    # request vk api
    try:
        VKAPI.fave.removeGroup(
            group_id=communityid
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
    # refresh content
    xbmc.executebuiltin('Container.Refresh()')


@route('/unfollowcommunity')
def unfollowcommunity(communityid):  # type: (int) -> None
    """
    Unfollow community.
    """
    communityid = int(communityid)
    # request vk api
    try:
        VKAPI.groups.leave(
            group_id=communityid
        )
    except vk.VkAPIError:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), 'VK API error!'), level=xbmc.LOGERROR)
        raise AddonError(ERR_VK_API)
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
        VKSESSION = initvksession()
        VKAPI = initvkapi()
        dispatch()
    except AddonError as e:
        xbmcgui.Dialog().notification(
            ADDON.getAddonInfo('id'), ADDON.getLocalizedString(e.errid).encode('utf-8'),
            icon=xbmcgui.NOTIFICATION_ERROR
        )
