// Live-tracking page for emergency contacts. Polls the tracking API and keeps
// the map centred on the latest location until the emergency ends.
(function () {
  "use strict";

  var POLL_MS = 10000;
  var root = document.getElementById("app");
  var endpoint = root.dataset.endpoint;
  var els = {
    badge: document.getElementById("badge"),
    title: document.getElementById("title"),
    subtitle: document.getElementById("subtitle"),
    gmaps: document.getElementById("gmaps"),
    call: document.getElementById("call"),
    updated: document.getElementById("updated"),
  };

  var map = L.map("map", { zoomControl: true }).setView([20.5937, 78.9629], 4); // India overview
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  }).addTo(map);

  var marker = null;
  var accuracy = null;
  var trail = L.polyline([], { weight: 4, opacity: 0.7 }).addTo(map);
  var centredOnce = false;
  var timer = null;

  function formatTime(iso) {
    return iso ? new Date(iso).toLocaleString() : "";
  }

  function render(data) {
    var active = data.status === "active";
    els.badge.textContent = active ? "EMERGENCY ACTIVE" : "EMERGENCY ENDED";
    els.badge.className = "badge " + (active ? "active" : "ended");
    els.title.textContent = active ? data.name + " may need help" : data.name + " is marked safe";
    els.subtitle.textContent = active
      ? "Started " + formatTime(data.started_at) + ". This page refreshes automatically."
      : "The emergency ended " + formatTime(data.ended_at) + ". Location sharing has stopped.";

    els.call.hidden = !active;
    els.call.textContent = "Call emergency services (" + data.emergency_number + ")";
    els.call.href = "tel:" + data.emergency_number;

    if (!active || !data.latest) {
      els.gmaps.hidden = true;
      if (marker) { map.removeLayer(marker); marker = null; }
      if (accuracy) { map.removeLayer(accuracy); accuracy = null; }
      trail.setLatLngs([]);
      els.updated.textContent = active ? "Waiting for the first GPS fix…" : "";
      return;
    }

    var latest = data.latest;
    var pos = [latest.lat, latest.lng];
    if (!marker) {
      marker = L.marker(pos, { title: data.name }).addTo(map);
    } else {
      marker.setLatLng(pos);
    }
    if (latest.accuracy_m) {
      if (!accuracy) {
        accuracy = L.circle(pos, { radius: latest.accuracy_m, weight: 1, fillOpacity: 0.1 }).addTo(map);
      } else {
        accuracy.setLatLng(pos).setRadius(latest.accuracy_m);
      }
    }
    trail.setLatLngs(data.path);
    if (!centredOnce) {
      map.setView(pos, 16);
      centredOnce = true;
    } else {
      map.panTo(pos);
    }

    els.gmaps.hidden = false;
    els.gmaps.href = "https://www.google.com/maps/search/?api=1&query=" + latest.lat + "," + latest.lng;
    els.updated.textContent = "Last updated " + formatTime(latest.recorded_at) +
      (data.gps_available ? "" : " (approximate: last known location)");
  }

  function poll() {
    fetch(endpoint, { headers: { Accept: "application/json" }, cache: "no-store" })
      .then(function (res) {
        if (!res.ok) { throw new Error("HTTP " + res.status); }
        return res.json();
      })
      .then(function (data) {
        render(data);
        if (data.status !== "active" && timer) { clearInterval(timer); timer = null; }
      })
      .catch(function () {
        els.updated.textContent = "Connection problem, retrying…";
      });
  }

  poll();
  timer = setInterval(poll, POLL_MS);
})();
