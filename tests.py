#!/usr/bin/env python

"""
TESTS:
# todo: describe list of all testcases/tests

1) Common
- install addon from github (new installation)
- first run with default settings
- authorize addon by entering user credentials
- run addon with cookies expired

2) Search
- search videos by entering a new query, then use any cm action for any searched video.
- ...

3) My videos
- ...

4) My video albums
- use set album/s for video cm action for user having 0 albums
- use set albums for video cm action for user having >100 albums
- ...

5) My communities
- ...

6) My likes
- ...

7) Stats
- ...

"""

import unittest
import addon


# test data: vk user
TEST_VK_USER = {
    'credentials': {
        'login': 'tweakcz@icloud.com',
        'password': None,  # todo
    },
}
TEST_VK_USER_ASSERT = {
    'id': '252651698',
    'accesstoken': None,  # todo
}

# test data: vk api video object (video albums > outdoor > easy beach life)
TEST_VIDEO = {
    'album_id': 52553483,
    'can_add': 1,
    'comments': 0,
    'date': 1399413471,
    'description': 'Cuba, Cayo Largo del Sol Island. Be nudist.',
    'duration': 317,
    'id': 168471765,
    'owner_id': 243422351,
    'photo_130': 'https://pp.userapi.com/c540505/u232253052/video/s_aa659be6.jpg',
    'photo_320': 'https://pp.userapi.com/c540505/u232253052/video/l_e3a199a7.jpg',
    'player': 'https://vk.com/video_ext.php?oid=243422351&id=168471765&hash=ba1f2675a67139a0&__ref=vk.api&api_hash=1539001490e6625aa046a6203649_GI2TENRVGE3DSOA',
    'title': 'Easy Beach Life',
    'views': 12,
}
TEST_VIDEO_ASSERT = {
    'oidid': '243422351_168471765',
    'url': 'https://vk.com/al_video.php?act=show_inline&al=1&video=243422351_168471765',
}


# testcases/tests
class VKAddonTestCase(unittest.TestCase):

    def setUp(self):
        """
        Set up test environment
        """
        self.vkaddon = addon.VKAddon()

    def test_buildoidid(self):
        """
        Test buildoidid() helper 
        (example)
        """
        oidid = self.vkaddon.buildoidid(TEST_VIDEO['owner_id'], TEST_VIDEO['id'])
        self.assertEqual(oidid, TEST_VIDEO_ASSERT['oidid'])


# run tests
if __name__ == '__main__':
    unittest.main()
