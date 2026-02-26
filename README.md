# AIO LCD Unchained

WARNING: i'm not responsible for any damage to your equipment. If anything get stuck your best option is to turn off your pc and disconnect it from power for a minute or two before restarting it.

This is a fork of [Marco Massarotto's](https://github.com/brokenmass/AIOLCDUnchained) with the introduction of gif support as well as cpu/gpu temperature monitoring

## Installation

Download latest executable from github releases run it and restart signalrgb.
The app adds an icon to the systray that can be left clicked

## Development

You must have python 3.11 and rust installed in your system

checkout the repository or download the latest code and install python dependencies

```
pip install -r requirements.txt --upgrade
```

build and install the q565 image compressor using rust

```
maturin build --release
pip install ./target/wheels/q565_rust-0.1.0-cp311-none-win_amd64.whl --force-reinstall
```

**Optional** Hardware temperature monitoring (Gpu/Cpu) is done via LibreHardwareMonitor, the exe comes precompiled with it, however, if you want a newer version you'd have to manually compile 
1. Download [LibreHardwareMonitor](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor/releases), the non-NET.10 zip 
2. Create and extract all dlls into a new folder called lhm in the root directory

build the exe

```
pyinstaller --noconfirm signalrgb.spec
```

**Run the EXE as administrator if LibreHardwareMonitor is bundled**

## Usage

Ensure NZXT CAM / Other proprietary software is closed and start one of the available functions:

### Rotating demo:

Simple animation with frames generated in realtime:

```
python rotating.py
```

### Screencap demo:

Captures an area of your screen and renders it in the kraken elit lcd

```
python screencap.py
```

### Signalrgb demo:

Receives a canvas section from signalRGB, adds temperature infos and display it on the device

```
python signalrgb.py
```

## Images

Remote desktop icons created by fzyn - Flaticon https://www.flaticon.com/free-icons/remote-desktop"
Kraken device images taken from NZXT website

## License

MIT License

Copyright (c) 2023 Marco Massarotto
Copyright (c) 2026 Jay Tat (GIF playback, HW monitoring, crop/browse extensions)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
