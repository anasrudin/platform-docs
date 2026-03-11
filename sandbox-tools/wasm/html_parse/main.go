//go:build wasip1

// html_parse extracts structured data from an HTML document.
// Compile: GOOS=js GOARCH=wasm go build -o html_parse.wasm .
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

// Input is the expected JSON input structure.
type Input struct {
	HTML string `json:"html"`
	URL  string `json:"url,omitempty"`
}

// Output is the JSON response.
type Output struct {
	Title   string   `json:"title"`
	Text    string   `json:"text"`
	Links   []string `json:"links"`
	Error   string   `json:"error,omitempty"`
}

func main() {
	if len(os.Args) < 2 {
		writeError("input JSON required as first argument")
		return
	}

	var inp Input
	if err := json.Unmarshal([]byte(os.Args[1]), &inp); err != nil {
		writeError(fmt.Sprintf("decode input: %v", err))
		return
	}
	if inp.HTML == "" {
		writeError("html field is required")
		return
	}

	out := parse(inp.HTML)
	data, _ := json.Marshal(out)
	fmt.Println(string(data))
}

// parse performs simple HTML extraction without CGO.
func parse(html string) Output {
	out := Output{}

	// Title
	if i := strings.Index(html, "<title"); i >= 0 {
		if j := strings.Index(html[i:], ">"); j >= 0 {
			start := i + j + 1
			if k := strings.Index(html[start:], "</title>"); k >= 0 {
				out.Title = strings.TrimSpace(html[start : start+k])
			}
		}
	}

	// Strip tags for plain text (simplified).
	noTags := stripTags(html)
	out.Text = strings.Join(strings.Fields(noTags), " ")
	if len(out.Text) > 2000 {
		out.Text = out.Text[:2000] + "..."
	}

	// Extract href links.
	rest := html
	for {
		idx := strings.Index(rest, "href=\"")
		if idx < 0 {
			break
		}
		rest = rest[idx+6:]
		end := strings.IndexByte(rest, '"')
		if end < 0 {
			break
		}
		link := rest[:end]
		if strings.HasPrefix(link, "http") {
			out.Links = append(out.Links, link)
		}
		rest = rest[end:]
	}
	return out
}

func stripTags(s string) string {
	var b strings.Builder
	inTag := false
	for _, r := range s {
		switch {
		case r == '<':
			inTag = true
		case r == '>':
			inTag = false
			b.WriteRune(' ')
		case !inTag:
			b.WriteRune(r)
		}
	}
	return b.String()
}

func writeError(msg string) {
	data, _ := json.Marshal(Output{Error: msg})
	fmt.Println(string(data))
}
