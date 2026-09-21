import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui

BarWidget {
  id: root
  moduleName: "wdg.autofull"

  property bool isOn: false
  property string mode: "maximized"
  property bool refreshPending: false
  property bool syncPending: false
  property bool watchersReady: false

  readonly property string stateHome: Quickshell.env("XDG_STATE_HOME") || Quickshell.env("HOME") + "/.local/state"
  readonly property string configHome: Quickshell.env("XDG_CONFIG_HOME") || Quickshell.env("HOME") + "/.config"

  readonly property string modeLabel: root.mode === "fullscreen" ? "Full (SUPER+F)" : "Full width (SUPER+ALT+F)"

  // Bundled toggle script, resolved relative to this file so the plugin is
  // self-contained wherever it is installed.
  readonly property string scriptPath: decodeURIComponent(Qt.resolvedUrl("bin/omarchy-autofull-workspace").toString().replace(/^file:\/\//, ""))

  function refresh() {
    if (probe.running) root.refreshPending = true
    else probe.running = true
  }

  function synchronize() {
    syncDelay.restart()
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "\uf065"
    active: root.isOn
    dimmed: !root.isOn
    tooltipText: (root.isOn ? "AutoFull: On" : "AutoFull: Off") + " · " + root.modeLabel + " · right-click: mode"
    onPressed: function(button) {
      if (!root.bar) return
      Quickshell.execDetached([root.scriptPath, button === Qt.RightButton ? "cycle" : "toggle"])
    }
  }

  // The flag file's presence is on/off; the conf file holds the mode.
  Process {
    id: probe
    command: [root.scriptPath, "bar"]
    onExited: function() {
      if (root.refreshPending) {
        root.refreshPending = false
        root.refresh()
      }
    }
    stdout: SplitParser {
      onRead: function(line) {
        var parts = String(line).trim().split(":")
        root.isOn = parts[0] === "on"
        if (parts[1]) root.mode = parts[1]
      }
    }
  }

  // Coalesce editor writes and retain changes arriving during an active sync.
  Timer {
    id: syncDelay
    interval: 100
    onTriggered: {
      if (synchronizer.running) root.syncPending = true
      else synchronizer.running = true
    }
  }

  Process {
    id: synchronizer
    command: [root.scriptPath, "sync"]
    onExited: function() {
      // The helper creates the parent directories before watches are attached.
      root.watchersReady = true
      root.refresh()
      if (root.syncPending) {
        root.syncPending = false
        root.synchronize()
      }
    }
  }

  // FileView also tracks creation/replacement of a missing target file.
  FileView {
    path: root.watchersReady ? root.stateHome + "/omarchy/toggles/hypr/autofull-workspace.lua" : ""
    watchChanges: true
    printErrors: false
    onFileChanged: root.refresh()
    onLoaded: root.refresh()
  }

  FileView {
    path: root.watchersReady ? root.configHome + "/omarchy/autofull-workspace.conf" : ""
    watchChanges: true
    printErrors: false
    onFileChanged: root.synchronize()
    onLoaded: root.synchronize()
  }

  property int restoreAttempts: 0

  function recover() {
    root.restoreAttempts = 3
    restoreDelay.restart()
  }

  IpcHandler {
    target: "autofull"
    function restore(): void { root.recover() }
  }

  Timer {
    id: restoreDelay
    interval: 1000
    onTriggered: {
      if (restorer.running) restart()
      else {
        root.restoreAttempts--
        restorer.running = true
      }
    }
  }

  Process {
    id: restorer
    command: [root.scriptPath, "restore"]
    onExited: function(exitCode, exitStatus) {
      if ((exitCode !== 0 || exitStatus !== 0) && root.restoreAttempts > 0)
        restoreDelay.restart()
    }
  }

  Component.onCompleted: root.synchronize()
}
