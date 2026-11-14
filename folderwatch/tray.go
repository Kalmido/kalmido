// 2.1175.0 (#2770): the symbol in the menu bar (Mac) / the notification area of the taskbar (Windows). This file holds
// what every platform shares: which symbol fits the state of the inboxes (a pure function), the tooltip text and the
// drawing of the symbol in code (no image files). tray_darwin.go / tray_windows.go show it, tray_other.go does nothing.
// The menu has only "Open status" (the local page) and "Quit"; if the symbol cannot be shown, the watcher runs on
// without it.
package main

import (
	"bytes"
	"encoding/binary"
	"image"
	"image/color"
	"image/png"
	"time"
)

// trayIcon is the look of the symbol.
type trayIcon int

const (
	iconOK     trayIcon = iota // every inbox is ready
	iconPaused                 // waiting by itself (network, Kalmido refuses for now) or no inbox set up yet
	iconError                  // needs you: key invalid / revoked (paused) or the folder is missing
)

// trayEvery: how often the symbol looks at the state (the page itself refreshes every 10 s).
const trayEvery = 3 * time.Second

// trayHooks is what the platform part needs from the running service.
type trayHooks struct {
	lang   string
	status func() trayIcon // current symbol
	open   func()          // "Open status": the local page in the browser
	quit   func()          // "Quit": stops the service like the button on the page
	logf   func(format string, args ...any)
}

// trayState picks the symbol for the states of all inboxes: an error outranks waiting, waiting outranks ready.
// The grouping follows the colours of the status page (s-paused / s-nodir red, s-offline / s-blocked amber).
func trayState(states []State) trayIcon {
	if len(states) == 0 {
		return iconPaused
	}
	out := iconOK
	for _, s := range states {
		switch s {
		case StReady:
		case StPaused, StNoDir:
			return iconError
		default: // StOffline, StBlocked and anything new: waiting
			out = iconPaused
		}
	}
	return out
}

// trayTip is the tooltip / the first (disabled) menu line: program name and state.
func trayTip(lang string, ic trayIcon) string {
	k := "tray_ok"
	switch ic {
	case iconPaused:
		k = "tray_paused"
	case iconError:
		k = "tray_error"
	}
	return T(lang, "app") + " - " + T(lang, k)
}

// iconCovers: where the symbol is drawn, in unit coordinates (0..1, y down). shape = the folder, mark = the cut-out
// sign on it (arrow up = ok, two bars = paused, exclamation mark = error).
func iconCovers(ic trayIcon, x, y float64) (shape, mark bool) {
	in := func(x0, y0, x1, y1 float64) bool { return x >= x0 && x < x1 && y >= y0 && y < y1 }
	shape = in(0.06, 0.30, 0.94, 0.86) || in(0.06, 0.18, 0.44, 0.32)
	switch ic {
	case iconOK:
		// triangle with its tip at (0.5, 0.38) and its base at y = 0.56, then the stem
		if y >= 0.38 && y < 0.56 {
			half := (y - 0.38) / 0.18 * 0.18
			mark = x >= 0.5-half && x < 0.5+half
		}
		mark = mark || in(0.44, 0.55, 0.56, 0.78)
	case iconPaused:
		mark = in(0.35, 0.42, 0.46, 0.78) || in(0.54, 0.42, 0.65, 0.78)
	case iconError:
		mark = in(0.445, 0.38, 0.555, 0.64) || in(0.445, 0.69, 0.555, 0.79)
	}
	return shape, mark && shape
}

// Colours of the Windows symbol (the Mac one is a template: macOS colours it for light / dark menu bars).
var iconColors = map[trayIcon]color.NRGBA{
	iconOK:     {0x18, 0x73, 0x81, 0xff}, // the Kalmido accent
	iconPaused: {0x8a, 0x62, 0x00, 0xff}, // amber like "waiting" on the page
	iconError:  {0xb3, 0x37, 0x2f, 0xff}, // red like an error on the page
}

// iconImage draws the symbol with size x size pixels (4x4 samples per pixel for smooth edges). template = black with
// the sign cut out (alpha only), else the folder in the state colour with a white sign.
func iconImage(ic trayIcon, size int, template bool) *image.NRGBA {
	img := image.NewNRGBA(image.Rect(0, 0, size, size))
	const n = 4
	col := iconColors[ic]
	for py := 0; py < size; py++ {
		for px := 0; px < size; px++ {
			shape, mark := 0, 0
			for sy := 0; sy < n; sy++ {
				for sx := 0; sx < n; sx++ {
					x := (float64(px) + (float64(sx)+0.5)/n) / float64(size)
					y := (float64(py) + (float64(sy)+0.5)/n) / float64(size)
					s, m := iconCovers(ic, x, y)
					if s {
						shape++
					}
					if m {
						mark++
					}
				}
			}
			if shape == 0 {
				continue
			}
			if template {
				img.SetNRGBA(px, py, color.NRGBA{0, 0, 0, uint8((shape - mark) * 255 / (n * n))})
				continue
			}
			// mix the folder colour with white by the share of the sign, alpha by the share of the folder
			mix := func(c uint8) uint8 { return uint8((int(c)*(shape-mark) + 255*mark) / shape) }
			img.SetNRGBA(px, py, color.NRGBA{mix(col.R), mix(col.G), mix(col.B), uint8(shape * 255 / (n * n))})
		}
	}
	return img
}

// iconPNG: the symbol as PNG bytes (the Mac loads it with NSImage).
func iconPNG(ic trayIcon, size int, template bool) []byte {
	var b bytes.Buffer
	_ = png.Encode(&b, iconImage(ic, size, template))
	return b.Bytes()
}

// iconDIB: the symbol as one icon image of an .ico file (BITMAPINFOHEADER with double height, 32-bit BGRA rows from the
// bottom, then the AND mask) - what CreateIconFromResourceEx on Windows takes.
func iconDIB(ic trayIcon, size int) []byte {
	img := iconImage(ic, size, false)
	maskRow := ((size + 31) / 32) * 4
	var b bytes.Buffer
	hdr := []any{uint32(40), int32(size), int32(2 * size), uint16(1), uint16(32), uint32(0),
		uint32(size*size*4 + maskRow*size), int32(0), int32(0), uint32(0), uint32(0)}
	for _, v := range hdr {
		_ = binary.Write(&b, binary.LittleEndian, v)
	}
	for y := size - 1; y >= 0; y-- {
		for x := 0; x < size; x++ {
			c := img.NRGBAAt(x, y)
			b.Write([]byte{c.B, c.G, c.R, c.A})
		}
	}
	b.Write(make([]byte, maskRow*size)) // all 0: the alpha channel decides
	return b.Bytes()
}
