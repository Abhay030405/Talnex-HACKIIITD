//go:build !windows

package drivers

import "os/exec"

// hideWindow does nothing off Windows: there is no console window to hide.
func hideWindow(*exec.Cmd) {}
