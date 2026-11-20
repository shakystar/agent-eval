package main

import (
	"errors"
	"testing"

	adapter "github.com/shakystar/codex-adapter"
)

func TestPreserveAdapterFailure(t *testing.T) {
	for _, execution := range []string{adapter.NotStarted, adapter.Unknown, adapter.Started, adapter.Completed} {
		failure := &adapter.Failure{Version: 1, Stage: "test", Execution: execution, Code: "timeout", Attempts: 3}
		if got := classified(failure, "execute", adapter.Unknown); got != failure {
			t.Fatalf("lost adapter failure for %s", execution)
		}
	}
	got := adapter.FailureOf(classified(errors.New("invalid"), "request_validation", adapter.NotStarted))
	if got == nil || got.Execution != adapter.NotStarted || got.Retryable {
		t.Fatal("incorrect local validation failure")
	}
}
