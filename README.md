![Add-on icon](resources/icon.png)

# VK (plugin.video.vk)

Kodi add-on for watching videos from VK.com social network.

- [Requirements](#requirements)
- [Installation](#installation)
- [Features and changelog](#features-and-changelog)
- [Screenshots](#screenshots)

## Requirements

- [Kodi](https://kodi.tv) v17+ installed
- [VK.com](https://vk.com) user account

## Installation

1. Download the add-on zip file:<br>
    [plugin.video.vk-1.2.0.zip](https://github.com/tommistolercz/plugin.video.vk/releases/download/v1.2.0/plugin.video.vk-1.2.0.zip)
    
2. Install it in Kodi:<br>
    `Kodi > Settings > Add-ons > Install from zip file...`

    [How to install add-ons from zip files](https://kodi.wiki/view/HOW-TO:Install_add-ons_from_zip_files)

## Features and changelog

### v1.3.0-dev (not released)

- [ ] Fix resolving error in `/playvideo` due unhandled cookies exp. (#57)
- [ ] Fix sorting of `/playedvideos` (by last played) (#78)
- [x] Fixed pagination for `/searchhistory`, `/playedvideos` (#74)
- [x] Fixed bug in `/deletealbum`
- [x] Fixed displaying of long video titles in lists
- [x] Added new features:
    - [x] `/watchlist` video list
    - [x] `/addvideotowatchlist` action
    - [x] `/deletevideofromwatchlist` action
    - [x] `/clearwatchlist` action
    - [x] `/clearsearchhistory` action (#75)
    - [x] `/clearplayedvideos` action (#75)
- [x] Added new settings:
    - [x] `keepaddonrequesthistory` (default false, not visible)
    - [x] `keepplayedvideohistory` (default false)
- [x] Optimized performance
- [x] Refined python code

### v1.2.0 (2019-03-04)

- [x] Fixed unicode issues:
    - [x] Fixed reported unicode issues (#66) (#70)
    - [x] Fixed weak encoding error in main menu (search history item)
- [x] Added new features:
    - [x] `/playedvideos` video list
    - [x] `/searchvideos` action (available in all lists)
- [x] Refactored add-on file structure and python code

### v1.1.0 (2019-02-01)

- [x] Fixed unicode issues
- [x] Fixed content refreshing after contextual actions
- [x] Fixed pagination bug
- [x] Fixed itemsperpage setting bug
- [x] Fixed Logout user button visibility bug 
- [x] Added info-labels showing video resolution in lists
- [x] Added counter for Search history in menu
- [x] Added code enabling Addict stats future feature
- [x] Reduced using of Kodi notifications
- [x] Utilized TinyDB for persisting add-on data
- [x] Refined complete python code
- [x] Refined language resources
- [x] Renamed cookies data file to be non-hidden

### v1.0.0 (2018-11-12)

Common:
- [x] EN/CZ language version
- [x] Manage add-on settings
- [x] Authorize add-on
- [x] List menu
- [x] Logout user

Search history:
- [x] List search history
- [x] Delete search

Videos:
- [x] Search videos
- [x] Search similar videos
- [x] List videos
- [x] List liked videos
- [x] List album videos
- [x] List community videos
- [x] Play video
- [x] Like video
- [x] Unlike video
- [x] Add video to albums

Video albums:
- [x] List albums
- [x] Rename album
- [x] Reorder album up/down
- [x] Delete album
- [x] Create new album

Communities:
- [x] List communities
- [x] List liked communities
- [x] Like community
- [x] Unlike community
- [x] Unfollow community

## Screenshots

![Screenshot 1: Add-on info](resources/media/screenshot1.jpg)

![Screenshot 2: Add-on settings](resources/media/screenshot2.jpg)

![Screenshot 3: Add-on menu](resources/media/screenshot3.jpg)

![Screenshot 4: Add-on content](resources/media/screenshot4.jpg)
