//go:build windows

package drivers

import (
	"os/exec"
	"syscall"
)

// createNoWindow is the Windows flag that stops a console window from opening for a program we start.
const createNoWindow = 0x08000000

// hideWindow keeps `docker` from flashing a console window every time sandboxd runs it. A test run makes hundreds of
// docker calls, and without this each one opens and closes a window on the sandbox host.
func hideWindow(cmd *exec.Cmd) {
	cmd.SysProcAttr = &syscall.SysProcAttr{HideWindow: true, CreationFlags: createNoWindow}
}
