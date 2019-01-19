# VK (plugin.video.vk)

Kodi add-on for watching videos from VK.com social network.

![Icon](./resources/icon.png)

## Requirements

- [Kodi](https://kodi.tv) v17+ installed
- [VK.com](https://vk.com) user account

## Installation

1. Download the add-on zip file:<br>
    **not yet released**
    <!--[plugin.video.vk-1.1.0.zip](https://github.com/tommistolercz/plugin.video.vk/releases/download/v1.1.0/plugin.video.vk-1.1.0.zip)-->
    
2. Install it in Kodi:<br>
    `Kodi > Settings > Add-ons > Install from zip file...`

    [How to install add-ons from zip files](https://kodi.wiki/view/HOW-TO:Install_add-ons_from_zip_files)

## Features / Changelog

### v1.0.0 <sub>(2018-11-12)</sub>

Common:
- [x] EN/CZ language version
- [x] Manage add-on settings
- [x] Authorize add-on (OAuth2)
- [x] List add-on menu
- [x] Logout user

Videos:
- [x] Search videos
- [x] List user's videos
- [x] List user's liked videos
- [x] List album videos
- [x] List community videos
- [x] Play video
- [x] Like/Unlike video
- [x] Add video to albums

Video albums:
- [x] List user's albums
- [x] Rename album
- [x] Reorder album (Move up/down)
- [x] Delete album
- [x] Create new album

Communities:
- [x] List user's communities
- [x] List user's liked communities
- [x] Like/Unlike community
- [x] Unfollow community

Search history:
- [x] List user's search history
- [x] Delete search

### v1.1.0 <sub>(not yet released)</sub>

Fixes, improvements, code refactorings:
- [x] Fix unicode issues
- [ ] Fix content refreshing after performing context menu actions
- [x] Fix pagination code
- [x] Refine add-on routing
- [x] Refine debug logging
- [x] Refine language resources
- [x] Rename cookies data file to be non-hidden
- [x] Utilize TinyDB for persisting add-on data
- [ ] Auto migrate user data and clean up files after add-on upgrade
- [x] Track add-on requests for enabling MY STATS feature
- [x] Reduce using of Kodi notifications
- [x] Set info-labels for listed videos to show resolution before playing
- [x] Show search history items counter in main menu
- [x] Hide the LOGOUT USER action button unless the user is logged in

## Screenshots

![Screenshot 1](./resources/media/screenshot1.jpg)

![Screenshot 2](./resources/media/screenshot2.jpg)

![Screenshot 3](./resources/media/screenshot3.jpg)

![Screenshot 4](./resources/media/screenshot4.jpg)
