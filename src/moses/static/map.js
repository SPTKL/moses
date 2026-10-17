"use strict";

let leafletPromise;
function ensureLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  if (!leafletPromise) {
    leafletPromise = new Promise((resolve, reject) => {
      const css = document.createElement("link");
      css.rel = "stylesheet"; css.href = "/assets/vendor/leaflet.css";
      document.head.append(css);
      const script = document.createElement("script");
      script.src = "/assets/vendor/leaflet.js";
      script.onload = () => window.L ? resolve(window.L) : reject(new Error("Map library did not initialize."));
      script.onerror = () => reject(new Error("Local map library could not be loaded."));
      document.head.append(script);
    }).catch(error => { leafletPromise = null; throw error; });
  }
  return leafletPromise;
}

export async function mountMap(container, collection, onSelect) {
  const L = await ensureLeaflet();
  const map = L.map(container, { zoomControl: false, attributionControl: true, preferCanvas: true, worldCopyJump: false });
  map.setView([0, 0], 2);
  const features = Array.isArray(collection.features) ? collection.features : [];
  const layers = [];
  let selected = -1, tiles = null;
  features.forEach((feature, index) => {
    const layer = L.geoJSON(feature, {
      style: () => ({ color: "#294b90", weight: 2, fillColor: "#6d90d2", fillOpacity: .44 }),
      pointToLayer: (_feature, latlng) => L.circleMarker(latlng, { radius: 5, color: "#294b90", weight: 1.5, fillColor: "#6d90d2", fillOpacity: .85 })
    }).addTo(map);
    layer.on("click", () => select(index));
    layers.push(layer);
  });
  const all = L.featureGroup(layers);
  function fit() { const bounds = all.getBounds(); if (bounds.isValid()) map.fitBounds(bounds.pad(.12), { maxZoom: 16 }); }
  function clearSelection() {
    if (selected >= 0) layers[selected].setStyle({ color: "#294b90", weight: 2, fillColor: "#6d90d2", fillOpacity: .44 });
    selected = -1;
  }
  function select(index) {
    if (index < 0 || index >= features.length) return;
    clearSelection();
    selected = index;
    layers[index].setStyle({ color: "#172b53", weight: 3, fillColor: "#3659a5", fillOpacity: .72 });
    layers[index].eachLayer(part => part.bringToFront?.());
    onSelect(index, features[index]);
  }
  function basemap(enabled) {
    if (tiles) { map.removeLayer(tiles); tiles = null; }
    if (enabled) {
      tiles = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a>',
        maxZoom: 19, referrerPolicy: "origin"
      });
      tiles.addTo(map);
      tiles.bringToBack();
    }
  }
  if (layers.length) fit();
  requestAnimationFrame(() => { if (container.isConnected) map.invalidateSize(); });
  return { zoomIn: () => map.zoomIn(), zoomOut: () => map.zoomOut(), fit, select, clearSelection, basemap, dispose: () => map.remove() };
}
