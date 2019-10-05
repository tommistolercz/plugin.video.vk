# coding=utf-8

import addon  # test target
import mock
import pytest

# sensitive test data
try:
    # from local non-vcs module
    from _testdata import *
except ImportError:
    # or from travis-ci secured env vars  (or blank)
    import os
    TESTDATA_VKUSER_LOGIN = os.environ.get('TESTDATA_VKUSER_LOGIN', '')
    TESTDATA_VKUSER_PSWD = os.environ.get('TESTDATA_VKUSER_PSWD', '')
    TESTDATA_FP_PROFILE = ''
    TESTDATA_SEARCHVIDEOS_QUERY = ''
    TESTDATA_VIDEO = {}
    TESTDATA_COMMUNITY = {}
    TESTDATA_LIKEDCOMMUNITY = {}


# mocks -----


MOCK_ADDONINFO = {
    'id': 'plugin.video.vk',
    'name': 'VK',
}

MOCK_KODIENV = {
    'fp_profile': TESTDATA_FP_PROFILE,
    'sysargv': {
        'path': str(__file__),
        'handle': int(0),
        'qs': str(''),
    }
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
    'vkuserlogin': TESTDATA_VKUSER_LOGIN,
    'vkuseraccesstoken': '',
}

MOCK_USERINPUTS = {
    'LSTR_30030': TESTDATA_VKUSER_LOGIN,
    'LSTR_30031': TESTDATA_VKUSER_PSWD,
    'LSTR_30083': TESTDATA_SEARCHVIDEOS_QUERY,
}

MOCK_VIDEO = TESTDATA_VIDEO
MOCK_COMMUNITY = TESTDATA_COMMUNITY
MOCK_LIKEDCOMMUNITY = TESTDATA_LIKEDCOMMUNITY


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


def test_vkapi_video_get(context=addon):
    context.ADDON = context.initaddon()
    vkapi = context.initvkapi()
    r = vkapi.video.get(
        album_id=None,
        videos=MOCK_VIDEO['_oidid'],
        extended=True,
    )
    assert r['count'] == 1


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
    context.listsearchedvideos(q=TESTDATA_SEARCHVIDEOS_QUERY, offset=0)
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
