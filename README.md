![VK icon](./resources/icon.png)

# VK (plugin.video.vk)

Kodi add-on for watching videos from VK.com social network.

## Requirements

- [Kodi](https://kodi.tv) v17+ installed
- [VK.com](https://vk.com) user account

## Installation

1. Download the add-on zip file:<br>
    **[WIP]**
    <!--[plugin.video.vk-1.1.0.zip](https://github.com/tommistolercz/plugin.video.vk/releases/download/v1.1.0/plugin.video.vk-1.1.0.zip)-->
    
2. Install it in Kodi:<br>
    `Kodi > Settings > Add-ons > Install from zip file...`
    
    [How to install add-ons from zip files](https://kodi.wiki/view/HOW-TO:Install_add-ons_from_zip_files)

## Features/Changelog

### v1.0.0

- Common:
    - [x] EN/CZ language version
    - [x] Manage add-on settings
    - [x] Authorize add-on (OAuth2)
    - [x] List add-on menu
    - [x] Logout user
- Videos:
    - [x] Search videos
    - [x] List user's videos
    - [x] List user's liked videos
    - [x] List album videos
    - [x] List community videos
    - [x] Play video
    - [x] Like/Unlike video
    - [x] Add video to albums
- Video albums:
    - [x] List user's albums
    - [x] Rename album
    - [x] Reorder album (Move up/down)
    - [x] Delete album
    - [x] Create new album
- Communities:
    - [x] List user's communities
    - [x] List user's liked communities
    - [x] Like/Unlike community
    - [x] Unfollow community
- Search history:
    - [x] List user's search history
    - [x] Delete search

### v1.1.0

- Fixes/improvements/refactorings:
    - [x] Fix unicode issues
    - [ ] Fix content refreshing after performing context menu actions (Kodi v18 changes?)
    - [x] Fix paginators
    - [x] Refine add-on routing (url/internal naming scheme)
    - [x] Refine debug logging
    - [x] Refine language resources
    - [x] Rename cookies data file to be non-hidden (cookiejar.txt)
    - [x] Utilize TinyDB for persisting add-on data (db.json)
    - [x] Merge search history data (db.json)
    - [ ] Autom. migrate user data and clean up obsolete files after add-on upgrade
    - [x] Track add-on requests for enabling MY STATS feature (db.json)
    - [x] Reduce using of Kodi notifications (do not confirm successful user actions)
    - [x] Set correct infolabels for listed video to show its resolution (before playing it)
    - [x] Show search history items counter in main menu
    - [x] Do not show the LOGOUT USER action button unless the user is logged in
