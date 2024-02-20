# Plexy
 Search and cast your Plex Library with Flow Launcher

![Plexy](https://github.com/Garulf/Plexy/assets/535299/82be35d5-9e30-4d94-980a-7b2de9d481a7)


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

```pl cars```

This will search for any media item matching "cars".

```pl movies:cars 3```

This will search the "movies" library for an item matching "cars 3".

```pl tvshows:the witcher```

```pl tv shows:the witcher```

Both examples will search the library matching "TV Shows" for an item called "the witcher"

### Interaction:

Selecting an item will open it in your web browser.

Opening the context menu on an item allows you to stream the media item to any available Plex Clients

# Requirements

Python 3.6 or higher

Wox, or Flow Launcher

##
<a href="https://www.buymeacoffee.com/garulf" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-green.png" alt="Buy Me A Coffee" style="height: 60px !important;width: 217px !important;" ></a>
