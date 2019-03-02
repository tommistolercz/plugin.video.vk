# coding=utf-8
# import web_pdb; web_pdb.set_trace()
__all__ = []


# builtins
import datetime
import os
import pickle
import re
import sys
import urllib  # py2
import urlparse  # py2

# kodi api
import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin

# 3rd party modules
import tinydb
import vk


# addon error ids
ERR_VK_AUTH = 30020
ERR_VK_API = 30021
ERR_ROUTING = 30022
ERR_DATA_FILE = 30023
ERR_RESOLVING = 30024

# addon data filenames
FILENAME_DB = 'db.json'
FILENAME_COOKIES = 'cookies.txt'

# addon db tables
TBL_ADDON_REQUESTS = 'addonRequests'
TBL_SEARCH_HISTORY = 'searchHistory'
TBL_PLAYED_VIDEOS = 'playedVideos'

# vk api config
VK_API_APP_ID = '6432748'
VK_API_SCOPE = 'email,friends,groups,offline,stats,status,video,wall'
VK_API_LANG = 'ru'
VK_API_VERSION = '5.92'

# etc
ALT_COLOR = 'blue'
ITEM_TYPE_FOLDER = True
ITEM_TYPE_NOTFOLDER = False

# global vars
ROUTING = {}
SYSARGV = {}
ADDON = None
DB = None
VKSESSION = None
VKAPI = None


class AddonError(Exception):
    """
    Exception class for addon errors.
    """
    def __init__(self, errid):  # type: (int) -> None
        self.errid = errid


def inittinydb():  # type: () -> tinydb.TinyDB
    """
    Initialize TinyDB (create a new data file if doesn't exist).
    """
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_DB))
    db = tinydb.TinyDB(fp, indent=4, sort_keys=False)
    xbmc.log('{0}: TinyDB initialized: {1}'.format(ADDON.getAddonInfo('id'), fp))
    return db


def initvksession():  # type: () -> vk.AuthSession
    """
    Initialize VK session.
    """
    if ADDON.getSetting('vkuseraccesstoken') == '':
        # ask user for entering vk credentials for authorizing addon
        login = xbmcgui.Dialog().input(ADDON.getLocalizedString(30030))
        pswd = xbmcgui.Dialog().input(ADDON.getLocalizedString(30031), option=xbmcgui.ALPHANUM_HIDE_INPUT)
        if not login or not pswd:
            raise AddonError(ERR_VK_AUTH)
        # create a new vk session
        try:
            vksession = vk.AuthSession(VK_API_APP_ID, login, pswd, VK_API_SCOPE)
        except vk.VkAuthError:
            raise AddonError(ERR_VK_AUTH)
        xbmc.log('{0}: VK session created.'.format(ADDON.getAddonInfo('id')))
        # save obtained token + save cookies
        ADDON.setSetting('vkuseraccesstoken', vksession.access_token)
        savecookies(vksession.auth_session.cookies)
    else:
        # restore existing vk session (using token)
        try:
            vksession = vk.Session(ADDON.getSetting('vkuseraccesstoken'))
        except vk.VkAuthError:
            raise AddonError(ERR_VK_AUTH)
        xbmc.log('{0}: VK session restored using token.'.format(ADDON.getAddonInfo('id')))
        # load cookies
        vksession.requests_session.cookies = loadcookies()
    return vksession


def savecookies(cookiejar):  # type: (object) -> None
    """
    Save cookiejar object to addon data file (truncate if exists).
    """
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_COOKIES))
    try:
        with open(fp, 'wb') as f:
            pickle.dump(cookiejar, f)
    except OSError:
        raise AddonError(ERR_DATA_FILE)
    xbmc.log('{0}: Cookies saved: {1}'.format(ADDON.getAddonInfo('id'), fp))


def loadcookies():  # type: () -> object
    """
    Load cookiejar object from addon data file (must exist since auth).
    """
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_COOKIES))
    try:
        with open(fp, 'rb') as f:
            cookiejar = pickle.load(f)
    except OSError:
        raise AddonError(ERR_DATA_FILE)
    xbmc.log('{0}: Cookies loaded: {1}'.format(ADDON.getAddonInfo('id'), fp))
    return cookiejar


def deletecookies():  # type: () -> None
    """
    Delete cookies addon data file.
    """
    fp = str(os.path.join(xbmc.translatePath(ADDON.getAddonInfo('profile')), FILENAME_COOKIES))
    try:
        os.remove(fp)
    except os.error:
        raise AddonError(ERR_DATA_FILE)
    xbmc.log('{0}: Cookies deleted: {1}'.format(ADDON.getAddonInfo('id'), fp))


def initvkapi():  # type: () -> vk.API
    """
    Initialize VK API.
    """
    try:
        # create api object
        vkapi = vk.API(VKSESSION, v=VK_API_VERSION, lang=VK_API_LANG)
        _ = vkapi.stats.trackVisitor()
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: VK API initialized.'.format(ADDON.getAddonInfo('id')))
    return vkapi


def buildurl(urlpath, urlargs=None):  # type: (str, dict) -> str
    """
    Build addon url.
    """
    url = 'plugin://{0}{1}'.format(ADDON.getAddonInfo('id'), urlpath)
    if urlargs:
        url += '?{0}'.format(urllib.urlencode(urlargs))
    xbmc.log('{0}: Addon url built: {1}'.format(ADDON.getAddonInfo('id'), url))
    return url


def parseurl():  # type: () -> tuple
    """
    Parse addon url.
    """
    urlpath = str(urlparse.urlsplit(SYSARGV['path'])[2])
    urlargs = {}
    if SYSARGV['qs'].startswith('?'):
        urlargs = urlparse.parse_qs(SYSARGV['qs'].lstrip('?'))
        for k, v in list(urlargs.items()):
            urlargs[k] = v.pop()
    parsedurl = (urlpath, urlargs)
    xbmc.log('{0}: Addon url parsed: {1}'.format(ADDON.getAddonInfo('id'), parsedurl))
    return parsedurl


def route(urlpath):  # type: (str) -> callable(object)
    """
    Register a route (set callable handler for given urlpath).
    """
    def sethandler(handler):  # type: (callable(object)) -> callable(object)
        ROUTING.update({urlpath: handler})
        return handler
    return sethandler


def dispatch():  # type: () -> None
    """
    Dispatch routing.
    """
    # parse addon url
    urlpath, urlargs = parseurl()
    # update addon requests db with the last request
    lastrequest = {
        'dt': datetime.datetime.now().isoformat(),
        'urlpath': urlpath,
        'urlargs': urlargs,
    }
    _ = DB.table(TBL_ADDON_REQUESTS).insert(lastrequest)
    xbmc.log('{0}: Addon requests db updated: {1}'.format(ADDON.getAddonInfo('id'), lastrequest))
    # call handler
    try:
        handler = ROUTING[urlpath]
    except KeyError:
        raise AddonError(ERR_ROUTING)
    xbmc.log('{0}: Routing dispatched: {1}'.format(ADDON.getAddonInfo('id'), handler.__name__))
    handler(**urlargs)


# common


@route('/')
def listmenu():  # type: () -> None
    """
    List menu.
    """
    # collect counters
    try:
        counters = dict(
            VKAPI.execute.getMenuCounters(),
            searchhistory=len(DB.table(TBL_SEARCH_HISTORY)),
            playedvideos=len(DB.table(TBL_PLAYED_VIDEOS)),
        )
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Counters: {1}'.format(ADDON.getAddonInfo('id'), counters))
    # create list items
    listitems = [
        # search videos
        (
            buildurl('/searchvideos'),
            xbmcgui.ListItem('{0}'.format(ADDON.getLocalizedString(30040))),
            ITEM_TYPE_FOLDER
        ),
        # search history
        (
            buildurl('/searchhistory'),
            xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30041), ALT_COLOR, counters['searchhistory'])),
            ITEM_TYPE_FOLDER
        ),
        # played videos
        (
            buildurl('/playedvideos'),
            xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30047), ALT_COLOR, counters['playedvideos'])),
            ITEM_TYPE_FOLDER
        ),
        # videos
        (
            buildurl('/videos'),
            xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30042), ALT_COLOR, counters['videos'])),
            ITEM_TYPE_FOLDER
        ),
        # liked videos
        (
            buildurl('/likedvideos'),
            xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30043), ALT_COLOR, counters['likedvideos'])),
            ITEM_TYPE_FOLDER
        ),
        # albums
        (
            buildurl('/albums'),
            xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30044), ALT_COLOR, counters['albums'])),
            ITEM_TYPE_FOLDER
        ),
        # communities
        (
            buildurl('/communities'),
            xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30045), ALT_COLOR, counters['communities'])),
            ITEM_TYPE_FOLDER
        ),
        # liked communities
        (
            buildurl('/likedcommunities'),
            xbmcgui.ListItem('{0} [COLOR {1}]({2})[/COLOR]'.format(ADDON.getLocalizedString(30046), ALT_COLOR, counters['likedcommunities'])),
            ITEM_TYPE_FOLDER
        ),
    ]
    # show list in kodi
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route('/logout')
def logout():  # type: () -> None
    """
    Logout user.
    """
    # delete cookies + reset user access token
    deletecookies()
    ADDON.setSetting('vkuseraccesstoken', '')
    xbmc.log('{0}: User logged out.'.format(ADDON.getAddonInfo('id')))
    xbmcgui.Dialog().notification(ADDON.getAddonInfo('id'), ADDON.getLocalizedString(30032))


# search history


@route('/searchhistory')
def listsearchhistory():  # type: () -> None
    """
    List search history.
    """
    # query db for search history list, empty if no data
    searchhistory = {
        'count': len(DB.table(TBL_SEARCH_HISTORY)),
        'items': DB.table(TBL_SEARCH_HISTORY).all(),
    }
    xbmc.log('{0}: Search history: {1}'.format(ADDON.getAddonInfo('id'), searchhistory))
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
                    'RunPlugin({0})'.format(buildurl('/deletesearch', {'searchid': search.doc_id}))
                ),
                # search videos
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051)),
                    'Container.Update({0})'.format(buildurl('/searchvideos'))  # upd.required!
                ),
                # search similar
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30080)),
                    'Container.Update({0})'.format(buildurl('/searchvideos', {'similarq': search['q']}))  # upd.required!
                ),
            ]
        )
        # add item to list
        listitems.append(
            (
                buildurl('/searchvideos', {'q': search['q']}),
                li,
                ITEM_TYPE_FOLDER
            )
        )
    # show list in kodi, even if empty
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route('/deletesearch')
def deletesearch(searchid):  # type: (int) -> None
    """
    Delete search from search history.
    """
    searchid = int(searchid)
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(ADDON.getLocalizedString(30081), ADDON.getLocalizedString(30082)):
        return
    # query db for deleting
    _ = DB.table(TBL_SEARCH_HISTORY).remove(doc_ids=[searchid])
    xbmc.log('{0}: Search deleted: {1}'.format(ADDON.getAddonInfo('id'), searchid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


# videos


@route('/searchvideos')
def searchvideos(q='', similarq='', offset=0):  # type: (str, str, int) -> None
    """
    Search videos.
    """
    offset = int(offset)
    itemsperpage = int(ADDON.getSetting('itemsperpage'))
    # if q not passed, ask user for entering a new query / editing similar one
    if not q:
        q = xbmcgui.Dialog().input(ADDON.getLocalizedString(30051), defaultt=similarq)
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
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(searchedvideos['count']) > offset + itemsperpage:
        searchedvideos['next'] = {
            'url': buildurl('/searchvideos', {'q': q, 'similarq': similarq, 'offset': offset + itemsperpage}),
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
        _ = DB.table(TBL_SEARCH_HISTORY).upsert(lastsearch, tinydb.where('q') == lastsearch['q'])
        xbmc.log('{0}: Search history db updated: {1}'.format(ADDON.getAddonInfo('id'), lastsearch))
        # notify search results count
        xbmcgui.Dialog().notification(ADDON.getAddonInfo('id'), ADDON.getLocalizedString(30052).format(searchedvideos['count']))
    # build list
    buildvideolist(searchedvideos)


@route('/playedvideos')
def listplayedvideos():  # type: () -> None
    """
    List played videos.
    """
    # query db for played videos list, empty if no data
    playedvideos = {
        'count': len(DB.table(TBL_PLAYED_VIDEOS)),
        'items': DB.table(TBL_PLAYED_VIDEOS).all(),
    }
    xbmc.log('{0}: Played videos: {1}'.format(ADDON.getAddonInfo('id'), playedvideos))
    # build list
    buildvideolist(playedvideos)


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
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(videos['count']) > offset + itemsperpage:
        videos['next'] = {
            'url': buildurl('/videos', {'offset': offset + itemsperpage}),
        }
    xbmc.log('{0}: Videos: {1}'.format(ADDON.getAddonInfo('id'), videos))
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
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(likedvideos['count']) > offset + itemsperpage:
        likedvideos['next'] = {
            'url': buildurl('/likedvideos', {'offset': offset + itemsperpage}),
        }
    xbmc.log('{0}: Liked videos: {1}'.format(ADDON.getAddonInfo('id'), likedvideos))
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
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(albumvideos['count']) > offset + itemsperpage:
        albumvideos['next'] = {
            'url': buildurl('/albumvideos', {'albumid': albumid, 'offset': offset + itemsperpage}),
        }
    xbmc.log('{0}: Album videos: {1}'.format(ADDON.getAddonInfo('id'), albumvideos))
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
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(communityvideos['count']) > offset + itemsperpage:
        communityvideos['next'] = {
            'url': buildurl('/communityvideos', {'communityid': communityid, 'offset': offset + itemsperpage}),
        }
    xbmc.log('{0}: Community videos: {1}'.format(ADDON.getAddonInfo('id'), communityvideos))
    # build list
    buildvideolist(communityvideos)


def buildvideolist(listdata):  # type: (dict) -> None
    """
    Build list of videos:

    - ``/searchvideos``
    - ``/videos``
    - ``/likedvideos``
    - ``/albumvideos``
    - ``/communityvideos``
    - ``/playedvideos``
    """
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
                    'RunPlugin({0})'.format(buildurl('/unlikevideo',
                                                     {'ownerid': video['owner_id'], 'videoid': video['id']}))
                )
            )
        else:
            # like video
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30053)),
                    'RunPlugin({0})'.format(buildurl('/likevideo',
                                                     {'ownerid': video['owner_id'], 'videoid': video['id']}))
                )
            )
        # add video to albums
        cmi.append(
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30055)),
                'RunPlugin({0})'.format(buildurl('/addvideotoalbums',
                                                 {'ownerid': video['owner_id'], 'videoid': video['id']}))
            )
        )
        # search videos
        cmi.append(
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051)),
                'Container.Update({0})'.format(buildurl('/searchvideos'))  # upd.required!
            )
        )
        # search similar
        cmi.append(
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30080)),
                'Container.Update({0})'.format(buildurl('/searchvideos', {'similarq': video['title']}))  # upd.required!
            )
        )
        li.addContextMenuItems(cmi)
        # add video item to list
        listitems.append(
            (
                buildurl('/playvideo', {'ownerid': video['owner_id'], 'videoid': video['id']}),
                li,
                ITEM_TYPE_NOTFOLDER
            )
        )
    # paginator item
    if 'next' in listdata:
        listitems.append(
            (
                listdata['next']['url'],
                xbmcgui.ListItem('[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30050))),
                ITEM_TYPE_FOLDER
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
        raise AddonError(ERR_VK_API)
    # resolve playable streams via vk videoinfo url
    vi = VKSESSION.requests_session.get(
        url='https://vk.com/al_video.php?act=show_inline&al=1&video={0}'.format(oidid),
        headers={'User-Agent': xbmc.getUserAgent()},  # +cookies required (sent autom.)
    )
    xbmc.log('{0}: Resolving video url: {1}'.format(ADDON.getAddonInfo('id'), vi.url))
    matches = re.findall(r'"url(\d+)":"([^"]+)"', vi.text.replace('\\', ''))
    playables = {}
    for m in matches:
        qual = int(m[0])
        playables[qual] = m[1]
    if playables:
        # streams resolved, use one of best quality
        maxqual = max(playables.keys())
        xbmc.log('{0}: Playable stream resolved: {1}'.format(ADDON.getAddonInfo('id'), playables[maxqual]))
    else:
        raise AddonError(ERR_RESOLVING)
    # update played videos db
    video.update(
        {
            'oidid': oidid,
            'lastPlayed': datetime.datetime.now().isoformat(),
        }
    )
    DB.table(TBL_PLAYED_VIDEOS).upsert(video, tinydb.where('oidid') == oidid)
    xbmc.log('{0}: Played videos db updated: {1}'.format(ADDON.getAddonInfo('id'), video))
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
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # request vk api
    try:
        _ = VKAPI.likes.add(
            type='video',
            owner_id=ownerid,
            item_id=videoid,
        )
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Video liked: {1}'.format(ADDON.getAddonInfo('id'), oidid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


@route('/unlikevideo')
def unlikevideo(ownerid, videoid):  # type: (int, int) -> None
    """
    Unlike video.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
    # request vk api
    try:
        _ = VKAPI.likes.delete(
            type='video',
            owner_id=ownerid,
            item_id=videoid,
        )
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Video unliked: {1}'.format(ADDON.getAddonInfo('id'), oidid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


@route('/addvideotoalbums')
def addvideotoalbums(ownerid, videoid):  # type: (int, int) -> None
    """
    Add video to albums.
    """
    ownerid = int(ownerid)
    videoid = int(videoid)
    oidid = str('{0}_{1}'.format(ownerid, videoid))
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
        raise AddonError(ERR_VK_API)
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
            _ = VKAPI.video.removeFromAlbum(
                owner_id=ownerid,
                video_id=videoid,
                album_ids=albumids
            )
        # add new sel album ids if any
        if len(newalbumids) > 0:
            _ = VKAPI.video.addToAlbum(
                owner_id=ownerid,
                video_id=videoid,
                album_ids=newalbumids
            )
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Video added to albums: {1}'.format(ADDON.getAddonInfo('id'), oidid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


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
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Albums: {1}'.format(ADDON.getAddonInfo('id'), albums))
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
                    'RunPlugin({0})'.format(buildurl('/reorderalbum', {'albumid': album['id'], 'beforeid': beforeid}))
                ),
                # reorder album down
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30062)),
                    'RunPlugin({0})'.format(buildurl('/reorderalbum', {'albumid': album['id'], 'afterid': afterid}))
                ),
                # rename album
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30060)),
                    'RunPlugin({0})'.format(buildurl('/renamealbum', {'albumid': album['id']}))
                ),
                # delete album
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30063)),
                    'RunPlugin({0})'.format(buildurl('/deletealbum', {'albumid': album['id']}))
                ),
                # create new album
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30065)),
                    'RunPlugin({0})'.format(buildurl('/createalbum'))
                ),
                # search videos
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051)),
                    'Container.Update({0})'.format(buildurl('/searchvideos'))  # upd.required!
                ),
            ]
        )
        listitems.append(
            (
                buildurl('/albumvideos', {'albumid': album['id']}),
                li,
                ITEM_TYPE_FOLDER
            )
        )
    # paginator item
    if offset + albumsperpage < albums['count']:
        listitems.append(
            (
                buildurl('/albums', {'offset': offset + albumsperpage}),
                xbmcgui.ListItem('[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30050))),
                ITEM_TYPE_FOLDER
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
        _ = VKAPI.video.reorderAlbums(
            album_id=albumid,
            **reorder
        )
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Album reordered: {1}'.format(ADDON.getAddonInfo('id'), albumid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


@route('/renamealbum')
def renamealbum(albumid):  # type: (int) -> None
    """
    Rename album.
    """
    albumid = int(albumid)
    # request vk api for album
    try:
        album = VKAPI.video.getAlbumById(
            album_id=albumid
        )
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    # ask user for editing current album title
    newtitle = xbmcgui.Dialog().input(ADDON.getLocalizedString(30060), defaultt=album['title'])
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
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Album renamed: {1}'.format(ADDON.getAddonInfo('id'), albumid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


@route('/deletealbum')
def deletealbum(albumid):  # type: (int) -> None
    """
    Delete album.
    """
    albumid = int(albumid)
    # ask user for confirmation
    if not xbmcgui.Dialog().yesno(ADDON.getLocalizedString(30063), ADDON.getLocalizedString(30064)):
        return
    # request vk api
    try:
        _ = VKAPI.video.deletealbum()
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Album deleted: {1}'.format(ADDON.getAddonInfo('id'), albumid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


@route('/createalbum')
def createalbum():  # type: () -> None
    """
    Create album.
    """
    # ask user for entering new album title
    albumtitle = xbmcgui.Dialog().input(ADDON.getLocalizedString(30065))
    if not albumtitle:
        return
    # request vk api
    try:
        album = VKAPI.video.addAlbum(
            title=albumtitle,
            privacy=3,  # 3=onlyme
        )
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Album created: {1}'.format(ADDON.getAddonInfo('id'), album['album_id']))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


# communities


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
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(communities['count']) > offset + itemsperpage:
        communities['next'] = {
            'url': buildurl('/communities', {'offset': offset + itemsperpage}),
        }
    xbmc.log('{0}: Communities: {1}'.format(ADDON.getAddonInfo('id'), communities))
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
        raise AddonError(ERR_VK_API)
    # pagination data
    if int(likedcommunities['count']) > offset + itemsperpage:
        likedcommunities['next'] = {
            'url': buildurl('/likedcommunities', {'offset': offset + itemsperpage}),
        }
    xbmc.log('{0}: Liked communities: {1}'.format(ADDON.getAddonInfo('id'), likedcommunities))
    # build list
    buildcommunitylist('/likedcommunities', likedcommunities)


def buildcommunitylist(listtype, listdata):  # type: (str, dict) -> None
    """
    Build list of communities:

    - ``/communities``
    - ``/likedcommunities``
    """
    # create list
    listitems = []
    namekey = 'title' if listtype == '/likedcommunities' else 'name'
    for community in listdata['items']:
        if listtype == '/likedcommunities':
            community['id'] = community['id'].split('_')[2]
        # create community item
        li = xbmcgui.ListItem(community[namekey])
        # set art
        li.setArt({'thumb': community['photo_200']})
        # create context menu
        cmi = []
        # unlike/like community
        if listtype == '/likedcommunities':
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30071)),
                    'RunPlugin({0})'.format(buildurl('/unlikecommunity', {'communityid': community['id']}))
                )
            )
        else:
            cmi.append(
                (
                    '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30070)),
                    'RunPlugin({0})'.format(buildurl('/likecommunity', {'communityid': community['id']}))
                )
            )
        # unfollow community
        cmi.append(
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30072)),
                'RunPlugin({0})'.format(buildurl('/unfollowcommunity', {'communityid': community['id']}))
            )
        )
        # search videos
        cmi.append(
            (
                '[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30051)),
                'Container.Update({0})'.format(buildurl('/searchvideos'))  # upd.required!
            )
        )
        li.addContextMenuItems(cmi)
        # add item to list
        listitems.append(
            (
                buildurl('/communityvideos', {'communityid': '{0}'.format(community['id'])}),
                li,
                ITEM_TYPE_FOLDER
            )
        )
    # paginator item
    if 'next' in listdata:
        listitems.append(
            (
                listdata['next']['url'],
                xbmcgui.ListItem('[COLOR {0}]{1}[/COLOR]'.format(ALT_COLOR, ADDON.getLocalizedString(30050))),
                ITEM_TYPE_FOLDER
            )
        )
    # show list in kodi, even if empty
    xbmcplugin.setContent(SYSARGV['handle'], 'files')
    xbmcplugin.addDirectoryItems(SYSARGV['handle'], listitems, len(listitems))
    xbmcplugin.addSortMethod(SYSARGV['handle'], xbmcplugin.SORT_METHOD_NONE)
    xbmcplugin.endOfDirectory(SYSARGV['handle'])


@route('/likecommunity')
def likecommunity(communityid):  # type: (int) -> None
    """
    Like community.
    """
    communityid = int(communityid)
    # request vk api
    try:
        _ = VKAPI.fave.addGroup(
            group_id=communityid
        )
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Community liked: {1}'.format(ADDON.getAddonInfo('id'), communityid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


@route('/unlikecommunity')
def unlikecommunity(communityid):  # type: (int) -> None
    """
    Unlike community.
    """
    communityid = int(communityid)
    # request vk api
    try:
        _ = VKAPI.fave.removeGroup(
            group_id=communityid
        )
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Community unliked: {1}'.format(ADDON.getAddonInfo('id'), communityid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


@route('/unfollowcommunity')
def unfollowcommunity(communityid):  # type: (int) -> None
    """
    Unfollow community.
    """
    communityid = int(communityid)
    # request vk api
    try:
        _ = VKAPI.groups.leave(
            group_id=communityid
        )
    except vk.VkAPIError:
        raise AddonError(ERR_VK_API)
    xbmc.log('{0}: Community unfollowed: {1}'.format(ADDON.getAddonInfo('id'), communityid))
    # refresh content
    xbmc.executebuiltin('Container.Refresh')


if __name__ == '__main__':
    SYSARGV = {
        'path': str(sys.argv[0]),
        'handle': int(sys.argv[1]),
        'qs': str(sys.argv[2]),
    }
    try:
        ADDON = xbmcaddon.Addon()
        DB = inittinydb()
        VKSESSION = initvksession()
        VKAPI = initvkapi()
        dispatch()
    except AddonError as e:
        xbmc.log('{0}: {1}'.format(ADDON.getAddonInfo('id'), ADDON.getLocalizedString(e.errid)), level=xbmc.LOGERROR)
        xbmcgui.Dialog().notification(
            ADDON.getAddonInfo('id'), ADDON.getLocalizedString(e.errid), icon=xbmcgui.NOTIFICATION_ERROR
        )
