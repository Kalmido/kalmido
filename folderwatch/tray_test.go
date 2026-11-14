// 2.1175.0 (#2770): the shared part of the menu bar / taskbar symbol - which symbol fits which state, the texts and the
// drawn images (the platform part itself can only be looked at on a Mac / Windows computer).
package main

import (
	"bytes"
	"encoding/binary"
	"image/png"
	"testing"
)

func TestTrayState(t *testing.T) {
	cases := []struct {
		in   []State
		want trayIcon
	}{
		{nil, iconPaused}, // nothing set up yet
		{[]State{StReady}, iconOK},
		{[]State{StReady, StReady}, iconOK},
		{[]State{StReady, StOffline}, iconPaused},
		{[]State{StBlocked}, iconPaused},
		{[]State{StReady, StPaused}, iconError}, // key revoked: needs you
		{[]State{StOffline, StNoDir}, iconError},
		{[]State{StNoDir, StOffline, StReady}, iconError}, // an error outranks waiting, whatever the order
		{[]State{"new-state"}, iconPaused},
	}
	for _, c := range cases {
		if got := trayState(c.in); got != c.want {
			t.Errorf("trayState(%v) = %d, want %d", c.in, got, c.want)
		}
	}
}

func TestTrayTexts(t *testing.T) {
	if got := trayTip("de", iconOK); got != "Kalmido Ordner-Wächter - Bereit" {
		t.Errorf("tip de ok: %q", got)
	}
	if got := trayTip("en", iconError); got != "Kalmido Folder watcher - Needs you - open the status" {
		t.Errorf("tip en error: %q", got)
	}
	for _, k := range []string{"tray_open", "tray_ok", "tray_paused", "tray_error", "btn_quit"} {
		if T("de", k) == k || T("en", k) == k || T("de", k) == T("en", k) && k != "tray_ok" {
			t.Errorf("text %s missing or not translated", k)
		}
	}
}

func TestTrayIcons(t *testing.T) {
	kinds := []trayIcon{iconOK, iconPaused, iconError}
	seen := map[string]bool{}
	for _, ic := range kinds {
		// Mac: a template PNG 36x36 (18 pt at 2x), black with alpha only, the sign cut out of the folder
		img, err := png.Decode(bytes.NewReader(iconPNG(ic, 36, true)))
		if err != nil {
			t.Fatalf("icon %d: %v", ic, err)
		}
		if b := img.Bounds(); b.Dx() != 36 || b.Dy() != 36 {
			t.Fatalf("icon %d size %v", ic, b)
		}
		var opaque, clear int
		for y := 0; y < 36; y++ {
			for x := 0; x < 36; x++ {
				r, g, b, a := img.At(x, y).RGBA()
				if r != 0 || g != 0 || b != 0 {
					t.Fatalf("icon %d: template pixel (%d,%d) is not black", ic, x, y)
				}
				switch a {
				case 0xffff:
					opaque++
				case 0:
					clear++
				}
			}
		}
		if opaque < 300 || clear < 200 {
			t.Errorf("icon %d: %d opaque, %d clear pixels", ic, opaque, clear)
		}
		if _, _, _, a := img.At(1, 1).RGBA(); a != 0 {
			t.Errorf("icon %d: the corner must stay transparent", ic)
		}
		key := string(iconPNG(ic, 36, true))
		if seen[key] {
			t.Errorf("icon %d looks like another state", ic)
		}
		seen[key] = true

		// Windows: one icon image (BITMAPINFOHEADER, height doubled, 32 bit, then the AND mask)
		for _, size := range []int{16, 20, 24, 32} {
			d := iconDIB(ic, size)
			mask := ((size + 31) / 32) * 4
			if len(d) != 40+size*size*4+mask*size {
				t.Fatalf("dib %d/%d: length %d", ic, size, len(d))
			}
			if binary.LittleEndian.Uint32(d[0:]) != 40 || int32(binary.LittleEndian.Uint32(d[8:])) != int32(2*size) ||
				binary.LittleEndian.Uint16(d[14:]) != 32 {
				t.Fatalf("dib %d/%d: header %x", ic, size, d[:16])
			}
		}
	}
	// the colours tell the states apart on Windows: the middle of the folder body carries the state colour
	for _, ic := range kinds {
		c := iconImage(ic, 32, false).NRGBAAt(4, 20)
		if c != iconColors[ic] {
			t.Errorf("icon %d: body colour %v, want %v", ic, c, iconColors[ic])
		}
	}
	// the sign is white on the coloured folder (error: the bar of the exclamation mark)
	if c := iconImage(iconError, 32, false).NRGBAAt(16, 16); c.R != 255 || c.G != 255 || c.B != 255 || c.A != 255 {
		t.Errorf("error sign not white: %v", c)
	}
}
