//go:build darwin

// 2.1175.0 (#2770): the menu bar symbol on the Mac without cgo - NSStatusItem through the Objective-C runtime with the
// vendored purego (folderwatch/vendor). AppKit wants the main thread: init locks it, the service runs in a goroutine.
// If the symbol cannot be set up (no window server, AppKit missing), the watcher runs on without it.
package main

import (
	"errors"
	"fmt"
	"os"
	"runtime"
	"structs"
	"unsafe"

	"github.com/ebitengine/purego"
	"github.com/ebitengine/purego/objc"
)

func init() { runtime.LockOSThread() } // main() runs on the main thread, AppKit lives there

type nsSize struct {
	_             structs.HostLayout
	Width, Height float64
}

const (
	nsActivationPolicyAccessory = 1  // no Dock icon, no app menu
	nsSquareStatusItemLength    = -2 // NSSquareStatusItemLength
)

func runWithTray(svc func(ready func(trayHooks)) int) int {
	done := make(chan int, 1)
	hooks := make(chan trayHooks, 1)
	go func() { done <- svc(func(h trayHooks) { hooks <- h }) }()
	select {
	case code := <-done: // another copy runs, no port, quit before the start ...
		return code
	case h := <-hooks:
		if err := trayStart(h); err != nil {
			h.logf("menu bar symbol: %v - running without it", err)
			return <-done
		}
		h.logf("menu bar symbol shown")
		go func() { os.Exit(<-done) }() // "Quit" (symbol, page, signal) ends the service, then the process
		objc.ID(objc.GetClass("NSApplication")).Send(objc.RegisterName("sharedApplication")).Send(objc.RegisterName("run"))
		return <-done // [NSApp run] only comes back if AppKit gives up
	}
}

func nsString(s string) objc.ID {
	return objc.ID(objc.GetClass("NSString")).Send(objc.RegisterName("stringWithUTF8String:"), s)
}

// nsImage: a template image (macOS colours it for the menu bar) from PNG bytes drawn at 2x, shown at 18x18 points.
func nsImage(png []byte) objc.ID {
	data := objc.ID(objc.GetClass("NSData")).Send(objc.RegisterName("dataWithBytes:length:"), unsafe.Pointer(&png[0]), uint64(len(png)))
	runtime.KeepAlive(png)
	img := objc.ID(objc.GetClass("NSImage")).Send(objc.RegisterName("alloc")).Send(objc.RegisterName("initWithData:"), data)
	if img == 0 {
		return 0
	}
	img.Send(objc.RegisterName("setSize:"), nsSize{Width: 18, Height: 18})
	img.Send(objc.RegisterName("setTemplate:"), true)
	return img
}

// trayStart builds the status item with its menu and a timer for the state; any panic of the runtime calls counts as
// "no symbol".
func trayStart(h trayHooks) (err error) {
	defer func() {
		if r := recover(); r != nil {
			err = fmt.Errorf("%v", r)
		}
	}()
	if _, err := purego.Dlopen("/System/Library/Frameworks/AppKit.framework/AppKit", purego.RTLD_GLOBAL|purego.RTLD_LAZY); err != nil {
		return err
	}
	sel := objc.RegisterName
	pool := objc.ID(objc.GetClass("NSAutoreleasePool")).Send(sel("alloc")).Send(sel("init"))
	defer pool.Send(sel("drain"))
	app := objc.ID(objc.GetClass("NSApplication")).Send(sel("sharedApplication"))
	if app == 0 {
		return errors.New("no NSApplication")
	}
	app.Send(sel("setActivationPolicy:"), nsActivationPolicyAccessory)

	var images [3]objc.ID
	for _, ic := range []trayIcon{iconOK, iconPaused, iconError} {
		if images[ic] = nsImage(iconPNG(ic, 36, true)); images[ic] == 0 {
			return errors.New("symbol image not loaded")
		}
	}
	bar := objc.ID(objc.GetClass("NSStatusBar")).Send(sel("systemStatusBar"))
	if bar == 0 {
		return errors.New("no status bar")
	}
	item := bar.Send(sel("statusItemWithLength:"), float64(nsSquareStatusItemLength))
	if item == 0 {
		return errors.New("no status item")
	}
	item.Send(sel("retain"))
	button := item.Send(sel("button"))
	if button == 0 {
		return errors.New("status item without a button")
	}

	menu := objc.ID(objc.GetClass("NSMenu")).Send(sel("alloc")).Send(sel("init"))
	menu.Send(sel("setAutoenablesItems:"), false)
	addItem := func(title string, action objc.SEL, target objc.ID) objc.ID {
		mi := objc.ID(objc.GetClass("NSMenuItem")).Send(sel("alloc")).Send(sel("initWithTitle:action:keyEquivalent:"),
			nsString(title), action, nsString(""))
		if target != 0 {
			mi.Send(sel("setTarget:"), target)
		} else {
			mi.Send(sel("setEnabled:"), false)
		}
		menu.Send(sel("addItem:"), mi)
		return mi
	}

	cur := trayIcon(-1)
	var stateItem objc.ID
	update := func() {
		ic := h.status()
		if ic == cur {
			return
		}
		cur = ic
		tip := trayTip(h.lang, ic)
		button.Send(sel("setImage:"), images[ic])
		button.Send(sel("setToolTip:"), nsString(tip))
		stateItem.Send(sel("setTitle:"), nsString(tip))
	}
	cls, err := objc.RegisterClass("KalmidoFolderWatcherTray", objc.GetClass("NSObject"), nil, nil, []objc.MethodDef{
		{Cmd: sel("openStatus:"), Fn: func(_ objc.ID, _ objc.SEL, _ objc.ID) { go h.open() }},
		{Cmd: sel("quitWatcher:"), Fn: func(_ objc.ID, _ objc.SEL, _ objc.ID) { go h.quit() }},
		{Cmd: sel("tick:"), Fn: func(_ objc.ID, _ objc.SEL, _ objc.ID) { update() }},
	})
	if err != nil {
		return err
	}
	target := objc.ID(cls).Send(sel("alloc")).Send(sel("init"))

	stateItem = addItem(T(h.lang, "app"), 0, 0)
	menu.Send(sel("addItem:"), objc.ID(objc.GetClass("NSMenuItem")).Send(sel("separatorItem")))
	addItem(T(h.lang, "tray_open"), sel("openStatus:"), target)
	addItem(T(h.lang, "btn_quit"), sel("quitWatcher:"), target)
	item.Send(sel("setMenu:"), menu)

	update()
	objc.ID(objc.GetClass("NSTimer")).Send(sel("scheduledTimerWithTimeInterval:target:selector:userInfo:repeats:"),
		trayEvery.Seconds(), target, sel("tick:"), objc.ID(0), true)
	return nil
}
