//go:build wasip1

// json_parse queries a JSON document with a dot-notation path.
// Compile: GOOS=js GOARCH=wasm go build -o json_parse.wasm .
package main

import (
	"encoding/json"
	"fmt"
	"os"
	"strings"
)

type Input struct {
	JSON string `json:"json"`
	Path string `json:"path,omitempty"` // e.g. "user.address.city"
}

type Output struct {
	Value  any    `json:"value"`
	Type   string `json:"type"`
	Error  string `json:"error,omitempty"`
}

func main() {
	if len(os.Args) < 2 {
		writeOut(Output{Error: "input JSON required"})
		return
	}
	var inp Input
	if err := json.Unmarshal([]byte(os.Args[1]), &inp); err != nil {
		writeOut(Output{Error: "decode input: " + err.Error()})
		return
	}
	if inp.JSON == "" {
		writeOut(Output{Error: "json field required"})
		return
	}

	var doc any
	if err := json.Unmarshal([]byte(inp.JSON), &doc); err != nil {
		writeOut(Output{Error: "parse json: " + err.Error()})
		return
	}

	val := doc
	if inp.Path != "" {
		parts := strings.Split(inp.Path, ".")
		for _, p := range parts {
			m, ok := val.(map[string]any)
			if !ok {
				writeOut(Output{Error: fmt.Sprintf("path %q: not an object at %q", inp.Path, p)})
				return
			}
			val, ok = m[p]
			if !ok {
				writeOut(Output{Error: fmt.Sprintf("key %q not found", p)})
				return
			}
		}
	}

	writeOut(Output{Value: val, Type: typeName(val)})
}

func typeName(v any) string {
	switch v.(type) {
	case nil:
		return "null"
	case bool:
		return "bool"
	case float64:
		return "number"
	case string:
		return "string"
	case []any:
		return "array"
	case map[string]any:
		return "object"
	default:
		return "unknown"
	}
}

func writeOut(o Output) {
	data, _ := json.Marshal(o)
	fmt.Println(string(data))
}
