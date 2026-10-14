import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import QtQuick.Dialogs
import QtQuick.Effects

ApplicationWindow {
    id: win
    width: 1320; height: 850
    minimumWidth: 860; minimumHeight: 600
    visible: true
    title: s.rootName ? s.rootName + " — Mapper" : "Mapper"
    property var s: backend.state
    property var tr: backend.translations
    property var exts: backend.extensions
    readonly property bool searching: s.query !== "" || s.extension !== ""
    property string targetPath: ""
    property string action: ""
    property real fluid: Math.max(0.95, Math.min(1.12, 0.75 + width / 5000))
    property int motion: s.reducedMotion ? 0 : 160
    readonly property var chartColors: ["#719f87", "#9cbac6", "#d8b882", "#b79ab9", "#d69a8c", "#98b695", "#9ea9b6"]

    // ── Palette per tema: unica fonte dei colori / Per-theme palette: single source of colors ──
    readonly property var palettes: ({
        light: { bg: "#e9eef1", surface: "#f4f7f8", inset: "#e3e9ed", ink: "#22383c", muted: "#5f757b",
                 accent: "#356b59", onAccent: "#ffffff", rim: "#ffffff", line: "#d0dce1", hover: "#ffffff",
                 selection: "#d5e6dc", danger: "#a43f38", shadow: "#26788d99", scrim: "#4d1c2a30" },
        dark:  { bg: "#1d232b", surface: "#262f3a", inset: "#1a2028", ink: "#edf3f5", muted: "#9fb0bb",
                 accent: "#b4d3c1", onAccent: "#1e3a2c", rim: "#35424f", line: "#35424f", hover: "#313d4a",
                 selection: "#34503f", danger: "#ffb4a9", shadow: "#60000000", scrim: "#80000000" },
        blue:  { bg: "#121a28", surface: "#1a2435", inset: "#0f1622", ink: "#e8f0fb", muted: "#98abc6",
                 accent: "#8dbcf1", onAccent: "#0d2440", rim: "#2a3a54", line: "#2a3a54", hover: "#23324a",
                 selection: "#1f3a5e", danger: "#ffb4a9", shadow: "#60000000", scrim: "#80000000" },
        red:   { bg: "#221819", surface: "#2d2123", inset: "#1b1314", ink: "#f8eded", muted: "#c4a9aa",
                 accent: "#efaa97", onAccent: "#3d1a12", rim: "#46343a", line: "#46343a", hover: "#3a2b2d",
                 selection: "#4d302b", danger: "#ff8f8f", shadow: "#60000000", scrim: "#80000000" }
    })
    readonly property var pal: palettes[s.theme === "system" ? (Qt.styleHints.colorScheme === Qt.Dark ? "dark" : "light") : s.theme] || palettes.light

    color: pal.bg
    palette.window: pal.surface
    palette.windowText: pal.ink
    palette.base: pal.inset
    palette.text: pal.ink
    palette.button: pal.surface
    palette.buttonText: pal.ink
    palette.highlight: pal.accent
    palette.highlightedText: pal.onAccent
    font.family: uiFont
    font.pixelSize: Math.round(14 * fluid)

    // ── Utilità / Helpers ──
    function t(key) { return tr[key] || key }
    function fmt(key, values) {
        let text = t(key)
        for (let k in values) text = text.replace("{" + k + "}", values[k])
        return text
    }
    function num(n) { return Number(n).toLocaleString(Qt.locale(s.language), "f", 0) }
    function baseName(path) { return path.replace(/[\\/]+$/, "").split(/[\\/]/).pop() }
    function parentDir(path) {
        let p = path.replace(/[\\/]+$/, "")
        let i = p.search(/[\\/][^\\/]*$/)
        return i > 0 ? p.slice(0, i) : p
    }
    function fileUrl(path) { return "file:///" + path.replace(/\\/g, "/").replace(/^\/+/, "") }
    function escapeHtml(text) { return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;") }
    // Evidenzia la parte cercata nel nome / Highlights the searched part of the name
    function highlight(name) {
        let q = s.query.trim()
        let i = q ? name.toLowerCase().indexOf(q.toLowerCase()) : -1
        if (i < 0) return escapeHtml(name)
        return escapeHtml(name.slice(0, i)) + "<b><font color='" + pal.accent + "'>" + escapeHtml(name.slice(i, i + q.length))
               + "</font></b>" + escapeHtml(name.slice(i + q.length))
    }
    function slices() {
        let list = [], other = 0
        for (let i = 0; i < exts.length; i++) {
            if (i < chartColors.length) list.push({ label: exts[i].label, fraction: exts[i].fraction, color: chartColors[i] })
            else other += exts[i].fraction
        }
        if (other > 0) list.push({ label: "", fraction: other, color: pal.muted })
        return list
    }
    function nameDialog(kind, path, current) { action = kind; targetPath = path; itemName.text = current || ""; editDialog.open() }
    function removeDialog(path) { targetPath = path; deleteDialog.open() }
    function openContext(path, item, x, y) { targetPath = path; contextMenu.popup(item, x, y) }
    // Doppio clic / Invio: cartella → apri o mostra nell'albero, file → apri
    // Double-click / Enter: folder → expand or show in tree, file → open
    function activate(item) {
        if (!item) return
        if (!item.directory) backend.openPath(item.fullPath)
        else if (searching) backend.reveal(item.fullPath)
        else backend.toggle(item.fullPath)
    }
    function saveMap() {
        let folder = parentDir(s.path)
        let name = (s.rootName.replace(/[\\/:*?"<>|]/g, "") || "map") + "-map.txt"
        saveDialog.currentFolder = fileUrl(folder)
        saveDialog.selectedFile = fileUrl(folder + "/" + name)
        saveDialog.open()
    }
    function hint(item, text) {
        if (text) {
            let p = item.mapToItem(win.contentItem, item.width / 2, item.height)
            tip.anchorX = p.x; tip.anchorY = p.y; tip.text = text; tip.target = item
        } else if (tip.target === item) {
            tip.target = null
        }
    }

    // ── Componenti condivisi / Shared components ──
    component Icon: Label {
        property string glyph: ""
        text: glyph
        visible: glyph !== "" && iconFont !== ""
        font.family: iconFont
        font.pixelSize: 16
        color: win.pal.ink
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }
    component Caption: Label { color: win.pal.muted; font.pixelSize: Math.round(12 * win.fluid) }
    component Heading: Label { color: win.pal.ink; font.pixelSize: Math.round(18 * win.fluid); font.weight: Font.DemiBold }

    component SoftButton: Button {
        id: b
        property bool primary: false
        property bool destructive: false
        property string glyph: ""
        property string tip: ""
        implicitHeight: 40
        implicitWidth: Math.max(implicitHeight, row.implicitWidth + (b.text ? 30 : 0))
        hoverEnabled: true
        focusPolicy: Qt.TabFocus
        opacity: enabled ? 1 : 0.4
        scale: down ? 0.97 : 1
        Behavior on scale { NumberAnimation { duration: win.motion } }
        Accessible.name: text || tip
        onHoveredChanged: win.hint(b, hovered ? b.tip : "")
        onVisibleChanged: if (!visible) win.hint(b, "")
        readonly property color fg: primary ? win.pal.onAccent : destructive ? win.pal.danger : win.pal.ink
        contentItem: Item {
            implicitWidth: row.implicitWidth
            implicitHeight: row.implicitHeight
            Row {
                id: row
                anchors.centerIn: parent
                spacing: 8
                Icon { glyph: b.glyph; color: b.fg; font.pixelSize: b.text ? 14 : 15; anchors.verticalCenter: parent.verticalCenter }
                Label {
                    text: b.text; visible: b.text !== ""
                    color: b.fg; font.weight: b.primary ? Font.DemiBold : Font.Medium
                    anchors.verticalCenter: parent.verticalCenter
                }
            }
        }
        background: Rectangle {
            radius: 12
            color: b.primary ? (b.hovered ? Qt.lighter(win.pal.accent, 1.08) : win.pal.accent)
                 : b.down ? win.pal.inset : b.hovered ? win.pal.hover : b.flat ? "transparent" : win.pal.surface
            border.width: b.visualFocus ? 2 : (b.flat || b.primary ? 0 : 1)
            border.color: b.visualFocus ? win.pal.accent : win.pal.line
            Behavior on color { ColorAnimation { duration: win.motion } }
        }
    }

    component SoftField: TextField {
        id: f
        property string glyph: ""
        implicitHeight: 42
        color: win.pal.ink
        placeholderTextColor: win.pal.muted
        selectionColor: win.pal.accent
        selectedTextColor: win.pal.onAccent
        selectByMouse: true
        leftPadding: glyph && iconFont ? 40 : 14
        rightPadding: 14
        opacity: enabled ? 1 : 0.6
        background: Rectangle {
            radius: 12; color: win.pal.inset
            border.color: f.activeFocus ? win.pal.accent : win.pal.line
            border.width: f.activeFocus ? 2 : 1
            Behavior on border.color { ColorAnimation { duration: win.motion } }
            Icon {
                glyph: f.glyph; color: f.activeFocus ? win.pal.accent : win.pal.muted; font.pixelSize: 15
                anchors.left: parent.left; anchors.leftMargin: 14; anchors.verticalCenter: parent.verticalCenter
            }
        }
    }

    component Surface: Rectangle {
        radius: 24; color: win.pal.surface
        border.width: 1; border.color: win.pal.rim
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true; shadowBlur: 0.7; shadowColor: win.pal.shadow
            shadowHorizontalOffset: 4; shadowVerticalOffset: 6
        }
    }

    component SoftScrollBar: ScrollBar {
        id: sb
        contentItem: Rectangle {
            implicitWidth: 6; implicitHeight: 6; radius: 3; color: win.pal.muted
            opacity: sb.pressed ? 0.75 : sb.active || sb.hovered ? 0.45 : 0
            Behavior on opacity { NumberAnimation { duration: win.motion } }
        }
    }

    component SoftMenu: Menu {
        id: m
        padding: 6
        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: win.motion }
            NumberAnimation { property: "scale"; from: 0.97; to: 1; duration: win.motion; easing.type: Easing.OutCubic }
        }
        exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: win.motion / 2 } }
        onAboutToShow: win.hint(tip.target || win.contentItem, "")
        background: Rectangle {
            implicitWidth: 248
            radius: 14; color: win.pal.surface
            border.width: 1; border.color: win.pal.line
            layer.enabled: true
            layer.effect: MultiEffect { shadowEnabled: true; shadowBlur: 0.6; shadowColor: win.pal.shadow; shadowVerticalOffset: 4 }
        }
    }

    component SoftMenuItem: MenuItem {
        id: mi
        property string glyph: ""
        property string hint: ""
        property bool destructive: false
        implicitHeight: visible ? 36 : 0
        height: visible ? implicitHeight : 0
        leftPadding: 10; rightPadding: 12
        opacity: enabled ? 1 : 0.4
        contentItem: RowLayout {
            spacing: 10
            Item {
                Layout.preferredWidth: 18; Layout.fillHeight: true; visible: iconFont !== ""
                Icon { anchors.centerIn: parent; glyph: mi.glyph; font.pixelSize: 14; color: mi.destructive ? win.pal.danger : win.pal.muted }
            }
            Label { text: mi.text; Layout.fillWidth: true; elide: Text.ElideMiddle; color: mi.destructive ? win.pal.danger : win.pal.ink }
            Label { text: mi.hint; visible: mi.hint !== ""; color: win.pal.muted; font.pixelSize: Math.round(12 * win.fluid) }
        }
        background: Rectangle { radius: 9; color: mi.highlighted ? win.pal.inset : "transparent" }
    }

    component SoftSeparator: MenuSeparator {
        topPadding: 4; bottomPadding: 4; leftPadding: 8; rightPadding: 8
        contentItem: Rectangle { implicitHeight: 1; color: win.pal.line }
    }

    component SoftDialog: Dialog {
        id: d
        property string acceptText: win.t("ok")
        property string rejectText: win.t("cancel")
        property string secondaryText: ""
        property string acceptGlyph: ""
        property string secondaryGlyph: ""
        property bool destructive: false
        property bool canAccept: true
        signal secondaryClicked()
        anchors.centerIn: parent
        width: Math.min(win.width - 64, 460)
        modal: true
        focus: true
        padding: 22; topPadding: 4; bottomPadding: 8
        // Invio conferma il dialogo / Enter confirms the dialog
        Shortcut { sequences: ["Return", "Enter"]; enabled: d.opened && d.canAccept && d.acceptText !== ""; onActivated: d.accept() }
        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: win.motion }
            NumberAnimation { property: "scale"; from: 0.96; to: 1; duration: win.motion; easing.type: Easing.OutCubic }
        }
        exit: Transition { NumberAnimation { property: "opacity"; to: 0; duration: win.motion / 2 } }
        Overlay.modal: Rectangle { color: win.pal.scrim }
        background: Rectangle {
            radius: 22; color: win.pal.surface
            border.width: 1; border.color: win.pal.rim
            layer.enabled: true
            layer.effect: MultiEffect { shadowEnabled: true; shadowBlur: 0.8; shadowColor: win.pal.shadow; shadowVerticalOffset: 8 }
        }
        header: Label {
            text: d.title; padding: 22; bottomPadding: 10; elide: Text.ElideRight
            color: win.pal.ink; font.pixelSize: Math.round(18 * win.fluid); font.weight: Font.DemiBold
        }
        footer: Item {
            implicitHeight: buttons.implicitHeight + 40
            RowLayout {
                id: buttons
                anchors.fill: parent; anchors.margins: 22; anchors.topMargin: 14; anchors.bottomMargin: 22
                spacing: 10
                SoftButton { text: d.secondaryText; glyph: d.secondaryGlyph; visible: d.secondaryText !== ""; onClicked: d.secondaryClicked() }
                Item { Layout.fillWidth: true }
                SoftButton { text: d.rejectText; visible: d.rejectText !== ""; onClicked: d.reject() }
                SoftButton {
                    text: d.acceptText; glyph: d.acceptGlyph; visible: d.acceptText !== ""
                    primary: !d.destructive; destructive: d.destructive; enabled: d.canAccept
                    onClicked: d.accept()
                }
            }
        }
    }

    component SoftCombo: ComboBox {
        id: c
        property var labelFor: function(value) { return value }
        implicitHeight: 40
        displayText: labelFor(currentValue)
        contentItem: Label {
            leftPadding: 14; rightPadding: 34
            text: c.displayText; color: win.pal.ink
            verticalAlignment: Text.AlignVCenter; elide: Text.ElideRight
        }
        indicator: Icon {
            glyph: "\uE70D"; font.pixelSize: 11; color: win.pal.muted
            x: c.width - width - 14; y: (c.height - height) / 2
        }
        background: Rectangle {
            radius: 12; color: c.hovered ? win.pal.hover : win.pal.inset
            border.width: c.visualFocus || c.popup.visible ? 2 : 1
            border.color: c.visualFocus || c.popup.visible ? win.pal.accent : win.pal.line
        }
        delegate: ItemDelegate {
            id: option
            required property var modelData
            required property int index
            width: ListView.view.width; height: 34
            highlighted: c.highlightedIndex === index
            contentItem: Label {
                text: c.labelFor(option.modelData)
                color: option.index === c.currentIndex ? win.pal.accent : win.pal.ink
                font.weight: option.index === c.currentIndex ? Font.DemiBold : Font.Normal
                verticalAlignment: Text.AlignVCenter
            }
            background: Rectangle { radius: 8; color: option.highlighted ? win.pal.inset : "transparent" }
        }
        popup: Popup {
            y: c.height + 4; width: c.width; padding: 6
            implicitHeight: contentItem.implicitHeight + 12
            contentItem: ListView {
                clip: true; implicitHeight: contentHeight
                model: c.popup.visible ? c.delegateModel : null
                currentIndex: c.highlightedIndex
            }
            background: Rectangle { radius: 12; color: win.pal.surface; border.width: 1; border.color: win.pal.line }
        }
    }

    component SoftSwitch: Switch {
        id: sw
        indicator: Rectangle {
            implicitWidth: 42; implicitHeight: 24
            x: sw.leftPadding; y: (sw.height - height) / 2
            radius: 12; color: sw.checked ? win.pal.accent : win.pal.inset
            border.width: 1; border.color: sw.checked ? win.pal.accent : win.pal.line
            Rectangle {
                x: sw.checked ? parent.width - width - 3 : 3; y: 3
                width: 18; height: 18; radius: 9
                color: sw.checked ? win.pal.onAccent : win.pal.muted
                Behavior on x { NumberAnimation { duration: win.motion } }
            }
        }
        contentItem: Label {
            text: sw.text; color: win.pal.ink
            leftPadding: sw.indicator.width + 12; verticalAlignment: Text.AlignVCenter
        }
    }

    // Tooltip unico e coerente col tema / Single, theme-consistent tooltip
    ToolTip {
        id: tip
        objectName: "toolTip"
        property Item target: null
        property real anchorX: 0
        property real anchorY: 0
        visible: target !== null && text !== ""
        delay: 550
        x: Math.max(8, Math.min(win.width - width - 8, anchorX - width / 2))
        y: anchorY + 6
        padding: 8
        contentItem: Label { text: tip.text; color: win.pal.bg; font.pixelSize: Math.round(12 * win.fluid) }
        background: Rectangle { radius: 8; color: win.pal.ink; opacity: 0.94 }
    }

    // ── Dialoghi di sistema / System dialogs ──
    FolderDialog {
        id: folderDialog
        title: win.t("select_folder")
        currentFolder: win.s.path ? win.fileUrl(win.s.path) : ""
        onAccepted: backend.openFolder(selectedFolder.toString())
    }
    FileDialog {
        id: saveDialog
        title: win.t("export_map"); fileMode: FileDialog.SaveFile
        nameFilters: [win.t("text_files") + " (*.txt)"]; defaultSuffix: "txt"
        onAccepted: backend.exportMap(selectedFile.toString())
    }

    Shortcut { sequence: "Ctrl+O"; enabled: !win.s.busy; onActivated: folderDialog.open() }
    Shortcut { sequence: "Ctrl+L"; onActivated: { pathField.forceActiveFocus(); pathField.selectAll() } }
    Shortcut { sequence: "Ctrl+F"; enabled: win.s.scanned; onActivated: { filterField.forceActiveFocus(); filterField.selectAll() } }
    Shortcut { sequence: "Ctrl+E"; enabled: win.s.scanned && !win.s.busy; onActivated: exportDialog.open() }
    Shortcut { sequence: "Ctrl+S"; enabled: win.s.scanned && !win.s.busy; onActivated: win.saveMap() }
    Shortcut { sequence: "F5"; enabled: !win.s.busy && win.s.path !== ""; onActivated: backend.scan() }
    Shortcut { sequence: "Escape"; enabled: win.s.busy && win.s.cancellable; onActivated: backend.cancel() }

    Rectangle { width: 320; height: 320; radius: 145; rotation: 24; x: win.width - 200; y: -150; color: win.pal.accent; opacity: 0.045 }
    Rectangle { width: 260; height: 260; radius: 110; rotation: -18; x: -180; y: win.height - 250; color: win.pal.accent; opacity: 0.045 }

    ColumnLayout {
        anchors.fill: parent; anchors.margins: win.width < 1000 ? 18 : 28
        spacing: 16

        // ── Intestazione / Header ──
        RowLayout {
            Layout.fillWidth: true; spacing: 14
            Rectangle {
                width: 44; height: 44; radius: 15; color: win.pal.accent; rotation: -8
                Label {
                    anchors.centerIn: parent; rotation: 8
                    text: iconFont ? "\uE890" : "◈"; font.family: iconFont || uiFont
                    font.pixelSize: 22; color: win.pal.onAccent
                }
            }
            ColumnLayout {
                spacing: 0
                Label { text: "Mapper"; color: win.pal.ink; font.pixelSize: Math.round(24 * win.fluid); font.weight: Font.DemiBold }
                Caption { text: win.t("workspace_subtitle") }
            }
            Item { Layout.fillWidth: true }
            SoftButton { flat: true; glyph: "\uE897"; text: iconFont ? "" : win.t("guide"); tip: win.t("guide"); onClicked: guide.open() }
            SoftButton { glyph: "\uE713"; text: win.t("settings"); onClicked: settings.open() }
        }

        // ── Barra di mappatura / Mapping bar ──
        RowLayout {
            Layout.fillWidth: true; spacing: 10
            SoftField {
                id: pathField; objectName: "pathField"
                Layout.fillWidth: true; glyph: "\uE8B7"
                placeholderText: win.t("path_placeholder")
                enabled: !win.s.busy
                Accessible.name: win.t("select_folder")
                onAccepted: { backend.openFolder(text); tree.forceActiveFocus() }
            }
            // Il campo segue il percorso attivo solo quando non lo si sta modificando
            // The field follows the active path only while it is not being edited
            Binding { target: pathField; property: "text"; value: win.s.path; when: !pathField.activeFocus; restoreMode: Binding.RestoreNone }
            SoftButton {
                glyph: "\uE81C"; text: iconFont ? "" : win.t("recent"); tip: win.t("recent")
                enabled: !win.s.busy && backend.recent.length > 0
                onClicked: recentMenu.popup(this, 0, height + 6)
            }
            SoftButton { glyph: "\uE838"; text: win.t("browse"); enabled: !win.s.busy; onClicked: folderDialog.open() }
            SoftButton {
                id: mapButton; objectName: "mapButton"
                readonly property bool same: win.s.scanned && pathField.text === win.s.path
                text: win.s.busy ? win.t("cancel") : same ? win.t("refresh") : win.t("scan")
                glyph: win.s.busy ? "\uE711" : same ? "\uE72C" : "\uE8FD"
                tip: win.s.busy ? "Esc" : "F5"
                primary: !win.s.busy; destructive: win.s.busy
                enabled: win.s.busy ? win.s.cancellable : pathField.text.trim() !== ""
                onClicked: {
                    if (win.s.busy) { backend.cancel(); return }
                    backend.openFolder(pathField.text)
                    tree.forceActiveFocus()
                }
            }
        }

        ProgressBar {
            Layout.fillWidth: true; Layout.preferredHeight: 3; Layout.topMargin: -8
            opacity: win.s.busy ? 1 : 0
            Behavior on opacity { NumberAnimation { duration: win.motion } }
            indeterminate: win.s.progress < 0; value: Math.max(0, win.s.progress)
            background: Rectangle { color: win.pal.inset; radius: 2 }
            contentItem: Item {
                Rectangle {
                    width: parent.width * (win.s.progress < 0 ? 0.3 : win.s.progress)
                    height: parent.height; radius: 2; color: win.pal.accent
                    Behavior on width { NumberAnimation { duration: win.motion } }
                    SequentialAnimation on opacity {
                        running: win.s.progress < 0 && win.s.busy && !win.s.reducedMotion; loops: Animation.Infinite
                        NumberAnimation { to: 0.35; duration: 600 }
                        NumberAnimation { to: 1; duration: 600 }
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true; Layout.fillHeight: true; spacing: 18

            // ── Esplora + Cerca / Explorer + Search ──
            Surface {
                Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumWidth: 420
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 18; spacing: 12
                    RowLayout {
                        Layout.fillWidth: true; spacing: 6
                        Heading { text: win.t("explorer") }
                        Caption {
                            text: win.s.rootName; visible: win.s.scanned
                            elide: Text.ElideMiddle; Layout.maximumWidth: 240; Layout.leftMargin: 4
                        }
                        Item { Layout.fillWidth: true }
                        SoftButton {
                            flat: true; glyph: "\uE70E"; tip: win.t("collapse_all")
                            visible: iconFont !== "" && !win.searching; enabled: win.s.scanned
                            onClicked: backend.expandAll(false)
                        }
                        SoftButton {
                            flat: true; glyph: "\uE70D"; tip: win.t("expand_all")
                            visible: iconFont !== "" && !win.searching; enabled: win.s.scanned
                            onClicked: backend.expandAll(true)
                        }
                        SoftButton {
                            glyph: "\uE710"; text: win.t("new"); enabled: win.s.scanned && !win.s.busy
                            onClicked: { win.targetPath = win.s.path; createMenu.popup(this, 0, height + 6) }
                        }
                        SoftButton {
                            objectName: "exportButton"
                            glyph: "\uE74E"; text: win.t("export_map"); tip: "Ctrl+E"
                            enabled: win.s.scanned && !win.s.busy
                            onClicked: exportDialog.open()
                        }
                    }
                    SoftField {
                        id: filterField; objectName: "filterField"
                        Layout.fillWidth: true; glyph: "\uE721"
                        placeholderText: win.s.scanned ? win.t("quick_search") : win.t("search_needs_map")
                        text: win.s.query; enabled: win.s.scanned
                        rightPadding: clearQuery.visible ? 46 : 14
                        Accessible.name: win.t("quick_search")
                        onTextEdited: backend.setQuery(text)
                        onAccepted: { tree.forceActiveFocus(); if (tree.currentIndex < 0 && tree.count > 0) tree.currentIndex = 0 }
                        Keys.onDownPressed: { tree.forceActiveFocus(); if (tree.currentIndex < 0 && tree.count > 0) tree.currentIndex = 0 }
                        Keys.onEscapePressed: { if (text) backend.setQuery(""); else tree.forceActiveFocus() }
                        SoftButton {
                            id: clearQuery
                            anchors.right: parent.right; anchors.rightMargin: 6; anchors.verticalCenter: parent.verticalCenter
                            implicitHeight: 30; flat: true; glyph: "\uE711"; text: iconFont ? "" : "×"; tip: win.t("clear_search")
                            visible: filterField.text !== ""
                            onClicked: backend.setQuery("")
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 8
                        visible: win.searching
                        Rectangle {
                            visible: win.s.extension !== ""
                            implicitWidth: chip.implicitWidth + 20; implicitHeight: 28; radius: 14
                            color: chipArea.containsMouse ? win.pal.hover : win.pal.inset
                            border.width: 1; border.color: win.pal.line
                            Row {
                                id: chip; anchors.centerIn: parent; spacing: 6
                                Rectangle { width: 8; height: 8; radius: 4; anchors.verticalCenter: parent.verticalCenter; color: win.pal.accent }
                                Label {
                                    text: win.s.extension === "—" ? win.t("chart_no_ext") : win.s.extension
                                    color: win.pal.ink; font.pixelSize: Math.round(12 * win.fluid); anchors.verticalCenter: parent.verticalCenter
                                }
                                Icon { glyph: "\uE711"; font.pixelSize: 9; color: win.pal.muted; anchors.verticalCenter: parent.verticalCenter }
                            }
                            MouseArea {
                                id: chipArea; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor
                                onClicked: backend.setExtension(win.s.extension)
                            }
                        }
                        Caption { text: win.s.shown === 1 ? win.t("result_one") : win.fmt("results_count", { count: win.num(win.s.shown) }) }
                        Item { Layout.fillWidth: true }
                        SoftButton { flat: true; implicitHeight: 30; text: win.t("clear_filters"); onClicked: backend.clearFilters() }
                    }
                    Item {
                        Layout.fillWidth: true; Layout.fillHeight: true
                        ListView {
                            id: tree; objectName: "fileList"
                            anchors.fill: parent; clip: true
                            model: fileModel; reuseItems: true; cacheBuffer: 400
                            boundsBehavior: Flickable.StopAtBounds
                            ScrollBar.vertical: SoftScrollBar {}
                            currentIndex: -1
                            Keys.onPressed: function(event) {
                                let item = tree.currentItem
                                if (event.key === Qt.Key_Escape && win.searching) { backend.clearFilters(); event.accepted = true; return }
                                if (!item) return
                                let ctrl = event.modifiers & Qt.ControlModifier
                                let idle = !win.s.busy
                                if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) win.activate(item)
                                else if (event.key === Qt.Key_Right && item.directory && !win.searching) backend.setExpanded(item.fullPath, true)
                                else if (event.key === Qt.Key_Left && !win.searching) {
                                    if (item.directory && item.expanded) backend.setExpanded(item.fullPath, false)
                                    else { let p = fileModel.indexOf(item.parentPath); if (p >= 0) tree.currentIndex = p }
                                }
                                else if (event.key === Qt.Key_F2 && idle) win.nameDialog("rename", item.fullPath, item.itemName)
                                else if (event.key === Qt.Key_Delete && idle) win.removeDialog(item.fullPath)
                                else if (ctrl && event.key === Qt.Key_C) backend.clipboard(item.fullPath, "copy")
                                else if (ctrl && event.key === Qt.Key_X) backend.clipboard(item.fullPath, "cut")
                                else if (ctrl && event.key === Qt.Key_V && idle && win.s.clipboard !== "") backend.fileAction("paste", item.fullPath, "")
                                else if (event.key === Qt.Key_Menu || (event.key === Qt.Key_F10 && (event.modifiers & Qt.ShiftModifier)))
                                    win.openContext(item.fullPath, item, 48, item.height)
                                else return
                                event.accepted = true
                            }
                            Connections {
                                target: backend
                                function onRevealed(row) {
                                    tree.currentIndex = row
                                    tree.positionViewAtIndex(row, ListView.Center)
                                    tree.forceActiveFocus()
                                }
                            }
                            delegate: ItemDelegate {
                                id: row
                                objectName: "fileRow"
                                required property string itemName
                                required property string fullPath
                                required property bool directory
                                required property int level
                                required property bool expanded
                                required property string extension
                                required property string relativePath
                                required property string parentPath
                                required property string kind
                                required property int index
                                readonly property bool active: hovered || ListView.isCurrentItem
                                readonly property string location: relativePath.length > itemName.length
                                    ? relativePath.slice(0, relativePath.length - itemName.length - 1) : win.s.rootName
                                width: tree.width
                                height: win.searching ? 54 : 40
                                hoverEnabled: true
                                focusPolicy: Qt.NoFocus
                                leftPadding: 8; rightPadding: 6; topPadding: 0; bottomPadding: 0
                                opacity: win.s.clipboardMode === "cut" && win.s.clipboard === fullPath ? 0.5 : 1
                                onClicked: { tree.currentIndex = index; tree.forceActiveFocus() }
                                onDoubleClicked: win.activate(row)
                                Accessible.name: itemName
                                background: Rectangle {
                                    radius: 10
                                    color: row.ListView.isCurrentItem ? win.pal.selection : row.hovered ? win.pal.inset : "transparent"
                                    Behavior on color { ColorAnimation { duration: win.motion } }
                                }
                                contentItem: RowLayout {
                                    spacing: 6
                                    Item { Layout.preferredWidth: Math.min(row.level * 18, tree.width * 0.4); visible: row.level > 0 }
                                    Label {
                                        Layout.preferredWidth: 20; Layout.fillHeight: true
                                        visible: !win.searching
                                        text: !row.directory ? "" : iconFont ? (row.expanded ? "\uE70D" : "\uE76C") : (row.expanded ? "▾" : "▸")
                                        font.family: iconFont || uiFont; font.pixelSize: 10; color: win.pal.muted
                                        horizontalAlignment: Text.AlignHCenter; verticalAlignment: Text.AlignVCenter
                                        TapHandler { enabled: row.directory; onTapped: backend.toggle(row.fullPath) }
                                    }
                                    Icon {
                                        glyph: row.kind === "link" ? "\uE71B" : row.directory ? (row.expanded && !win.searching ? "\uE838" : "\uE8B7") : "\uE8A5"
                                        color: row.directory ? win.pal.accent : win.pal.muted
                                    }
                                    ColumnLayout {
                                        Layout.fillWidth: true; spacing: 1
                                        Label {
                                            Layout.fillWidth: true; elide: Text.ElideMiddle; color: win.pal.ink
                                            textFormat: win.searching ? Text.StyledText : Text.PlainText
                                            text: win.searching ? win.highlight(row.itemName) : row.itemName
                                        }
                                        Caption { Layout.fillWidth: true; text: row.location; visible: win.searching; elide: Text.ElideMiddle }
                                    }
                                    Caption { text: row.kind === "link" ? win.t("link_item") : row.extension; visible: !row.directory && !row.active && tree.width > 480 }
                                    Row {
                                        visible: row.active; spacing: 2
                                        SoftButton {
                                            flat: true; implicitHeight: 30; glyph: "\uE7AC"; tip: win.t("show_in_tree")
                                            visible: win.searching && iconFont !== ""; onClicked: backend.reveal(row.fullPath)
                                        }
                                        SoftButton {
                                            flat: true; implicitHeight: 30; glyph: "\uE8A7"; text: iconFont ? "" : "↗"; tip: win.t("open_file")
                                            onClicked: backend.openPath(row.fullPath)
                                        }
                                        SoftButton {
                                            flat: true; implicitHeight: 30; glyph: "\uE712"; text: iconFont ? "" : "…"; tip: win.t("more_actions")
                                            onClicked: { tree.currentIndex = row.index; win.openContext(row.fullPath, this, 0, height + 4) }
                                        }
                                    }
                                }
                                TapHandler {
                                    acceptedButtons: Qt.RightButton
                                    onTapped: function(point) {
                                        tree.currentIndex = row.index
                                        win.openContext(row.fullPath, row, point.position.x, point.position.y)
                                    }
                                }
                            }
                        }
                        // Stato vuoto: guida al primo passo / Empty state: guides the first step
                        ColumnLayout {
                            anchors.centerIn: parent; width: Math.min(parent.width - 32, 420)
                            spacing: 14; visible: tree.count === 0
                            Rectangle {
                                Layout.alignment: Qt.AlignHCenter; width: 84; height: 84; radius: 28; rotation: -6; color: win.pal.inset
                                Label {
                                    anchors.centerIn: parent; rotation: 6; font.pixelSize: 34; color: win.pal.accent
                                    font.family: iconFont || uiFont
                                    text: !iconFont ? "◈" : win.s.scanned ? "\uE721" : win.s.busy ? "\uE8FD" : "\uE898"
                                }
                            }
                            Heading {
                                Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                                text: win.s.scanned ? win.t("search_no_results") : win.s.busy ? win.t("scanning") : win.t("empty_title")
                            }
                            Caption {
                                Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.WordWrap
                                visible: text !== ""
                                text: win.s.scanned ? win.t("filter_empty_hint") : win.s.busy
                                      ? (win.s.progress >= 0 ? Math.round(win.s.progress * 100) + "%" : "") : win.t("drop_hint")
                            }
                            SoftButton {
                                Layout.alignment: Qt.AlignHCenter; primary: true; glyph: "\uE838"; text: win.t("browse")
                                visible: !win.s.scanned && !win.s.busy; onClicked: folderDialog.open()
                            }
                            SoftButton {
                                Layout.alignment: Qt.AlignHCenter; text: win.t("clear_filters")
                                visible: win.s.scanned && win.searching; onClicked: backend.clearFilters()
                            }
                            ColumnLayout {
                                Layout.fillWidth: true; Layout.topMargin: 8; spacing: 2
                                visible: !win.s.scanned && !win.s.busy && backend.recent.length > 0
                                Caption { text: win.t("recent"); Layout.leftMargin: 10 }
                                Repeater {
                                    model: backend.recent
                                    delegate: ItemDelegate {
                                        id: recentRow
                                        required property string modelData
                                        Layout.fillWidth: true; implicitHeight: 36; hoverEnabled: true
                                        onClicked: backend.openFolder(modelData)
                                        background: Rectangle { radius: 10; color: recentRow.hovered ? win.pal.inset : "transparent" }
                                        contentItem: RowLayout {
                                            spacing: 10
                                            Icon { glyph: "\uE8B7"; color: win.pal.accent; font.pixelSize: 14 }
                                            Label { text: recentRow.modelData; color: win.pal.ink; elide: Text.ElideMiddle; Layout.fillWidth: true }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    Caption {
                        Layout.fillWidth: true; elide: Text.ElideRight
                        text: win.searching ? win.t("search_hint") : win.t("explorer_hint")
                    }
                }
            }

            // ── Panoramica / Overview ──
            Surface {
                Layout.preferredWidth: Math.max(260, Math.min(340, win.width * 0.25))
                Layout.fillHeight: true
                ColumnLayout {
                    anchors.fill: parent; anchors.margins: 20; spacing: 14
                    Heading { text: win.t("overview") }
                    RowLayout {
                        Layout.fillWidth: true; spacing: 20
                        ColumnLayout {
                            spacing: 0
                            Label { text: win.num(win.s.files); color: win.pal.ink; font.pixelSize: Math.round(28 * win.fluid); font.weight: Font.DemiBold }
                            Caption { text: win.t("files") }
                        }
                        Rectangle { width: 1; height: 40; color: win.pal.line }
                        ColumnLayout {
                            spacing: 0
                            Label { text: win.num(win.s.folders); color: win.pal.ink; font.pixelSize: Math.round(28 * win.fluid); font.weight: Font.DemiBold }
                            Caption { text: win.t("folders") }
                        }
                        Item { Layout.fillWidth: true }
                    }
                    Item {
                        visible: win.height >= 700
                        Layout.fillWidth: true; Layout.preferredHeight: visible ? 170 : 0
                        Canvas {
                            id: donut; anchors.centerIn: parent; width: Math.min(parent.width, parent.height); height: width
                            property string activeExtension: win.s.extension
                            property color ring: win.pal.inset
                            property color other: win.pal.muted
                            onActiveExtensionChanged: requestPaint()
                            onRingChanged: requestPaint()
                            onOtherChanged: requestPaint()
                            onWidthChanged: requestPaint()
                            onPaint: {
                                let ctx = getContext("2d"); ctx.reset()
                                let cx = width / 2, cy = height / 2, r = width * 0.39
                                ctx.lineWidth = Math.max(12, width * 0.1); ctx.strokeStyle = ring
                                ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke()
                                let start = -Math.PI / 2
                                for (let slice of win.slices()) {
                                    let end = start + slice.fraction * Math.PI * 2
                                    ctx.strokeStyle = slice.color
                                    ctx.globalAlpha = activeExtension && activeExtension !== slice.label ? 0.25 : 1
                                    ctx.beginPath(); ctx.arc(cx, cy, r, start + 0.015, Math.max(start + 0.015, end - 0.015)); ctx.stroke()
                                    start = end
                                }
                            }
                            Connections { target: backend; function onExtensionsChanged() { donut.requestPaint() } }
                            MouseArea {
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: distance(mouseX, mouseY) ? Qt.PointingHandCursor : Qt.ArrowCursor
                                function distance(x, y) {
                                    let d = Math.hypot(x - width / 2, y - height / 2)
                                    return d >= width * 0.3 && d <= width * 0.48
                                }
                                onClicked: function(mouse) {
                                    if (!distance(mouse.x, mouse.y)) return
                                    let angle = (Math.atan2(mouse.y - height / 2, mouse.x - width / 2) + Math.PI / 2 + Math.PI * 2) % (Math.PI * 2)
                                    let total = 0
                                    for (let slice of win.slices()) {
                                        total += slice.fraction * Math.PI * 2
                                        if (angle <= total) { if (slice.label) backend.setExtension(slice.label); return }
                                    }
                                }
                            }
                        }
                        ColumnLayout {
                            anchors.centerIn: parent; spacing: 0
                            Label { Layout.alignment: Qt.AlignHCenter; text: win.num(win.s.total); font.pixelSize: Math.round(22 * win.fluid); color: win.pal.ink; font.weight: Font.DemiBold }
                            Caption { Layout.alignment: Qt.AlignHCenter; text: win.t("total_items") }
                        }
                    }
                    Caption { text: win.t("chart_title"); wrapMode: Text.WordWrap; Layout.fillWidth: true }
                    ListView {
                        id: legend; objectName: "legend"
                        Layout.fillWidth: true; Layout.fillHeight: true; clip: true
                        model: win.exts; spacing: 2
                        boundsBehavior: Flickable.StopAtBounds
                        ScrollBar.vertical: SoftScrollBar {}
                        delegate: ItemDelegate {
                            id: entry
                            required property var modelData
                            required property int index
                            width: legend.width; height: 34; hoverEnabled: true
                            onClicked: backend.setExtension(modelData.label)
                            background: Rectangle {
                                radius: 10
                                color: win.s.extension === entry.modelData.label ? win.pal.selection : entry.hovered ? win.pal.inset : "transparent"
                            }
                            contentItem: RowLayout {
                                spacing: 10
                                Rectangle {
                                    width: 8; height: 8; radius: 4
                                    color: entry.index < win.chartColors.length ? win.chartColors[entry.index] : win.pal.muted
                                }
                                Label {
                                    text: entry.modelData.label === "—" ? win.t("chart_no_ext") : entry.modelData.label
                                    color: win.pal.ink; Layout.fillWidth: true; elide: Text.ElideRight
                                }
                                Caption { text: win.num(entry.modelData.count) + "  ·  " + Math.max(entry.modelData.fraction > 0 ? 1 : 0, Math.round(entry.modelData.fraction * 100)) + "%" }
                            }
                        }
                    }
                    Caption { text: win.t("chart_hint"); Layout.fillWidth: true; wrapMode: Text.WordWrap; visible: win.exts.length > 0 }
                }
            }
        }

        // ── Barra di stato / Status bar ──
        RowLayout {
            Layout.fillWidth: true; spacing: 8
            Rectangle { width: 6; height: 6; radius: 3; color: win.s.error ? win.pal.danger : win.pal.accent }
            Caption {
                id: statusText
                Layout.fillWidth: true; elide: Text.ElideMiddle
                text: win.s.status || win.t("ready")
                color: win.s.error ? win.pal.danger : win.pal.muted
                HoverHandler { onHoveredChanged: win.hint(statusText, hovered && statusText.truncated ? statusText.text : "") }
            }
            // Elementi non letti nell'ultima scansione / Items not read in the latest scan
            SoftButton {
                objectName: "errorsButton"
                flat: true; implicitHeight: 26; glyph: "\uE7BA"
                visible: win.s.errors > 0 && !win.s.busy
                text: win.fmt("scan_errors_button", { count: win.num(win.s.errors) })
                onClicked: errorsDialog.open()
            }
            Caption { text: win.s.busy && win.s.progress >= 0 ? Math.round(win.s.progress * 100) + "%" : "© 2026 Mapper by Mattia De Lillo" }
        }
    }

    // ── Trascina una cartella / Drop a folder ──
    DropArea {
        id: drop
        anchors.fill: parent
        enabled: !win.s.busy
        onEntered: function(drag) { drag.accepted = drag.hasUrls }
        onDropped: function(drop) { if (drop.hasUrls) backend.openFolder(drop.urls[0].toString()) }
        Rectangle {
            anchors.fill: parent; anchors.margins: 12; radius: 26
            visible: drop.containsDrag
            color: Qt.rgba(win.pal.bg.r, win.pal.bg.g, win.pal.bg.b, 0.88)
            border.width: 2; border.color: win.pal.accent
            ColumnLayout {
                anchors.centerIn: parent; spacing: 12
                Icon { Layout.alignment: Qt.AlignHCenter; glyph: "\uE898"; font.pixelSize: 40; color: win.pal.accent }
                Heading { Layout.alignment: Qt.AlignHCenter; text: win.t("drop_overlay") }
            }
        }
    }

    // ── Menu / Menus ──
    SoftMenu {
        id: recentMenu
        Instantiator {
            model: backend.recent
            delegate: SoftMenuItem {
                required property string modelData
                text: modelData; glyph: "\uE8B7"
                onTriggered: backend.openFolder(modelData)
            }
            onObjectAdded: function(index, object) { recentMenu.insertItem(index, object) }
            onObjectRemoved: function(index, object) { recentMenu.removeItem(object) }
        }
        SoftSeparator {}
        SoftMenuItem { text: win.t("clear_recent"); glyph: "\uE74D"; onTriggered: backend.clearRecent() }
    }
    SoftMenu {
        id: createMenu
        SoftMenuItem { text: win.t("ctx_new_file"); glyph: "\uE8A5"; onTriggered: win.nameDialog("new_file", win.targetPath, "") }
        SoftMenuItem { text: win.t("ctx_new_folder"); glyph: "\uE8F4"; onTriggered: win.nameDialog("new_folder", win.targetPath, "") }
        SoftSeparator {}
        SoftMenuItem {
            text: win.t("ctx_paste"); glyph: "\uE77F"; enabled: win.s.clipboard !== ""
            onTriggered: backend.fileAction("paste", win.targetPath, "")
        }
    }
    SoftMenu {
        id: contextMenu; objectName: "contextMenu"
        SoftMenuItem { text: win.t("open_file"); glyph: "\uE8A7"; hint: "Enter"; onTriggered: backend.openPath(win.targetPath) }
        SoftMenuItem { text: win.t("show_in_folder"); glyph: "\uE8DA"; onTriggered: backend.showInFolder(win.targetPath) }
        SoftMenuItem { text: win.t("show_in_tree"); glyph: "\uE7AC"; visible: win.searching; onTriggered: backend.reveal(win.targetPath) }
        SoftMenuItem { text: win.t("copy_path"); glyph: "\uE71B"; onTriggered: backend.copyPath(win.targetPath) }
        SoftSeparator {}
        SoftMenuItem { text: win.t("ctx_cut"); glyph: "\uE8C6"; hint: "Ctrl+X"; enabled: !win.s.busy; onTriggered: backend.clipboard(win.targetPath, "cut") }
        SoftMenuItem { text: win.t("ctx_copy"); glyph: "\uE8C8"; hint: "Ctrl+C"; enabled: !win.s.busy; onTriggered: backend.clipboard(win.targetPath, "copy") }
        SoftMenuItem {
            text: win.t("ctx_paste"); glyph: "\uE77F"; hint: "Ctrl+V"; enabled: !win.s.busy && win.s.clipboard !== ""
            onTriggered: backend.fileAction("paste", win.targetPath, "")
        }
        SoftMenuItem { text: win.t("ctx_clone"); glyph: "\uE8C8"; enabled: !win.s.busy; onTriggered: backend.fileAction("clone", win.targetPath, "") }
        SoftSeparator {}
        SoftMenuItem { text: win.t("ctx_new_file"); glyph: "\uE8A5"; enabled: !win.s.busy; onTriggered: win.nameDialog("new_file", win.targetPath, "") }
        SoftMenuItem { text: win.t("ctx_new_folder"); glyph: "\uE8F4"; enabled: !win.s.busy; onTriggered: win.nameDialog("new_folder", win.targetPath, "") }
        SoftMenuItem {
            text: win.t("ctx_rename"); glyph: "\uE8AC"; hint: "F2"; enabled: !win.s.busy
            onTriggered: win.nameDialog("rename", win.targetPath, win.baseName(win.targetPath))
        }
        SoftSeparator {}
        SoftMenuItem {
            text: win.t("ctx_delete"); glyph: "\uE74D"; hint: "Del"; destructive: true; enabled: !win.s.busy
            onTriggered: win.removeDialog(win.targetPath)
        }
    }

    // ── Dialoghi / Dialogs ──
    SoftDialog {
        id: exportDialog; objectName: "exportDialog"
        title: win.t("export_map")
        width: Math.min(win.width - 80, 860); height: Math.min(win.height - 80, 660)
        acceptText: win.t("save_as"); acceptGlyph: "\uE74E"
        rejectText: win.t("close")
        secondaryText: win.t("copy_map"); secondaryGlyph: "\uE8C8"
        property int lines: 0
        onAboutToShow: { previewText.text = backend.preview(); lines = backend.lineCount() }
        onAccepted: win.saveMap()
        onSecondaryClicked: backend.copyMap()
        contentItem: ColumnLayout {
            spacing: 10
            Caption {
                Layout.fillWidth: true; wrapMode: Text.WordWrap
                text: exportDialog.lines > win.s.previewLimit
                      ? win.fmt("preview_truncated", { shown: win.num(win.s.previewLimit), total: win.num(exportDialog.lines) })
                      : win.fmt("preview_lines", { total: win.num(exportDialog.lines) })
            }
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                radius: 14; color: win.pal.inset; border.width: 1; border.color: win.pal.line
                ScrollView {
                    anchors.fill: parent; anchors.margins: 4; clip: true
                    ScrollBar.vertical: SoftScrollBar {}
                    ScrollBar.horizontal: SoftScrollBar {}
                    TextArea {
                        id: previewText; readOnly: true; selectByMouse: true; wrapMode: Text.NoWrap
                        font.family: "Consolas"; font.pixelSize: 13; color: win.pal.ink
                        selectionColor: win.pal.accent; selectedTextColor: win.pal.onAccent
                        background: null
                    }
                }
            }
        }
    }
    SoftDialog {
        id: editDialog; objectName: "editDialog"
        title: win.action === "rename" ? win.t("rename_title") : win.action === "new_file" ? win.t("new_file_title") : win.t("new_folder_title")
        canAccept: backend.isValidName(itemName.text)
        onOpened: {
            itemName.forceActiveFocus()
            let dot = itemName.text.lastIndexOf(".")
            if (win.action === "rename" && dot > 0) itemName.select(0, dot); else itemName.selectAll()
        }
        onAccepted: backend.fileAction(win.action, win.targetPath, itemName.text)
        contentItem: ColumnLayout {
            spacing: 8
            SoftField {
                id: itemName; Layout.fillWidth: true
                placeholderText: win.t("item_name")
                onAccepted: if (editDialog.canAccept) editDialog.accept()
            }
            Caption {
                Layout.fillWidth: true; wrapMode: Text.WordWrap
                text: win.t("error_invalid_name"); color: win.pal.danger
                opacity: itemName.text !== "" && !editDialog.canAccept ? 1 : 0
            }
        }
    }
    SoftDialog {
        id: deleteDialog; objectName: "deleteDialog"
        title: win.t("confirm_delete_title")
        acceptText: win.t("ctx_delete"); acceptGlyph: "\uE74D"; destructive: true
        onAccepted: backend.fileAction("delete", win.targetPath, "")
        contentItem: Label {
            text: win.fmt("confirm_delete", { name: win.baseName(win.targetPath) })
            wrapMode: Text.WordWrap; color: win.pal.ink
        }
    }
    SoftDialog {
        id: errorsDialog; objectName: "errorsDialog"
        title: win.t("scan_errors_title")
        width: Math.min(win.width - 80, 760); height: Math.min(win.height - 80, 560)
        acceptText: win.t("close"); rejectText: ""
        property var items: []
        readonly property var reasons: ({
            access_denied: win.t("reason_access_denied"), not_found: win.t("reason_not_found"),
            path_too_long: win.t("reason_path_too_long"), depth_limit: win.t("reason_depth_limit"),
            error: win.t("reason_error")
        })
        onAboutToShow: items = backend.scanErrors()
        contentItem: ColumnLayout {
            spacing: 10
            Caption {
                Layout.fillWidth: true; wrapMode: Text.WordWrap
                text: win.t("scan_errors_intro") + (win.s.errors > errorsDialog.items.length
                      ? " " + win.fmt("errors_more", { shown: win.num(errorsDialog.items.length), total: win.num(win.s.errors) }) : "")
            }
            Rectangle {
                Layout.fillWidth: true; Layout.fillHeight: true
                radius: 14; color: win.pal.inset; border.width: 1; border.color: win.pal.line
                ListView {
                    objectName: "errorsList"
                    anchors.fill: parent; anchors.margins: 6; clip: true
                    model: errorsDialog.items
                    ScrollBar.vertical: SoftScrollBar {}
                    delegate: ColumnLayout {
                        required property var modelData
                        width: ListView.view.width; spacing: 0
                        Label {
                            Layout.fillWidth: true; text: modelData.path; elide: Text.ElideMiddle
                            color: win.pal.ink; leftPadding: 8; topPadding: 6
                        }
                        Caption { text: errorsDialog.reasons[modelData.reason] || modelData.reason; leftPadding: 8; bottomPadding: 6 }
                    }
                }
            }
        }
    }
    SoftDialog {
        id: settings; objectName: "settingsDialog"
        title: win.t("settings")
        width: Math.min(win.width - 64, 480)
        property var themes: ["light", "dark", "blue", "red", "system"]
        property var languages: ["it", "en", "de", "fr", "es"]
        property var languageNames: ({ it: "Italiano", en: "English", de: "Deutsch", fr: "Français", es: "Español" })
        property var original: ({})
        property bool committed: false
        function current() { return [themes[themeChoice.currentIndex], languages[langChoice.currentIndex], reduce.checked] }
        // Anteprima dal vivo; Annulla/Esc ripristina / Live preview; Cancel/Esc reverts
        function preview() { let v = current(); backend.previewPreferences(v[0], v[1], v[2]) }
        onAboutToShow: {
            original = { theme: win.s.theme, language: win.s.language, reduced: win.s.reducedMotion }
            committed = false
            themeChoice.currentIndex = themes.indexOf(win.s.theme)
            langChoice.currentIndex = languages.indexOf(win.s.language)
            reduce.checked = win.s.reducedMotion
        }
        onAccepted: { committed = true; let v = current(); backend.preferences(v[0], v[1], v[2]) }
        onClosed: if (!committed) backend.previewPreferences(original.theme, original.language, original.reduced)
        contentItem: ColumnLayout {
            spacing: 10
            Caption { text: win.t("theme") }
            SoftCombo {
                id: themeChoice; Layout.fillWidth: true
                model: settings.themes
                labelFor: function(value) { return win.t("theme_" + value) }
                onActivated: settings.preview()
            }
            Caption { text: win.t("language"); Layout.topMargin: 4 }
            SoftCombo {
                id: langChoice; Layout.fillWidth: true
                model: settings.languages
                labelFor: function(value) { return settings.languageNames[value] || value }
                onActivated: settings.preview()
            }
            SoftSwitch { id: reduce; text: win.t("reduce_motion"); Layout.topMargin: 4; onToggled: settings.preview() }
            Rectangle { Layout.fillWidth: true; Layout.topMargin: 8; height: 1; color: win.pal.line }
            Caption { text: win.t("about") }
            Label {
                Layout.fillWidth: true; wrapMode: Text.WordWrap; color: win.pal.ink
                text: "Mapper " + win.s.version + "\n" + win.t("about_author") + " Mattia De Lillo\n" + win.t("about_copyright")
            }
            RowLayout {
                spacing: 8
                SoftButton { glyph: "\uE897"; text: win.t("guide"); onClicked: guide.open() }
                SoftButton { glyph: "\uE71B"; text: win.t("about_repo"); onClicked: Qt.openUrlExternally("https://github.com/SoulFlaZ3R/mapper") }
            }
        }
    }
    SoftDialog {
        id: guide; objectName: "guideDialog"
        title: win.t("guide_title")
        width: Math.min(win.width - 80, 580)
        rejectText: ""
        readonly property var shortcuts: [["Ctrl+O", "browse"], ["Ctrl+L", "path_placeholder_short"], ["F5", "refresh"],
            ["Ctrl+F", "quick_search_short"], ["Ctrl+E", "export_map"], ["Ctrl+S", "save_as"], ["F2", "ctx_rename"],
            ["Ctrl+C / X / V", "clipboard_keys"], ["Del", "ctx_delete"], ["Esc", "cancel"]]
        contentItem: ColumnLayout {
            spacing: 12
            Label { Layout.fillWidth: true; text: win.t("guide_content"); wrapMode: Text.WordWrap; color: win.pal.ink; lineHeight: 1.25 }
            Rectangle { Layout.fillWidth: true; height: 1; color: win.pal.line }
            GridLayout {
                columns: 2; columnSpacing: 18; rowSpacing: 4
                Repeater {
                    model: guide.shortcuts
                    delegate: Label {
                        required property var modelData
                        required property int index
                        Layout.column: 0
                        Layout.row: index
                        text: modelData[0]; color: win.pal.accent; font.weight: Font.DemiBold
                    }
                }
                Repeater {
                    model: guide.shortcuts
                    delegate: Label {
                        required property var modelData
                        required property int index
                        Layout.column: 1
                        Layout.row: index
                        text: win.t(modelData[1]); color: win.pal.ink
                    }
                }
            }
        }
    }

    onClosing: function(close) {
        if (win.s.busy && !win.s.cancellable) close.accepted = false
        else backend.shutdown()
    }
}
