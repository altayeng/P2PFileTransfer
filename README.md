# P2P File Transfer

A simple file sharing tool that works across your local network. No cloud, no servers, just direct transfers between your devices.

## What it does

Ever needed to quickly send a file from your laptop to your desktop? Or share photos from your phone to your computer without using cloud services? This tool creates a web interface on your local network that lets you drag and drop files between any connected devices.

## Why I built this

I got tired of:
- Uploading files to cloud services just to download them on another device in the same room
- Dealing with USB drives for simple file transfers
- Complex network sharing setups that break every OS update
- File sharing apps that require accounts and internet connections

So I made something dead simple: start the app, open the web page, drag your files. Done.

## Features

- **Web interface** - Works in any browser, on any device
- **Drag & drop** - Just drag files into the browser window
- **Cross-platform** - Runs on macOS and Windows
- **No internet needed** - Everything stays on your local network
- **System tray integration** - Sits quietly in your menu bar/system tray
- **Transfer history** - See what you've shared recently

## Getting started

### What you need
- Python 3.7 or newer
- Devices connected to the same WiFi network

### Installation

```bash
# Download the code
git clone https://github.com/altayeng/P2PFileTransfer.git
cd P2PFileTransfer
 
# Install dependencies
pip install -r requirements.txt
```

### Running it

**On macOS:**
```bash
python macos.py
```

**On Windows:**
```bash
python windows.py
```

The app will start and show you the web address to open. Usually something like `http://192.168.1.100:4848`.

### Using it

1. Open the web address in any browser on any device on your network
2. Drag files into the upload area
3. Files appear on all connected devices instantly
4. Download what you need

That's it.

## How it works

The app creates a simple web server on port 4848 that serves a file sharing interface. When you upload a file, it's temporarily stored on the host computer and made available for download to other devices. Files are automatically cleaned up after transfer.

No magic, no complex networking - just HTTP serving files over your local network.

## Use cases

**At home:**
- Moving photos from phone to computer
- Sharing documents between laptop and desktop
- Getting files onto a device that doesn't have cloud apps

**At work:**
- Quick file sharing during meetings
- Moving files between work computers
- Sharing with colleagues without email attachments

**The main advantage:** If one computer goes down, others keep working. No single point of failure.

## Technical stuff

- **Backend:** Flask (Python web framework)
- **Frontend:** Plain HTML/CSS/JavaScript
- **System integration:** rumps for macOS tray, tkinter for Windows
- **Network:** Standard HTTP on port 4848
- **Security:** Local network only, no external access

## Contributing

Found a bug? Have an idea? Feel free to:
- Open an issue
- Submit a pull request
- Fork it and make it your own

This is a simple tool that does one thing well. I'd like to keep it that way.

## License

MIT License - use it however you want.

---

*Sometimes the simplest solutions are the best ones.*