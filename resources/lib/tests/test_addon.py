# coding=utf-8

import addon  # test target
import pytest
import mock


# mocks -----


MOCK_USERINPUTS = {
    # vk user credentials
    'LSTR_30030': 'tweakcz@icloud.com',  # login (email/phone)  # todo: sensitive
    'LSTR_30031': '123atakdal321',  # pswd  # todo: sensitive
    # search videos
    'LSTR_30083': 'kazantip',  # q
}

MOCK_USERSETTINGS = {
    'forcevideoviewmode': 'true',
    'forcevideoviewmodeid': '500',
    'itemsperpage': '200',
    'keepaddonrequesthistory': 'false',
    'keepplayedvideohistory': 'false',
    'preferhls': 'false',
    'searchadult': 'true',
    'searchduration': '0',
    'searchdurationmins': '',
    'searchown': 'false',
    'searchsort': '2',  # '0'=bydate, '1'=byduration, '2'=byrelevance
    'vkuserlogin': '',
    'vkuseraccesstoken': '',
}

MOCK_KODIENV = {
    'fp_profile': '/Users/tom/Library/Application Support/Kodi/userdata/addon_data/plugin.video.vk',  # todo: sensitive
    'sysargv': {
        'path': str(__file__),
        'handle': int(0),
        'qs': str(''),
    }
}

MOCK_ADDONINFO = {
    'id': 'plugin.video.vk',
    'name': 'VK',
}

MOCK_VIDEO = {  # todo: sensitive
    '_oidid': '-152615939_456239302',  # debug
    u'owner_id': -152615939,
    u'id': 456239302,
    u'title': u'Kylie Martin (Creampie Detention) [Anal Sex, Blowjob, Deep Anal, Hardcore, All Sex, 1080p]',
    u'description': u'',
    u'width': 1920,
    u'height': 1080,
    u'duration': 2633,
    u'date': 1523360209,
    u'views': 4313,
    u'repeat': 0,
    u'player': u'https://vk.com/video_ext.php?oid=-152615939&id=456239302&hash=84d414ce93f53b48&__ref=vk.api&api_hash=156284320289899b2df810d92ef7_GI2TENRVGE3DSOA',
    u'photo_130': u'https://pp.userapi.com/c834204/v834204472/111239/dDjIhW3x3So.jpg',
    u'photo_320': u'https://pp.userapi.com/c834204/v834204472/111237/lCfUxDzapmE.jpg',
    u'photo_800': u'https://pp.userapi.com/c834204/v834204472/111236/765KevKJfPc.jpg',
    u'first_frame_130': u'https://pp.userapi.com/c841639/v841639021/97441/AlHZ72z9Q3k.jpg',
    u'first_frame_160': u'https://pp.userapi.com/c841639/v841639021/97440/inF0XQV6Vj0.jpg',
    u'first_frame_320': u'https://pp.userapi.com/c841639/v841639021/9743f/-5KXAkullr0.jpg',
    u'first_frame_800': u'https://pp.userapi.com/c841639/v841639021/9743e/Xh9djH65FwQ.jpg',
    u'is_favorite': True,
    u'can_add_to_faves': 1,
    u'likes': {u'count': 125, u'user_likes': 1},
    u'can_like': 1,
    u'can_add': 0,
    u'can_comment': 1,
    u'comments': 0,
    u'can_repost': 1,
    u'reposts': {u'count': 0, u'user_reposted': 0},
}

MOCK_COMMUNITY = {  # todo: sensitive
    u'id': 165942624,
    u'name': u'Pornlab 18+',
    u'screen_name': u'p0rnlab',
    u'type': u'group',
    u'photo_50': u'https://pp.userapi.com/c846419/v846419435/3e4e6/hAsVQ4qA7nA.jpg?ava=1',
    u'photo_100': u'https://pp.userapi.com/c846419/v846419435/3e4e5/R2bT3IoCfHM.jpg?ava=1',
    u'photo_200': u'https://pp.userapi.com/c846419/v846419435/3e4e3/maq4BH3zHWQ.jpg?ava=1',
    u'is_member': 1,
    u'is_admin': 0,
    u'is_advertiser': 0,
    u'is_closed': 0,
}

MOCK_LIKEDCOMMUNITY = {  # todo: sensitive
    u'group': {
        u'id': 176973002,
        u'name': u'PornoRUS',
        u'screen_name': u'club176973002',
        u'type': u'group',
        u'photo_50': u'https://sun6-19.userapi.com/c849224/v849224035/10d046/JYTo8O3Fi3w.jpg?ava=1',
        u'photo_100': u'https://sun6-13.userapi.com/c849224/v849224035/10d045/FJMvXD1AeF8.jpg?ava=1',
        u'photo_200': u'https://sun6-19.userapi.com/c849224/v849224035/10d044/iif7Iapvt8I.jpg?ava=1',
        u'is_member': 1,
        u'is_admin': 0,
        u'is_advertiser': 0,
        u'is_closed': 0,
    },
    u'type': u'group',
    u'description': u'Erotic, 13K members',
    u'tags': [],
    u'updated_date': 1557234431,
}


# patches -----


# patch addon.xbmc module
@pytest.fixture(autouse=True)
def patch_xbmc(monkeypatch, context=addon):
    mock_xbmc = mock.Mock(name='xbmc')
    monkeypatch.setattr(context, 'xbmc', mock_xbmc)


# patch addon.xbmcaddon module
@pytest.fixture(autouse=True)
def patch_xbmcaddon(monkeypatch, context=addon):

    def mock_getaddoninfo(id_):  # type: (str) -> str
        return MOCK_ADDONINFO[id_]

    def mock_getsetting(id_):  # type: (str) -> str
        return MOCK_USERSETTINGS[id_]

    def mock_setsetting(id_, value):  # type: (str, str) -> None
        MOCK_USERSETTINGS[id_] = value

    def mock_getlocalizedstring(id_):  # type: (int) -> str
        return 'LSTR_{}'.format(id_)

    mock_addonclass = mock.Mock(name='Addon')
    mock_addonclass.getAddonInfo.side_effect = mock_getaddoninfo
    mock_addonclass.getSetting.side_effect = mock_getsetting
    mock_addonclass.setSetting.side_effect = mock_setsetting
    mock_addonclass.getLocalizedString.side_effect = mock_getlocalizedstring

    mock_xbmcaddon = mock.Mock(name='xbmcaddon')
    mock_xbmcaddon.Addon.return_value = mock_addonclass
    monkeypatch.setattr(context, 'xbmcaddon', mock_xbmcaddon)


# patch addon.xbmcplugin module
@pytest.fixture(autouse=True)
def patch_xbmcplugin(monkeypatch, context=addon):
    mock_xbmcplugin = mock.Mock(name='xbmcplugin')
    monkeypatch.setattr(context, 'xbmcplugin', mock_xbmcplugin)


# patch addon.xbmcgui module
@pytest.fixture(autouse=True)
def patch_xbmcgui(monkeypatch, context=addon):

    def mock_input(heading, **_):  # type: (str, dict) -> str
        return MOCK_USERINPUTS[heading]

    mock_dialogclass = mock.Mock(name='Dialog')
    mock_dialogclass.input.side_effect = mock_input

    mock_xbmcgui = mock.Mock(name='xbmcgui')
    mock_xbmcgui.Dialog.return_value = mock_dialogclass
    monkeypatch.setattr(context, 'xbmcgui', mock_xbmcgui)


# patch addon.buildfp()
@pytest.fixture(autouse=True)
def patch_buildfp(monkeypatch, context=addon):

    def mock_buildfp(filename):  # type: (str) -> str
        import os
        fp = str(os.path.join(MOCK_KODIENV['fp_profile'], filename))
        return fp

    monkeypatch.setattr(context, 'buildfp', mock_buildfp)


# patch addon.parsesysargv()
@pytest.fixture(autouse=True)
def patch_parsesysargv(monkeypatch, context=addon):

    def mock_parsesysargv():  # type: () -> dict
        return MOCK_KODIENV['sysargv']

    monkeypatch.setattr(context, 'parsesysargv', mock_parsesysargv)


# tests -----


def test_addonglobal(context=addon):
    context.ADDON = context.initaddon()
    assert context.ADDON.getAddonInfo('id') == MOCK_ADDONINFO['id']
    assert context.ADDON.getSetting('itemsperpage') == MOCK_USERSETTINGS['itemsperpage']


def test_initvkauthsession(context=addon):
    context.ADDON = context.initaddon()
    context.logout()
    assert context.ADDON.getSetting('vkuseraccesstoken') == ''
    # create a new vk session
    vkauthsession = context.initvkauthsession()
    assert context.ADDON.getSetting('vkuseraccesstoken') != ''
    assert isinstance(vkauthsession, context.vk.api.AuthSession)
    # restore vk auth session
    vkauthsession_r = context.initvkauthsession()
    assert isinstance(vkauthsession_r, context.vk.api.AuthSession)


def test_initvkapi(context=addon):
    context.ADDON = context.initaddon()
    vkapi = context.initvkapi()
    assert isinstance(vkapi, context.vk.api.API)


# general


def test_listaddonmenu(context=addon):
    context.ADDON = context.initaddon()
    context.listaddonmenu()
    assert True


# search


def test_listsearchhistory(context=addon):
    context.ADDON = context.initaddon()
    context.listsearchhistory(offset=0)
    assert True


def test_searchvideos(context=addon):
    context.ADDON = context.initaddon()
    context.searchvideos(defq='')
    assert True


# videos


def test_listsearchedvideos(context=addon):
    context.ADDON = context.initaddon()
    context.listsearchedvideos(q='kazantip', offset=0)
    assert True


def test_listvideos(context=addon):
    context.ADDON = context.initaddon()
    context.listvideos(ownerid=0, albumid=0, offset=0)
    context.listvideos(ownerid=-MOCK_COMMUNITY['id'], albumid=0, offset=0)
    assert True


def test_listlikedvideos(context=addon):
    context.ADDON = context.initaddon()
    context.listlikedvideos(offset=0)
    assert True


def test_listwatchlist(context=addon):
    context.ADDON = context.initaddon()
    context.listwatchlist(offset=0)
    assert True


def test_playvideo(context=addon):
    context.ADDON = context.initaddon()
    context.playvideo(ownerid=MOCK_VIDEO['owner_id'], videoid=MOCK_VIDEO['id'])
    assert True


# communities


def test_listcommunities(context=addon):
    context.ADDON = context.initaddon()
    context.listcommunities(offset=0)
    assert True


def test_listlikedcommunities(context=addon):
    context.ADDON = context.initaddon()
    context.listlikedcommunities(offset=0)
    assert True


# albums


def test_listalbums(context=addon):
    context.ADDON = context.initaddon()
    context.listalbums(offset=0)
    assert True
