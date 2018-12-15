# VK (plugin.video.vk)

Kodi add-on for watching videos from VK.com social network.

## Requirements

- [Kodi](https://kodi.tv) 17.x or newer<br>
    (tested on: Kodi 17.6/macOS 10.13 High Sierra, Kodi 17.6/LibreELEC 8.2, Kodi 17.4/iOS 10)

- [VK.com](https://vk.com) user account

## Installation

1. Download the add-on zip file:<br>
    [plugin.video.vk-1.1.0.zip](https://github.com/tommistolercz/plugin.video.vk/releases/download/v1.1.0/plugin.video.vk-1.1.0.zip) **[WIP]**
    
2. Install in Kodi:<br>
    Settings > Add-ons > Install from zip file... (select downloaded file, press OK)
    
(More detailed instructions available [here](https://kodi.wiki/view/HOW-TO:Install_add-ons_from_zip_files).)

## Features

### v1.0.0

- Common
    - [x] Edit add-on settings
    - [x] List add-on main menu
    - [x] Authorize add-on (OAuth2 support using user access token)
    - [x] Logout user
    - [x] User-friendly listings (incl. pagination, HD thumbs, item counters, auto switching view modes, ...)
    - [x] EN/CZ translations
- Search
    - [x] Search videos
    - [x] List searched videos
    - [x] Search similar videos
    - [x] List search history
    - [x] Delete search
- My videos
    - [x] List videos
    - [x] Play video (HD support incl. 1080p)
- My video albums
    - [x] List albums
    - [x] List album videos
    - [x] Add album
    - [x] Rename album
    - [x] Reorder album up/down
    - [x] Delete album
    - [x] Set albums for video
- My communities
    - [x] List communities
    - [x] List community videos
    - [x] Leave community
- My likes
    - [x] List liked videos
    - [x] List liked communities
    - [x] Like video
    - [x] Unlike video
    - [x] Like community
    - [x] Unlike community

### v1.1.0 **[WIP]**

- Stats
    - [x] Track addon usage (usage.log)
    - [ ] List usage stats

### Backlog

Future features and ideas backlog:

- [ ] Auto copy name of playing video to clipboard
- [ ] Keyboard shortcuts for addon
- [ ] Played videos: list of all videos played by user
- [ ] Autoremove duplicated videos from album/list
- [ ] Setting for alternative color
- [ ] Search history items counter: getsearchhistorycounter() helper, show in main menu: SEARCH HISTORY (32)
- [ ] More detailed community lists
- [ ] use other info-labels (i.e. plot,...) for showing more details
- [ ] Download video: context menu action (video item), youtube-dl module integration
- [ ] Recently set albums: when use set albums for video context action, the recently set albums is saved and available for repetitive use.
- [ ] Import videos from favourites.xml
- [ ] Video news/updates
- [ ] Go to community the video belongs to
- [ ] Enable more sort methods for search history list
- [ ] Share video: context menu action (video item): sharing method: email?, recent recipients list?
- [ ] Add setting for custom path to addon data files (enable user to have the search history data synced among devices (using cloud services like Google Drive, Dropbox, etc)
- [ ] Auto-generated session playlists
- [ ] Set correct info-labels to show video's resolution in lists (without playing it): api serves video resolution in video object's width/height attributes (optional), set correct info-labels to show in Kodi
- [ ] VK API data analyzer
- [ ] Search videos with suggestions: plugin.program.autocompletion integration
- [ ] Try to utilize some free face/image recognition API:
    - [Face++](https://console.faceplusplus.com/dashboard), [docs](https://console.faceplusplus.com/documents/6329700)
    - search results analyzer: recommends which of searched videos are best to play (i.e. creates playlist) based on stats data, likes, preferences, ...)
    - detect faces (cm action)
    
## Docs

Some dev docs available [here](./resources/docs/DOCS.md).
