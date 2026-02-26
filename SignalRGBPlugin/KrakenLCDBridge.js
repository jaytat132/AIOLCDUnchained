export function Name() {
  return 'Kraken LCD Bridge';
}
export function Version() {
  return '0.0.2';
}
export function Type() {
  return 'network';
}
export function Publisher() {
  return 'Brokenmass';
}
export function Documentation() {
  return 'N/A';
}
export function Size() {
  return [6, 6];
}
export function DefaultPosition() {
  return [165, 60];
}
export function DefaultScale() {
  return 1.0;
}
export function DefaultComponentBrand() {
  return 'CompGen';
}
export function LedNames() {
  return [];
}
export function LedPositions() {
  return [];
}

const parameters = {
  displayMode: {
    property: 'displayMode',
    group: '',
    label: 'Display Mode',
    type: 'combobox',
    values: ['SignalRGB Canvas', 'GIF'],
    default: 'SignalRGB Canvas',
  },
  gifPath: {
    property: 'gifPath',
    group: '',
    label: 'GIF File Path',
    type: 'textfield',
    default: '',
  },
  gifRotation: {
    property: 'gifRotation',
    group: '',
    label: 'GIF Rotation',
    type: 'combobox',
    values: ['0', '90', '180', '270'],
    default: '0',
  },
  fps: {
    property: 'fps',
    group: '',
    label: 'FPS',
    type: 'combobox',
    values: ['MAXIMUM', 'SIGNALRGB LIMITED', '20', '10', '5', '1', '0.1'],
    default: 'SIGNALRGB LIMITED',
  },
  screenSize: {
    property: 'screenSize',
    group: '',
    label: 'ScreenSize',
    step: '1',
    type: 'number',
    min: '1',
    max: '80',
    default: '40',
  },
  imageFormat: {
    property: 'imageFormat',
    group: '',
    label: 'Format',
    type: 'combobox',
    values: ['PNG', 'JPEG'],
    default: 'PNG',
  },
  colorPalette: {
    property: 'colorPalette',
    group: '',
    label: 'Color Palette',
    type: 'combobox',
    values: ['WEB', 'ADAPTIVE'],
    default: 'WEB',
  },
  composition: {
    property: 'composition',
    group: '',
    label: 'Composition mode',
    type: 'combobox',
    values: ['OFF', 'OVERLAY', 'MIX'],
    default: 'OVERLAY',
  },
  overlayTransparency: {
    property: 'overlayTransparency',
    group: '',
    label: 'Overlay Transparency',
    step: 1,
    type: 'number',
    min: 0,
    max: 100,
    default: 0,
  },
  spinner: {
    property: 'spinner',
    group: '',
    label: 'Spinner',
    type: 'combobox',
    values: ['OFF', 'STATIC', 'CPU', 'PUMP'],
    default: 'STATIC',
  },
  textOverlay: {
    property: 'textOverlay',
    group: '',
    label: 'Text overlay',
    type: 'boolean',
    default: true,
  },
  titleText: {
    property: 'titleText',
    group: '',
    label: 'titleText',
    type: 'textfield',
    default: 'SignalRGB',
  },
  titleFontSize: {
    property: 'titleFontSize',
    group: '',
    label: 'titleFontSize',
    step: 1,
    type: 'number',
    min: 10,
    max: 200,
    default: 40,
  },
  sensorFontSize: {
    property: 'sensorFontSize',
    group: '',
    label: 'sensorFontSize',
    step: 1,
    type: 'number',
    min: 10,
    max: 320,
    default: 160,
  },
  sensorLabelFontSize: {
    property: 'sensorLabelFontSize',
    group: '',
    label: 'sensorLabelFontSize',
    step: 1,
    type: 'number',
    min: 10,
    max: 200,
    default: 40,
  },
  sensorSource: {
    property: 'sensorSource',
    group: '',
    label: 'Sensor Display',
    type: 'combobox',
    values: ['Liquid', 'CPU Temp', 'GPU Temp'],
    default: 'Liquid',
  },
  gifFitMode: {
    property: 'gifFitMode',
    group: '',
    label: 'GIF Fit Mode',
    type: 'combobox',
    values: ['Fill', 'Fit', 'Stretch'],
    default: 'Fill',
  },
  gifZoom: {
    property: 'gifZoom',
    group: '',
    label: 'GIF Zoom %',
    step: 5,
    type: 'number',
    min: 100,
    max: 400,
    default: 100,
  },
  gifOffsetX: {
    property: 'gifOffsetX',
    group: '',
    label: 'GIF Offset X',
    step: 1,
    type: 'number',
    min: -50,
    max: 50,
    default: 0,
  },
  gifOffsetY: {
    property: 'gifOffsetY',
    group: '',
    label: 'GIF Offset Y',
    step: 1,
    type: 'number',
    min: -50,
    max: 50,
    default: 0,
  },
};

export function ControllableParameters() {
  return [
    parameters.displayMode,
    parameters.fps,
    parameters.screenSize,
    parameters.imageFormat,
    parameters.gifPath,
    parameters.gifRotation,
    parameters.gifFitMode,
    parameters.gifZoom,
    parameters.gifOffsetX,
    parameters.gifOffsetY,
    parameters.colorPalette,
    parameters.composition,
  ];
}

/* global
controller:readonly
discovery: readonly
*/

const BRIDGE_ADDRESS = 'http://127.0.0.1:30003';
let nextCall = 0;
let lastGifPath = '';
let lastGifRotation = '0';
let lastGifFps = '';
var saved = {
  colorPalette: 'WEB',
  imageFormat: 'PNG',
  composition: 'OVERLAY',
  overlayTransparency: 0,
  spinner: 'STATIC',
  textOverlay: true,
  titleText: 'SignalRGB',
  titleFontSize: 40,
  sensorFontSize: 160,
  sensorLabelFontSize: 40,
  sensorSource: 'Liquid',
};

export function onfpsChanged() {
  nextCall = 0;
  const mode = device.getProperty('displayMode')?.value ?? 'SignalRGB Canvas';
  if (mode === 'GIF') {
    lastGifPath = '';
    ongifPathChanged();
  }
}

export function onscreenSizeChanged() {
  device.setSize([screenSize + 1, screenSize + 1]);
}

export function onBrightnessChanged() {
  XmlHttp.Post(
    BRIDGE_ADDRESS + '/brightness',
    () => {},
    {brightness: device.getBrightness()},
    false
  );
}

export function ondisplayModeChanged() {
  const mode = device.getProperty('displayMode').value;
  if (mode === 'GIF') {
    // Snapshot current canvas settings before removing them
    saved.imageFormat = device.getProperty('imageFormat')?.value ?? saved.imageFormat;
    saved.colorPalette = device.getProperty('colorPalette')?.value ?? saved.colorPalette;
    saved.composition = device.getProperty('composition')?.value ?? saved.composition;
    saved.overlayTransparency = device.getProperty('overlayTransparency')?.value ?? saved.overlayTransparency;
    saved.spinner = device.getProperty('spinner')?.value ?? saved.spinner;
    saved.textOverlay = device.getProperty('textOverlay')?.value ?? saved.textOverlay;
    saved.titleText = device.getProperty('titleText')?.value ?? saved.titleText;
    saved.titleFontSize = device.getProperty('titleFontSize')?.value ?? saved.titleFontSize;
    saved.sensorFontSize = device.getProperty('sensorFontSize')?.value ?? saved.sensorFontSize;
    saved.sensorLabelFontSize = device.getProperty('sensorLabelFontSize')?.value ?? saved.sensorLabelFontSize;
    saved.sensorSource = device.getProperty('sensorSource')?.value ?? saved.sensorSource;
    // Hide canvas-only controls
    device.removeProperty('imageFormat');
    device.removeProperty('colorPalette');
    device.removeProperty('composition');
    device.removeProperty('overlayTransparency');
    device.removeProperty('spinner');
    device.removeProperty('textOverlay');
    device.removeProperty('titleText');
    device.removeProperty('titleFontSize');
    device.removeProperty('sensorFontSize');
    device.removeProperty('sensorLabelFontSize');
    device.removeProperty('sensorSource');
    // Kick off GIF if path is already set
    ongifPathChanged();
  } else {
    // Restore canvas controls
    device.addProperty(parameters.imageFormat);
    device.addProperty(parameters.colorPalette);
    device.addProperty(parameters.composition);
    oncompositionChanged();
    // Tell bridge to stop GIF
    XmlHttp.Post(BRIDGE_ADDRESS + '/gif/stop', () => {}, {}, false);
    lastGifPath = '';
  }
}

function _buildGifPayload() {
  return {
    path: device.getProperty('gifPath')?.value ?? '',
    rotation: parseInt(device.getProperty('gifRotation')?.value ?? '0'),
    fps: device.getProperty('fps')?.value ?? '',
    fitMode: device.getProperty('gifFitMode')?.value ?? 'Fill',
    zoom: parseInt(device.getProperty('gifZoom')?.value ?? '100'),
    offsetX: parseInt(device.getProperty('gifOffsetX')?.value ?? '0'),
    offsetY: parseInt(device.getProperty('gifOffsetY')?.value ?? '0'),
  };
}

export function ongifPathChanged() {
  const path = device.getProperty('gifPath')?.value ?? '';
  const rotation = device.getProperty('gifRotation')?.value ?? '0';
  const fpsVal = device.getProperty('fps')?.value ?? '';
  if (path && path !== lastGifPath) {
    lastGifPath = path;
    lastGifRotation = rotation;
    lastGifFps = fpsVal;
    XmlHttp.Post(BRIDGE_ADDRESS + '/gif', () => {}, _buildGifPayload(), false);
  }
}

export function ongifRotationChanged() {
  const path = device.getProperty('gifPath')?.value ?? '';
  const rotation = device.getProperty('gifRotation')?.value ?? '0';
  if (path && rotation !== lastGifRotation) {
    lastGifPath = '';
    ongifPathChanged();
  }
}

export function ongifFitModeChanged() {
  _resendGifIfActive();
}

export function ongifZoomChanged() {
  _resendGifIfActive();
}

export function ongifOffsetXChanged() {
  _resendGifIfActive();
}

export function ongifOffsetYChanged() {
  _resendGifIfActive();
}

function _resendGifIfActive() {
  const mode = device.getProperty('displayMode')?.value ?? 'SignalRGB Canvas';
  if (mode === 'GIF' && lastGifPath) {
    lastGifPath = '';
    ongifPathChanged();
  }
}

export function oncompositionChanged() {
  if (device.getProperty('composition').value === 'OFF') {
    device.removeProperty('overlayTransparency');
    device.removeProperty('spinner');
    device.removeProperty('textOverlay');
  } else {
    device.addProperty(parameters.overlayTransparency);
    device.addProperty(parameters.spinner);
    device.addProperty(parameters.textOverlay);
  }
  ontextOverlayChanged();
}

export function ontextOverlayChanged() {
  if (device.getProperty('textOverlay')?.value) {
    device.addProperty(parameters.titleText);
    device.addProperty(parameters.titleFontSize);
    device.addProperty(parameters.sensorFontSize);
    device.addProperty(parameters.sensorLabelFontSize);
    device.addProperty(parameters.sensorSource);
  } else {
    device.removeProperty('titleText');
    device.removeProperty('titleFontSize');
    device.removeProperty('sensorFontSize');
    device.removeProperty('sensorLabelFontSize');
    device.removeProperty('sensorSource');
  }
}

export function Initialize() {
  device.setName(controller.name);
  onscreenSizeChanged();
  oncompositionChanged();
  ondisplayModeChanged();
  if (controller.renderingMode === 'RGBA') {
    device.removeProperty('colorPalette');
  }
  try {
    const image = XmlHttp.downloadImage(device.image);
    device.setImageFromBase64(image);
  } catch (error) {
    device.log('Could not retrieve device image');
  }
  onBrightnessChanged();
  var gp = device.getProperty('gifPath')?.value ?? '';
  if (gp) {
    XmlHttp.Post(
      BRIDGE_ADDRESS + '/gif/config',
      function () {},
      _buildGifPayload(),
      true
    );
  }
}

export function Render() {
  if (!controller.online || Date.now() < nextCall) {
    return false;
  }

  const sz = device.getProperty('screenSize')?.value ?? 40;
  const fmt = device.getProperty('imageFormat')?.value ?? 'PNG';

  const RGBData = device.getImageBuffer(0, 0, sz, sz, {
    flipH: false,
    outputWidth: sz,
    outputHeight: sz,
    format: fmt,
  });

  const data = {
    raw: XmlHttp.Bytes2Base64(RGBData),
    rotation: device.rotation,
    colorPalette: device.getProperty('colorPalette')?.value ?? saved.colorPalette,
    composition: device.getProperty('composition')?.value ?? saved.composition,
    overlayTransparency: device.getProperty('overlayTransparency')?.value ?? saved.overlayTransparency,
    spinner: device.getProperty('spinner')?.value ?? saved.spinner,
    textOverlay: device.getProperty('textOverlay')?.value ?? saved.textOverlay,
    titleText: device.getProperty('titleText')?.value ?? saved.titleText,
    titleFontSize: device.getProperty('titleFontSize')?.value ?? saved.titleFontSize,
    sensorFontSize: device.getProperty('sensorFontSize')?.value ?? saved.sensorFontSize,
    sensorLabelFontSize: device.getProperty('sensorLabelFontSize')?.value ?? saved.sensorLabelFontSize,
    sensorSource: device.getProperty('sensorSource')?.value ?? saved.sensorSource,
  };

  const fpsConfig = device.getProperty('fps')?.value;
  if (Number(fpsConfig)) {
    nextCall = Date.now() + 1000 / Number(fpsConfig) - 15;
  }

  const async = fpsConfig === 'MAXIMUM';
  XmlHttp.Post(BRIDGE_ADDRESS + '/frame', () => {}, data, async);
}

export function Shutdown(suspend) {
  XmlHttp.Post(BRIDGE_ADDRESS + '/gif/stop', () => {}, {}, false);
}

export function DiscoveryService() {
  this.IconUrl = `${BRIDGE_ADDRESS}/images/plugin.png`;
  this.Initialize = function () {
    service.log('Initializing Plugin!');
    this.lastUpdate = 0;
  };

  this.ReadInfo = function (xhr) {
    if (xhr.readyState === 4) {
      if (xhr.status === 200 && xhr.responseText) {
        this.deviceInfo = JSON.parse(xhr.responseText);
        if (!this.controller) {
          this.controller = new KrakenLCDBridgeController(this.deviceInfo);
          service.addController(this.controller);
        }
        this.controller.updateStatus({online: true});
      } else if (this.controller) {
        this.controller.updateStatus({online: false});
      }
    }
  };

  this.Update = function () {
    const currentTime = Date.now();
    const self = this;
    if (currentTime - this.lastUpdate >= 2000) {
      this.lastUpdate = currentTime;
      XmlHttp.Get(
        BRIDGE_ADDRESS,
        function (xhr) {
          self.ReadInfo(xhr);
        },
        true
      );
    }
  };

  this.Discovered = function () {};
}

class KrakenLCDBridgeController {
  constructor(info) {
    this.id = info.serial;
    this.name = info.name;
    this.resolution = info.resolution;
    this.renderingMode = info.renderingMode;
    this.image = info.image;
    this.online = true;
    this.lastUpdate = Date.now();
    this.announcedController = false;
  }

  updateStatus({online}) {
    this.online = online;
    this.update();
  }

  update() {
    service.updateController(this);
    if (!this.announcedController) {
      this.announcedController = true;
      service.announceController(this);
    }
  }
}

class XmlHttp {
  static Bytes2Base64(bytes) {
    for (let i = 0; i < bytes.length; i++) {
      if (bytes[i] > 255 || bytes[i] < 0) {
        throw new Error('Invalid bytes');
      }
    }

    const base64Chars =
      'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
    let out = '';
    for (let i = 0; i < bytes.length; i += 3) {
      const groupsOfSix = [undefined, undefined, undefined, undefined];
      groupsOfSix[0] = bytes[i] >> 2;
      groupsOfSix[1] = (bytes[i] & 0x03) << 4;
      if (bytes.length > i + 1) {
        groupsOfSix[1] |= bytes[i + 1] >> 4;
        groupsOfSix[2] = (bytes[i + 1] & 0x0f) << 2;
      }
      if (bytes.length > i + 2) {
        groupsOfSix[2] |= bytes[i + 2] >> 6;
        groupsOfSix[3] = bytes[i + 2] & 0x3f;
      }
      for (let j = 0; j < groupsOfSix.length; j++) {
        if (typeof groupsOfSix[j] === 'undefined') {
          out += '=';
        } else {
          out += base64Chars[groupsOfSix[j]];
        }
      }
    }
    return out;
  }

  static downloadImage(url) {
    const xhr = new XMLHttpRequest();
    xhr.open('GET', controller.image, false);
    xhr.responseType = 'arraybuffer';
    xhr.send(null);
    if (xhr.status === 200) {
      return XmlHttp.Bytes2Base64(new Uint8Array(xhr.response));
    } else {
      throw new Error(`Request error ${xhr.status}`);
    }
  }

  static Get(url, callback, async = true) {
    const xhr = new XMLHttpRequest();
    xhr.timeout = 1000;
    xhr.open('GET', url, async);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = callback.bind(null, xhr);
    xhr.send();
  }

  static Post(url, callback, data, async = true) {
    const xhr = new XMLHttpRequest();
    xhr.timeout = 1000;
    xhr.open('POST', url, async);
    xhr.setRequestHeader('Accept', 'application/json');
    xhr.setRequestHeader('Content-Type', 'application/json');
    xhr.onreadystatechange = callback.bind(null, xhr);
    xhr.send(JSON.stringify(data));
  }
}
