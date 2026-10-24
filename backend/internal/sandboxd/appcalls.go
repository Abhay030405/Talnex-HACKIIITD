package sandboxd

import (
	"bytes"
	"context"
	"fmt"
	"net/textproto"
	"sort"
	"strconv"
	"strings"
	"time"
)

// Everything here is built on Exec, so it works the same for every driver and needs no network path from the host
// into the VM: the request is sent from inside the VM, to the app on its own loopback address.

// ListeningPorts returns the TCP ports something is listening on inside the VM, lowest first.
func (m *Manager) ListeningPorts(ctx context.Context, id string) ([]int, error) {
	res, err := m.Exec(ctx, id, ExecSpec{
		Command: []string{"sh", "-c", "cat /proc/net/tcp /proc/net/tcp6 2>/dev/null"},
		Timeout: 15 * time.Second,
	})
	if err != nil {
		return nil, err
	}
	return ParseListeningPorts(res.Stdout), nil
}

// ParseListeningPorts reads the text of /proc/net/tcp and /proc/net/tcp6. A line whose state is 0A is listening.
func ParseListeningPorts(text string) []int {
	seen := map[int]bool{}
	for _, line := range strings.Split(text, "\n") {
		f := strings.Fields(line)
		if len(f) < 4 || f[3] != "0A" {
			continue
		}
		i := strings.LastIndex(f[1], ":")
		if i < 0 {
			continue
		}
		port, err := strconv.ParseInt(f[1][i+1:], 16, 32)
		if err != nil || port <= 0 || port > 65535 {
			continue
		}
		seen[int(port)] = true
	}
	out := make([]int, 0, len(seen))
	for p := range seen {
		out = append(out, p)
	}
	sort.Ints(out)
	return out
}

// HTTPRequest is one request to send to the app inside a VM.
type HTTPRequest struct {
	Method  string            `json:"method"`
	Port    int               `json:"port"`
	Path    string            `json:"path"` // starts with /, may carry a query string
	Headers map[string]string `json:"headers"`
	Body    []byte            `json:"body"`
	Timeout time.Duration     `json:"-"`
}

// HTTPResponse is what the app answered. Error is set (and Status is 0) when no answer came back at all, so the
// caller can tell "the app did not answer" from "the host failed".
type HTTPResponse struct {
	Status     int                 `json:"status"`
	Headers    map[string][]string `json:"headers"`
	Body       []byte              `json:"body"`
	DurationMS int64               `json:"duration_ms"`
	Truncated  bool                `json:"truncated"`
	Error      string              `json:"error,omitempty"`
}

var allowedMethods = map[string]bool{"GET": true, "POST": true, "PUT": true, "PATCH": true, "DELETE": true, "HEAD": true, "OPTIONS": true}

// Request sends one HTTP request from inside the VM to a port on it.
func (m *Manager) Request(ctx context.Context, id string, req HTTPRequest) (HTTPResponse, error) {
	if _, err := m.Get(id); err != nil {
		return HTTPResponse{}, err
	}
	req.Method = strings.ToUpper(strings.TrimSpace(req.Method))
	if req.Method == "" {
		req.Method = "GET"
	}
	if !allowedMethods[req.Method] {
		return HTTPResponse{}, bad("method %q is not allowed", req.Method)
	}
	if req.Port < 1 || req.Port > 65535 {
		return HTTPResponse{}, bad("port must be between 1 and 65535")
	}
	if !strings.HasPrefix(req.Path, "/") || strings.ContainsAny(req.Path, " \t\r\n") {
		return HTTPResponse{}, bad("path must start with / and contain no spaces or line breaks")
	}
	if req.Timeout <= 0 {
		req.Timeout = 30 * time.Second
	}
	if req.Timeout > m.lim.ExecTimeout {
		req.Timeout = m.lim.ExecTimeout
	}

	args := []string{"curl", "-s", "-S", "-i", "--http1.1", "--max-time", strconv.Itoa(int(req.Timeout.Seconds()) + 1), "-X", req.Method}
	names := make([]string, 0, len(req.Headers))
	for k := range req.Headers {
		names = append(names, k)
	}
	sort.Strings(names)
	for _, k := range names {
		v := req.Headers[k]
		if k == "" || strings.ContainsAny(k+v, "\r\n") || strings.Contains(k, ":") {
			return HTTPResponse{}, bad("header %q has characters that are not allowed", k)
		}
		args = append(args, "-H", k+": "+v)
	}
	if len(req.Body) > 0 {
		args = append(args, "--data-binary", "@-")
	}
	args = append(args, fmt.Sprintf("http://127.0.0.1:%d%s", req.Port, req.Path))

	res, err := m.run(ctx, id, ExecSpec{Command: args, Stdin: req.Body, Timeout: req.Timeout + 10*time.Second})
	if err != nil {
		return HTTPResponse{}, err
	}
	out := HTTPResponse{DurationMS: res.DurationMS, Truncated: res.Truncated}
	if res.ExitCode != 0 {
		out.Error = curlError(res, req.Port)
		return out, nil
	}
	status, headers, body, ok := parseCurlOutput([]byte(res.Stdout))
	if !ok {
		out.Error = "the app sent something that is not an HTTP answer"
		return out, nil
	}
	out.Status, out.Headers, out.Body = status, headers, body
	return out, nil
}

func curlError(res ExecResult, port int) string {
	switch res.ExitCode {
	case 7:
		return fmt.Sprintf("connection refused: nothing is listening on port %d", port)
	case 28:
		return "the app did not answer in time"
	case 52:
		return "the app closed the connection without answering"
	}
	msg := strings.TrimSpace(res.Stderr)
	if msg == "" {
		msg = fmt.Sprintf("curl exited with %d", res.ExitCode)
	}
	return msg
}

// parseCurlOutput splits the text of `curl -i` into the status, the headers and the body. Interim "100 Continue"
// answers are skipped.
func parseCurlOutput(raw []byte) (status int, headers map[string][]string, body []byte, ok bool) {
	for {
		sep := bytes.Index(raw, []byte("\r\n\r\n"))
		if sep < 0 {
			return 0, nil, nil, false
		}
		head, rest := string(raw[:sep]), raw[sep+4:]
		lines := strings.Split(head, "\r\n")
		parts := strings.SplitN(lines[0], " ", 3)
		if len(parts) < 2 || !strings.HasPrefix(parts[0], "HTTP/") {
			return 0, nil, nil, false
		}
		code, err := strconv.Atoi(parts[1])
		if err != nil {
			return 0, nil, nil, false
		}
		if code >= 100 && code < 200 {
			raw = rest
			continue
		}
		headers = map[string][]string{}
		for _, l := range lines[1:] {
			i := strings.Index(l, ":")
			if i <= 0 {
				continue
			}
			k := textproto.CanonicalMIMEHeaderKey(strings.TrimSpace(l[:i]))
			headers[k] = append(headers[k], strings.TrimSpace(l[i+1:]))
		}
		return code, headers, rest, true
	}
}
