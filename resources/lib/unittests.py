"""
TESTCASES
---------
todo: define/describe list of all groups/testcases
todo: map to usecases

1) Common (addon install, setup, firstrun, authorization, ...)
- install addon from github (new installation)
- run with default settings
- ...

2) Search
- ...

3) My videos
- ...

4) my video albums
- use set album/s for video cma for user having 0 albums
- use 'set albums for video' cm action for user having >100 albums
- ...

5) my communities
- ...

6) my likes
- ...

7) stats
- ...

"""

import unittest
import addon

# test vk user
TEST_VK_USER = {
    'credentials': {
        'login': 'tweakcz@icloud.com',
        'password': None,  # todo
    },
}
ASSERT_TEST_VK_USER = {
    'id': '252651698',
    'accesstoken': None,  # todo
}

# test vk api video object
# (Home > Albums > Outdoor > Easy beach life)
TEST_VIDEO = {
    u'album_id': 52553483,
    u'can_add': 1,
    u'comments': 0,
    u'date': 1399413471,
    u'description': u'Cuba, Cayo Largo del Sol Island. Be nudist.',
    u'duration': 317,
    u'id': 168471765,
    u'owner_id': 243422351,
    u'photo_130': u'https://pp.userapi.com/c540505/u232253052/video/s_aa659be6.jpg',
    u'photo_320': u'https://pp.userapi.com/c540505/u232253052/video/l_e3a199a7.jpg',
    u'player': u'https://vk.com/video_ext.php?oid=243422351&id=168471765&hash=ba1f2675a67139a0&__ref=vk.api&api_hash=1539001490e6625aa046a6203649_GI2TENRVGE3DSOA',
    u'title': u'Easy Beach Life',
    u'views': 12,
}
ASSERT_TEST_VIDEO = {
    'oidid': '243422351_168471765',
    'url': 'https://vk.com/al_video.php?act=show_inline&al=1&video=243422351_168471765',
    'playablestreams': None,  # todo
}


class VKAddonTestCase(unittest.TestCase):

    def setUp(self):
        self.vkaddon = addon.VKAddon()

    def test_buildoidid(self):
        oidid = self.vkaddon.buildoidid(TEST_VIDEO['owner_id'], TEST_VIDEO['id'])
        self.assertEqual(oidid, ASSERT_TEST_VIDEO['oidid'])


if __name__ == '__main__':
    unittest.main()
