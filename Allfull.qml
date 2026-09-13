import QtQuick
import Quickshell
import Quickshell.Io
import qs.Ui

BarWidget {
  id: root
  moduleName: "wdg.allfull"

  property bool isOn: false
  property string mode: "maximized"

  readonly property string modeLabel: root.mode === "fullscreen" ? "Full (SUPER+F)" : "Full width (SUPER+ALT+F)"

  // Bundled toggle script, resolved relative to this file so the plugin is
  // self-contained wherever it is installed.
  readonly property string scriptPath: Qt.resolvedUrl("bin/omarchy-allfull-workspace").toString().replace("file://", "")

  function refresh() {
    probe.running = true
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
      if (button === Qt.RightButton) root.bar.run("'" + root.scriptPath + "' cycle")
      else root.bar.run("'" + root.scriptPath + "' toggle")
    }
  }

  // The flag file's presence is on/off; the conf file holds the mode.
  Process {
    id: probe
    command: [root.scriptPath, "bar"]
    stdout: SplitParser {
      onRead: function(line) {
        var parts = String(line).trim().split(":")
        root.isOn = parts[0] === "on"
        if (parts[1]) root.mode = parts[1]
      }
    }
  }

  // Watch the directory: FileView can't observe a file that doesn't exist yet.
  FileView {
    path: Quickshell.env("HOME") + "/.local/state/omarchy/toggles/hypr"
    watchChanges: true
    printErrors: false
    onFileChanged: root.refresh()
  }

  FileView {
    path: Quickshell.env("HOME") + "/.config/omarchy/allfull-workspace.conf"
    watchChanges: true
    printErrors: false
    onFileChanged: root.refresh()
    onLoaded: root.refresh()
  }

  Component.onCompleted: root.refresh()
}
