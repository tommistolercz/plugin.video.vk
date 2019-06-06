![Add-on icon](./resources/icon.png)

# VK (plugin.video.vk)

Kodi add-on for watching videos from VK.com social network.

- [Requirements](#requirements)
- [Installation](#installation)
- [Features](#features)
- [Screenshots](#screenshots)
- [Changelog](#changelog)

## Requirements

- [Kodi](https://kodi.tv) v17+ installed
- [VK.com](https://vk.com) user account

## Installation

1. Download the add-on zip file:<br>
    [plugin.video.vk-1.4.0.zip](https://github.com/tommistolercz/plugin.video.vk/releases/download/v1.4.0/plugin.video.vk-1.4.0.zip)
    
2. Install it in Kodi:<br>
    `Kodi > Settings > Add-ons > Install from zip file...`
    
    [How to install add-ons from zip files](https://kodi.wiki/view/HOW-TO:Install_add-ons_from_zip_files)

## Features
<<<<<<< HEAD

Translations:
- English
- Czech

Add-on settings:
- Items per page
- Force custom view mode for videos
- Search without age restrictions
- Search incl. own videos
- Search by video duration (any, longer/shorter than)
- Sort searched videos (by relevance, date, duration)
- Keep history of add-on requests (hidden)
- Keep history of played videos
- VK user login (email/phone)

 Auth:
- Authorize add-on
- Logout user

Navigation:
- List add-on menu
- Skip to page

Search:
- Search videos
- Search videos by similar title
- List search history
- Delete search from history
- Clear search history

Videos:
- List searched videos
- List my videos
- List my liked videos
- List album videos
- List community videos
- List played videos
- Clear played videos
- List watchlist
- Add video to watchlist
- Remove video from watchlist
- Clear watchlist
- Play video
- Like video
- Unlike video
- Set albums for video
- Go to (owning) community

Video albums:
- List my video albums
- Rename album
- Reorder album up/down
- Delete album
- Create new album

Communities:
- List my communities
- List my liked communities
- Like community
- Unlike community
- Follow community
- Unfollow community

## Screenshots

![Screenshot 1: Add-on settings](./resources/media/screenshot01.jpg)

![Screenshot 2: Add-on menu](./resources/media/screenshot02.jpg)

![Screenshot 3: Add-on content](./resources/media/screenshot03.jpg)

## Changelog

- [v1.4.0 (2019-06-06)](#v140-2019-06-06)
- [v1.3.0 (2019-04-17)](#v130-2019-04-17)
- [v1.2.0 (2019-03-04)](#v120-2019-03-04)
- [v1.1.0 (2019-02-01)](#v110-2019-02-01)
- [v1.0.0 (2018-11-12)](#v100-2018-11-12)

### v1.4.0 (2019-06-06)

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
- Updated readme
=======

Translations:
- English
- Czech

Add-on settings:
- Items per page
- Force custom view mode for videos
- Search incl. adult videos
- Search incl. own videos
- Search by video duration (any, longer/shorter than)
- Sort searched videos (by relevance, date, duration)
- Keep history of add-on requests
- Keep history of played videos

 Auth:
- Authorize add-on
- Logout user

Navigation:
- List add-on menu

Search:
- Search videos
- Search by similar title
- List search history
- Delete search from history
- Clear search history

Videos:
- List searched videos
- List my videos
- List my liked videos
- List album videos
- List community videos
- List played videos
- Clear played videos
- List watchlist
- Add video to watchlist
- Remove video from watchlist
- Clear watchlist
- Play video
- Like video
- Unlike video
- Add video to albums

Video albums:
- List my video albums
- Rename album
- Reorder album up/down
- Delete album
- Create new album

Communities:
- List my communities
- List my liked communities
- Like community
- Unlike community
- Unfollow community
>>>>>>> 1bf586169383b83466d48ff62e5d735da23f3705

### v1.3.0 (2019-04-17)

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

### v1.2.0 (2019-03-04)

Fixed:
- Reported unicode issues (#66, #70)
- Weak encoding error in main menu

Added:
- Played videos (list)

Changed:
- Search videos (contextual action, avail. in all lists)
- Refactored add-on file structure and python code

### v1.1.0 (2019-02-01)

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

### v1.0.0 (2018-11-12)

<<<<<<< HEAD
=======
![Screenshot 4: Add-on video list](resources/media/screenshot4.jpg)

## Changelog

### v1.0.0 (2018-11-12)

>>>>>>> 1bf586169383b83466d48ff62e5d735da23f3705
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
<<<<<<< HEAD
- Set albums for video
=======
- Add video to albums
>>>>>>> 1bf586169383b83466d48ff62e5d735da23f3705
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
<<<<<<< HEAD
=======

### v1.1.0 (2019-02-01)

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

### v1.2.0 (2019-03-04)

Fixed:
- Reported unicode issues (#66, #70)
- Weak encoding error in main menu

Added:
- Played videos (list)

Changed:
- Search videos (contextual action, avail. in all lists)
- Refactored add-on file structure and python code

### v1.3.0 (2019-04-17)

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
>>>>>>> 1bf586169383b83466d48ff62e5d735da23f3705
