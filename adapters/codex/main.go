// Command codex-grader runs one advisory grading turn with an explicit model.
package main

import (
	"context"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"os/signal"
	"syscall"

	adapter "github.com/shakystar/codex-adapter"
)

func classified(err error, stage, execution string) error {
	if adapter.FailureOf(err) != nil {
		return err
	}
	return &adapter.Failure{Version: 1, Stage: stage, Code: "operation_failed", Execution: execution}
}

func run() error {
	model := flag.String("model", "", "Codex model identifier")
	state := flag.String("state", "", "durable state directory")
	flag.Parse()
	if *model == "" || *state == "" {
		return classified(fmt.Errorf("model and state are required"), "configuration", adapter.NotStarted)
	}
	var req adapter.Request
	if err := json.NewDecoder(os.Stdin).Decode(&req); err != nil {
		return classified(err, "request_decode", adapter.NotStarted)
	}
	if err := req.Validate(); err != nil {
		return classified(err, "request_validation", adapter.NotStarted)
	}
	ctx, cancel := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer cancel()
	client, err := adapter.NewContext(ctx, adapter.Config{StateDir: *state, Model: *model})
	if err != nil {
		return classified(err, "initialization", adapter.NotStarted)
	}
	defer client.Close()
	result, err := client.Execute(ctx, req)
	if err != nil {
		return classified(err, "execute", adapter.Unknown)
	}
	if err := json.NewEncoder(os.Stdout).Encode(map[string]any{"text": result.Text, "session": result.Session, "usage": client.Usage()}); err != nil {
		return classified(err, "output", adapter.Completed)
	}
	return nil
}

func main() {
	if err := run(); err != nil {
		json.NewEncoder(os.Stderr).Encode(map[string]any{"event": "error", "error": err.Error(), "failure": adapter.FailureOf(err)})
		os.Exit(1)
	}
}
