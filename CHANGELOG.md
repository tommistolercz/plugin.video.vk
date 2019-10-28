# CHANGELOG

## plugin.video.vk-1.6.1-dev (unreleased)

Added:
- VK password (setting, default last used)

Fixed:
- Cannot play videos due video resolving error
- Reused maxthumb code in video albums list

Changed:
- Refactored tests for enabling CI
- Disabled logging in VK API wrapper
- Refined README

## plugin.video.vk-1.6.0 (2019-07-14)

Fixed:
- Play video throws video resolving error after session cookies expiration (#57) 
- Search videos not working on RPi (#96)
- My liked communities list empty (#94)
- `Video['is_favorite']` always false? (#91)

Added:
- Prefer HLS (adaptive bitrate) (setting, default false)
- CHANGELOG.md

Changed:
- Enabled external debugging and unit testing (pytest/mock)
- Reworked vkauthsession handling
- Reworked vkresolver (incl. support for HLS)
- Improved overall performance by reducing VKAPI calls
- Reduced size of video thumbs (1280px no longer displayed)
- Reused maxthumb code in community lists (200px or 100px displayed)
- Refactored sys.argv handling
- Refined string formatting/coloring
- Updated LICENSE.md (GNU GPLv3)
- Refined README.md
    
## plugin.video.vk-1.5.1 (2019-07-03)

Fixed:
- Pagination issue in `listvideos()` 

## plugin.video.vk-1.5.0 (2019-06-29)

Fixed:
- Content refreshing issues (#69)
- Cannot create first video album (#76)

Added:
- RU translation (thanks to Владимир Малявин)
- Search videos by album/community title (contextual actions, reused)
- Create new album (contextual action, reused in video list)

Changed:
- Optimized video contextual menu
- Optimized debug logging/formatting (all non-error logging disabled)
- Refactored `listvideos()`, `listalbumvideos()`, `listcommunityvideos()`
- Refactored `searchvideos()`, `listsearchedvideos()`
- Refactored `buildfp()`
- Updated README (repository installation info/link)

## plugin.video.vk-1.4.0 (2019-06-06)

Fixed:
- Play video fails on video resolving error on iOS (#82)
- Video resolver bug due which the best available quality to not always be played (#86)

Added:
- Go to community (contextual action) (#87)
- Follow community (contextual action) (#88)
- Skip to page (contextual action) (#84)
- VK user login (setting) (#85)
  
Changed:
- Pagination item (next/last page nr, moved to first pos.)
- Unfollow community (user confirmation)
- VK user access token setting (invisible)
- Notifications
- Optimized performance (video lists, play video, debug logging, ...)
- Updated language resources
- Updated README

## plugin.video.vk-1.3.0 (2019-04-17)

Fixed:
- Missing pagination for Search history and Played videos (#74)
- Bug in Delete album
- Displaying of long video titles in video lists

Added:
- Watchlist (list)
- Add video to watchlist (contextual action)
- Delete video from watchlist (contextual action)
- Clear watchlist (contextual action)
- Clear search history (contextual action) (#75)
- Clear played videos (contextual action) (#75)
- Keep history of add-on requests (setting, default false, not visible)
- Keep history of played videos (setting, default false)

Changed:
- Optimized performance
- Refined python code

## plugin.video.vk-1.2.0 (2019-03-04)

Fixed:
- Reported unicode issues (#66, #70)
- Weak encoding error in main menu

Added:
- Played videos (list)

Changed:
- Search videos (contextual action, avail. in all lists)
- Refactored add-on file structure and python code

## plugin.video.vk-1.1.0 (2019-02-01)

Fixed:
- Various unicode issues
- Content refreshing issues
- Pagination bug
- Items per page setting bug
- Logout user button visibility bug
 
Added:
- Infolabels showing video resolution in lists
- Counter for Search history menu item    
- Code enabling Usage stats (future feature)

Changed:
- Removed most of Kodi notifications
- Utilized TinyDB for persisting add-on data
- Refined complete python code
- Refined language resources
- Renamed cookies data file to be non-hidden

## plugin.video.vk-1.0.0 (2018-11-12)

Added:
- EN/CZ translations
- Manage add-on settings
- Authorize add-on
- List add-on menu
- Logout
- Search videos
- Search by similar title
- List search history
- Delete search from history
- List videos
- List liked videos
- List album videos
- List community videos
- Play video
- Like video
- Unlike video
- Set albums for video
- List albums
- Rename album
- Reorder album up/down
- Delete album
- Create new album
- List communities
- List liked communities
- Like community
- Unlike community
- Unfollow community
