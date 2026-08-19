"""A visual, click-to-choose alternative to `iloc set <lat> <lon>`.

Opens a native window (via pywebview, backed by the OS's own web engine)
showing a Leaflet map with Esri World Imagery satellite tiles (plus a
boundaries/places labels overlay) and a place/address search box backed by
OpenStreetMap's Nominatim geocoder. The map itself is just an HTML/JS page
served by a small local HTTP server running in a background thread; clicking
"Set this location" in the page POSTs the chosen coordinates back to that
server, which hands them back to this function and closes the window.

This module only answers "which lat/lon did the user pick" -- it knows
nothing about DVT, tunnels, or pymobiledevice3. iloc.cli is responsible for
actually applying the chosen coordinates (via a privileged `iloc set`
subprocess, since a root/Administrator process can't open GUI windows, so the
picker and the privileged `set` step must be different processes).
"""

import http.server
import json
import queue
import socket
import threading

import webview

_PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>iloc -- pick a location</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  :root {
    --bg: #1e1f22;
    --fg: #e3e3e3;
    --fg-dim: #9a9a9e;
    --border: #3a3b3f;
    --accent: #5b8cff;
    --panel-bg: rgba(30, 31, 34, 0.96);
  }
  html, body, #map { height: 100%; margin: 0; background: var(--bg); }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    color: var(--fg);
  }

  #panel {
    position: absolute; top: 16px; left: 50px; z-index: 1000;
    background: var(--panel-bg);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 16px 18px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.35);
    font-size: 13px;
    min-width: 260px;
  }
  #panel .title { font-weight: 600; font-size: 15px; margin-bottom: 12px; }
  #prompt { color: var(--fg-dim); }
  #coords { display: block; margin: 8px 0 14px; color: var(--fg); }
  #confirm {
    width: 100%; padding: 8px 16px; border: none; border-radius: 6px;
    background: var(--accent); color: #fff; font-family: inherit; font-size: 13px; font-weight: 500;
    cursor: pointer;
  }
  #confirm:hover:not(:disabled) { background: #4a7bee; }
  #confirm:disabled { background: #3a3b3f; color: #6b6b6e; cursor: default; }

  #credit { margin-top: 14px; font-size: 11px; color: #6b6b6e; text-align: center; }
  #credit a { color: var(--fg-dim); text-decoration: none; }
  #credit a:hover { color: var(--accent); text-decoration: underline; }

  #search-form { display: flex; gap: 6px; margin-bottom: 10px; }
  #search-input {
    flex: 1; min-width: 0; padding: 7px 10px; border: 1px solid var(--border); border-radius: 6px;
    background: #16171a; color: var(--fg); font-family: inherit; font-size: 13px;
  }
  #search-input:focus { outline: none; border-color: var(--accent); }
  #search-input::placeholder { color: #6b6b6e; }
  #search-btn {
    padding: 7px 12px; border: 1px solid var(--border); border-radius: 6px;
    background: #2a2b2f; color: var(--fg); font-family: inherit; font-size: 13px; cursor: pointer;
  }
  #search-btn:hover { background: #34353a; }
  #search-results { max-height: 140px; overflow-y: auto; margin-bottom: 4px; }
  #search-results:empty { margin-bottom: 0; }
  .search-status { color: var(--fg-dim); padding: 4px 2px; }
  .search-result {
    padding: 6px 8px; border-radius: 4px; cursor: pointer; font-size: 12px;
    line-height: 1.3; color: var(--fg-dim);
  }
  .search-result:hover { background: rgba(91, 140, 255, 0.15); color: var(--fg); }

  .leaflet-control-attribution { background: rgba(30,31,34,0.75) !important; color: #8a8a8e !important; }
  .leaflet-control-attribution a { color: var(--fg-dim) !important; }
  .leaflet-control-zoom a { background: #2a2b2f !important; color: var(--fg) !important; border-color: var(--border) !important; }
</style>
</head>
<body>
<div id="panel">
  <div class="title">Set location</div>
  <form id="search-form" autocomplete="off">
    <input id="search-input" type="text" placeholder="Search a place or address..." />
    <button id="search-btn" type="submit">Find</button>
  </form>
  <div id="search-results"></div>
  <span id="prompt">Click the map to drop a pin, drag it to fine-tune.</span>
  <span id="coords">No location selected.</span>
  <button id="confirm" disabled>Set location</button>
  <div id="credit">Made by Omar Khalil &middot; <a href="https://github.com/omarkhk12" target="_blank" rel="noopener">github.com/omarkhk12</a></div>
</div>
<div id="map"></div>
<script>
  var map = L.map('map', {zoomControl: true}).setView([__CENTER_LAT__, __CENTER_LON__], __ZOOM__);
  L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    {maxZoom: 19, attribution: 'Tiles &copy; Esri'}
  ).addTo(map);
  L.tileLayer(
    'https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}',
    {maxZoom: 19, attribution: ''}
  ).addTo(map);

  var pinIcon = L.divIcon({
    className: '',
    html: '<svg width="30" height="42" viewBox="0 0 34 46" xmlns="http://www.w3.org/2000/svg" ' +
          'style="filter:drop-shadow(0 2px 4px rgba(0,0,0,0.4));">' +
          '<path d="M17 44C17 44 32 27 32 17C32 7.6 25.4 1 17 1C8.6 1 2 7.6 2 17C2 27 17 44 17 44Z" ' +
          'fill="#5b8cff" stroke="#fff" stroke-width="1.5"/>' +
          '<circle cx="17" cy="17" r="6" fill="#fff"/>' +
          '</svg>',
    iconSize: [30, 42],
    iconAnchor: [15, 40]
  });

  var marker = null;
  var selected = null;

  function updateSelection(latlng) {
    selected = latlng;
    document.getElementById('coords').innerText =
      latlng.lat.toFixed(6) + ', ' + latlng.lng.toFixed(6);
    document.getElementById('confirm').disabled = false;
  }

  function placePin(latlng) {
    if (marker) {
      marker.setLatLng(latlng);
    } else {
      marker = L.marker(latlng, {icon: pinIcon, draggable: true}).addTo(map);
      marker.on('drag', function(ev) { updateSelection(ev.target.getLatLng()); });
    }
    updateSelection(latlng);
  }

  map.on('click', function(e) { placePin(e.latlng); });

  var searchForm = document.getElementById('search-form');
  var searchInput = document.getElementById('search-input');
  var searchResults = document.getElementById('search-results');

  searchForm.addEventListener('submit', function(e) {
    e.preventDefault();
    var query = searchInput.value.trim();
    if (!query) { return; }
    searchResults.innerHTML = '<div class="search-status">searching...</div>';
    fetch('https://nominatim.openstreetmap.org/search?format=json&limit=5&q=' + encodeURIComponent(query))
      .then(function(r) { return r.json(); })
      .then(function(results) {
        searchResults.innerHTML = '';
        if (!results.length) {
          searchResults.innerHTML = '<div class="search-status">no matches found</div>';
          return;
        }
        results.forEach(function(r) {
          var item = document.createElement('div');
          item.className = 'search-result';
          item.textContent = r.display_name;
          item.addEventListener('click', function() {
            var latlng = L.latLng(parseFloat(r.lat), parseFloat(r.lon));
            map.setView(latlng, 16);
            placePin(latlng);
            searchResults.innerHTML = '';
          });
          searchResults.appendChild(item);
        });
      })
      .catch(function() {
        searchResults.innerHTML = '<div class="search-status">search failed (no network?)</div>';
      });
  });

  document.getElementById('confirm').addEventListener('click', function() {
    document.getElementById('confirm').disabled = true;
    fetch('/select', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({lat: selected.lat, lon: selected.lng})
    }).then(function() {
      document.body.innerHTML =
        '<div style="padding:40px;font-size:16px;color:#e3e3e3;background:#1e1f22;' +
        'height:100%;font-family:-apple-system,BlinkMacSystemFont,\\'Segoe UI\\',Roboto,sans-serif">' +
        'Location set.<br><br>You can close this window.</div>';
    });
  });
</script>
</body>
</html>
"""


class MapPickerCancelledError(RuntimeError):
    pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _build_page(center_lat: float, center_lon: float, zoom: int) -> bytes:
    html = (
        _PAGE_TEMPLATE.replace("__CENTER_LAT__", str(center_lat))
        .replace("__CENTER_LON__", str(center_lon))
        .replace("__ZOOM__", str(zoom))
    )
    return html.encode("utf-8")


def pick_location_from_map(
    center_lat: float = 20.0, center_lon: float = 0.0, zoom: int = 2
) -> tuple[float, float]:
    """Open a map window and block until the user clicks a point and
    confirms it. Returns (latitude, longitude).

    Raises MapPickerCancelledError if the window is closed without a
    selection being confirmed.
    """
    selection: "queue.Queue[tuple[float, float]]" = queue.Queue(maxsize=1)
    page = _build_page(center_lat, center_lon, zoom)
    port = _free_port()
    window = None  # assigned below; referenced by Handler via closure

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, *args) -> None:
            pass  # keep the terminal quiet

        def do_GET(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(page)

        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(length))
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")
            try:
                selection.put_nowait((float(data["lat"]), float(data["lon"])))
            except queue.Full:
                pass
            if window is not None:
                threading.Thread(target=window.destroy, daemon=True).start()

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        window = webview.create_window(
            "iloc -- pick a location", f"http://127.0.0.1:{port}/", width=1000, height=700
        )
        webview.start()
    finally:
        server.shutdown()

    try:
        return selection.get_nowait()
    except queue.Empty:
        raise MapPickerCancelledError("No location was selected (window closed without confirming).")
