// 2.1175.0 (#2770): the symbol in the notification area of the taskbar on Windows - only the standard library (syscall
// into user32 / shell32: a hidden window, Shell_NotifyIconW, a popup menu). If it cannot be set up, the watcher runs on
// without it.
package main

import (
	"errors"
	"runtime"
	"syscall"
	"unsafe"
)

var (
	user32                   = syscall.NewLazyDLL("user32.dll")
	shell32                  = syscall.NewLazyDLL("shell32.dll")
	kernel32                 = syscall.NewLazyDLL("kernel32.dll")
	pRegisterClassExW        = user32.NewProc("RegisterClassExW")
	pCreateWindowExW         = user32.NewProc("CreateWindowExW")
	pDefWindowProcW          = user32.NewProc("DefWindowProcW")
	pDestroyWindow           = user32.NewProc("DestroyWindow")
	pGetMessageW             = user32.NewProc("GetMessageW")
	pTranslateMessage        = user32.NewProc("TranslateMessage")
	pDispatchMessageW        = user32.NewProc("DispatchMessageW")
	pPostMessageW            = user32.NewProc("PostMessageW")
	pPostQuitMessage         = user32.NewProc("PostQuitMessage")
	pSetTimer                = user32.NewProc("SetTimer")
	pRegisterWindowMessageW  = user32.NewProc("RegisterWindowMessageW")
	pCreatePopupMenu         = user32.NewProc("CreatePopupMenu")
	pDestroyMenu             = user32.NewProc("DestroyMenu")
	pAppendMenuW             = user32.NewProc("AppendMenuW")
	pTrackPopupMenu          = user32.NewProc("TrackPopupMenu")
	pGetCursorPos            = user32.NewProc("GetCursorPos")
	pSetForegroundWindow     = user32.NewProc("SetForegroundWindow")
	pGetSystemMetrics        = user32.NewProc("GetSystemMetrics")
	pCreateIconFromResourceE = user32.NewProc("CreateIconFromResourceEx")
	pShellNotifyIconW        = shell32.NewProc("Shell_NotifyIconW")
	pGetModuleHandleW        = kernel32.NewProc("GetModuleHandleW")
)

const (
	wmNull        = 0x0000
	wmDestroy     = 0x0002
	wmClose       = 0x0010
	wmTimer       = 0x0113
	wmLButtonUp   = 0x0202
	wmRButtonUp   = 0x0205
	wmApp         = 0x8000
	wmTrayNotify  = wmApp + 1
	nimAdd        = 0
	nimModify     = 1
	nimDelete     = 2
	nifMessage    = 0x1
	nifIcon       = 0x2
	nifTip        = 0x4
	mfString      = 0x0
	mfGrayed      = 0x1
	mfSeparator   = 0x800
	tpmRightBtn   = 0x2
	tpmReturnCmd  = 0x100
	smCxSmIcon    = 49
	smCySmIcon    = 50
	cmdOpen       = 1
	cmdQuit       = 2
	trayTimerID   = 1
	trayIconID    = 1
	lrDefaultClr  = 0
	iconResVer300 = 0x00030000
)

type wndClassEx struct {
	CbSize        uint32
	Style         uint32
	LpfnWndProc   uintptr
	CbClsExtra    int32
	CbWndExtra    int32
	HInstance     uintptr
	HIcon         uintptr
	HCursor       uintptr
	HbrBackground uintptr
	LpszMenuName  *uint16
	LpszClassName *uint16
	HIconSm       uintptr
}

type winMsg struct {
	HWnd    uintptr
	Message uint32
	WParam  uintptr
	LParam  uintptr
	Time    uint32
	Pt      struct{ X, Y int32 }
	Private uint32
}

// notifyIconData is NOTIFYICONDATAW (the Go field alignment matches the C layout on 64 and 32 bit).
type notifyIconData struct {
	CbSize           uint32
	HWnd             uintptr
	UID              uint32
	UFlags           uint32
	UCallbackMessage uint32
	HIcon            uintptr
	SzTip            [128]uint16
	DwState          uint32
	DwStateMask      uint32
	SzInfo           [256]uint16
	UVersion         uint32
	SzInfoTitle      [64]uint16
	DwInfoFlags      uint32
	GuidItem         [16]byte
	HBalloonIcon     uintptr
}

type winTray struct {
	h          trayHooks
	hwnd       uintptr
	icons      [3]uintptr
	cur        trayIcon
	taskbarMsg uintptr
}

func runWithTray(svc func(ready func(trayHooks)) int) int {
	done := make(chan int, 1)
	hooks := make(chan trayHooks, 1)
	go func() { done <- svc(func(h trayHooks) { hooks <- h }) }()
	select {
	case code := <-done:
		return code
	case h := <-hooks:
		runtime.LockOSThread() // the window and its messages belong to this thread
		t, err := trayStart(h)
		if err != nil {
			h.logf("taskbar symbol: %v - running without it", err)
			return <-done
		}
		h.logf("taskbar symbol shown")
		code := make(chan int, 1)
		go func() {
			c := <-done // "Quit" (symbol, page) ended the service: take the symbol away, then end
			code <- c
			pPostMessageW.Call(t.hwnd, wmClose, 0, 0)
		}()
		var m winMsg
		for {
			r, _, _ := pGetMessageW.Call(uintptr(unsafe.Pointer(&m)), 0, 0, 0)
			if int32(r) <= 0 { // WM_QUIT or an error
				break
			}
			pTranslateMessage.Call(uintptr(unsafe.Pointer(&m)))
			pDispatchMessageW.Call(uintptr(unsafe.Pointer(&m)))
		}
		return <-code
	}
}

var theTray *winTray // the window procedure is one callback for the whole process

func trayStart(h trayHooks) (*winTray, error) {
	if err := pShellNotifyIconW.Find(); err != nil {
		return nil, err
	}
	t := &winTray{h: h, cur: -1}
	cx, _, _ := pGetSystemMetrics.Call(smCxSmIcon)
	cy, _, _ := pGetSystemMetrics.Call(smCySmIcon)
	if cx == 0 || cy == 0 {
		cx, cy = 16, 16
	}
	for _, ic := range []trayIcon{iconOK, iconPaused, iconError} {
		dib := iconDIB(ic, int(cx))
		hi, _, err := pCreateIconFromResourceE.Call(uintptr(unsafe.Pointer(&dib[0])), uintptr(len(dib)), 1, iconResVer300,
			cx, cy, lrDefaultClr)
		runtime.KeepAlive(dib)
		if hi == 0 {
			return nil, err
		}
		t.icons[ic] = hi
	}
	inst, _, _ := pGetModuleHandleW.Call(0)
	cls, _ := syscall.UTF16PtrFromString("KalmidoFolderWatcherTray")
	wc := wndClassEx{LpfnWndProc: syscall.NewCallback(trayWndProc), HInstance: inst, LpszClassName: cls}
	wc.CbSize = uint32(unsafe.Sizeof(wc))
	if r, _, err := pRegisterClassExW.Call(uintptr(unsafe.Pointer(&wc))); r == 0 {
		return nil, err
	}
	name, _ := syscall.UTF16PtrFromString(T(h.lang, "app"))
	theTray = t
	hwnd, _, err := pCreateWindowExW.Call(0, uintptr(unsafe.Pointer(cls)), uintptr(unsafe.Pointer(name)), 0, 0, 0, 0, 0, 0, 0, inst, 0)
	if hwnd == 0 {
		theTray = nil
		return nil, err
	}
	t.hwnd = hwnd
	tb, _ := syscall.UTF16PtrFromString("TaskbarCreated")
	t.taskbarMsg, _, _ = pRegisterWindowMessageW.Call(uintptr(unsafe.Pointer(tb)))
	if !t.notify(nimAdd) {
		pDestroyWindow.Call(hwnd)
		theTray = nil
		return nil, errors.New("Shell_NotifyIconW refused the symbol")
	}
	pSetTimer.Call(hwnd, trayTimerID, uintptr(trayEvery.Milliseconds()), 0)
	return t, nil
}

// notify adds / updates / removes the symbol with the current state.
func (t *winTray) notify(op uintptr) bool {
	t.cur = t.h.status()
	d := notifyIconData{HWnd: t.hwnd, UID: trayIconID, UFlags: nifMessage | nifIcon | nifTip, UCallbackMessage: wmTrayNotify,
		HIcon: t.icons[t.cur]}
	d.CbSize = uint32(unsafe.Sizeof(d))
	tip, _ := syscall.UTF16FromString(trayTip(t.h.lang, t.cur))
	if len(tip) > len(d.SzTip) {
		tip = append(tip[:len(d.SzTip)-1], 0)
	}
	copy(d.SzTip[:], tip)
	r, _, _ := pShellNotifyIconW.Call(op, uintptr(unsafe.Pointer(&d)))
	return r != 0
}

func (t *winTray) menu() {
	m, _, _ := pCreatePopupMenu.Call()
	if m == 0 {
		return
	}
	defer pDestroyMenu.Call(m)
	add := func(flags, id uintptr, text string) {
		p, _ := syscall.UTF16PtrFromString(text)
		pAppendMenuW.Call(m, flags, id, uintptr(unsafe.Pointer(p)))
	}
	add(mfString|mfGrayed, 0, trayTip(t.h.lang, t.cur))
	pAppendMenuW.Call(m, mfSeparator, 0, 0)
	add(mfString, cmdOpen, T(t.h.lang, "tray_open"))
	add(mfString, cmdQuit, T(t.h.lang, "btn_quit"))
	var pt struct{ X, Y int32 }
	pGetCursorPos.Call(uintptr(unsafe.Pointer(&pt)))
	pSetForegroundWindow.Call(t.hwnd) // else the menu does not close on a click outside
	cmd, _, _ := pTrackPopupMenu.Call(m, tpmRightBtn|tpmReturnCmd, uintptr(pt.X), uintptr(pt.Y), 0, t.hwnd, 0)
	pPostMessageW.Call(t.hwnd, wmNull, 0, 0)
	switch cmd {
	case cmdOpen:
		go t.h.open()
	case cmdQuit:
		go t.h.quit()
	}
}

func trayWndProc(hwnd, msg, wparam, lparam uintptr) uintptr {
	t := theTray
	if t != nil && t.hwnd == hwnd {
		switch {
		case msg == wmTrayNotify && (lparam&0xffff == wmLButtonUp || lparam&0xffff == wmRButtonUp):
			t.menu()
			return 0
		case msg == wmTimer && wparam == trayTimerID:
			if t.h.status() != t.cur {
				t.notify(nimModify)
			}
			return 0
		case t.taskbarMsg != 0 && msg == t.taskbarMsg: // Explorer restarted: add the symbol again
			t.notify(nimAdd)
			return 0
		case msg == wmClose:
			t.notify(nimDelete)
			pDestroyWindow.Call(hwnd)
			return 0
		case msg == wmDestroy:
			pPostQuitMessage.Call(0)
			return 0
		}
	}
	r, _, _ := pDefWindowProcW.Call(hwnd, msg, wparam, lparam)
	return r
}
