![Plexy](https://github.com/Garulf/Plexy/assets/535299/04582125-0294-4092-80fd-19c2ce9de3dd)

# Plexy
 Search and cast your Plex Library with Flow Launcher

# Installation:

### Flow Lancher:

Simply type `pm install plexy` to have the plugin installed

### Manual Installation:

Unzip [Plexy.zip](https://github.com/Garulf/Plexy/releases/latest) to your launchers plugin directory.

| Launcher          | Plugin Path                      |
|-------------------|----------------------------------|
| Wox               | `%appdata%\Wox\Plugins`          |
| Flow Launcher     | `%appdata%\FlowLauncher\Plugins` |
| Portable Installs | `<Install Dir>\UserData\Plugins` |

# Configuration

Plexy will ask you for you servers URL and token at start-up.

| Setting       | Format                                                                                                                                       |
|---------------|----------------------------------------------------------------------------------------------------------------------------------------------|
| baseurl       | `baseurl` must include `http://` or `https://` e.g. `http://127.0.0.1:32400`                                                                 |
| token         | If you don't know how to retrieve your token follow this [guide](https://support.plex.tv/articles/201638786-plex-media-server-url-commands/) |

If your login fails you can reset all login information by pressing <kbd>Shift</kbd>+<kbd>Enter</kbd>. This brings up Plexy's context menu, you can reset your login by selecting "Reset Login".


# How-To:

### Basics:

Begin by typing the default ActionWord: `pl`

You can filter which library is searched by typing the libraries name and a colon symbol (`:`). Afterwhich you can enter your search term like normal.


#### Example:

Search for any media item matching "cars".

![Plexy](https://github.com/Garulf/Plexy/assets/535299/c592f4bf-2b15-49a1-8d3a-4e76a976b88d)

Search the "movies" library for an item matching "cars 3".

![Plexy](https://github.com/Garulf/Plexy/assets/535299/f3dee70a-bb7c-4cbe-bccf-8f231c88bcc7)

Search the library matching "TV Shows" for an item called "the witcher"

![Plexy](https://github.com/Garulf/Plexy/assets/535299/7a2da5c4-9f76-431a-b6a9-e7442c3ce571)


### Interaction:

Selecting an item will open it in your web browser.

Opening the context menu on an item allows you to stream the media item to any available Plex Clients

# Requirements

Python 3.8 or higher

Wox, or Flow Launcher

##
<a href="https://www.buymeacoffee.com/garulf" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-green.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>
