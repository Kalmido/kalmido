//go:build !darwin && !windows

// 2.1175.0 (#2770): Linux and other systems - no symbol (decision 14.11.2026), the service runs as before.
package main

func runWithTray(svc func(ready func(trayHooks)) int) int { return svc(nil) }
