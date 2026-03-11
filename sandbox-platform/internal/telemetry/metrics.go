// Package telemetry provides Prometheus metrics for the platform.
package telemetry

import (
	"github.com/prometheus/client_golang/prometheus"
	"github.com/prometheus/client_golang/prometheus/promauto"
)

var (
	// JobsSubmitted counts all jobs submitted via POST /execute.
	JobsSubmitted = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "sandbox_jobs_submitted_total",
		Help: "Total jobs submitted, by tool and tier.",
	}, []string{"tool", "tier"})

	// JobsCompleted counts finished jobs.
	JobsCompleted = promauto.NewCounterVec(prometheus.CounterOpts{
		Name: "sandbox_jobs_completed_total",
		Help: "Total jobs completed, by tool, tier, and status.",
	}, []string{"tool", "tier", "status"})

	// JobDuration records how long jobs take end-to-end.
	JobDuration = promauto.NewHistogramVec(prometheus.HistogramOpts{
		Name:    "sandbox_job_duration_seconds",
		Help:    "Job execution duration by tier.",
		Buckets: []float64{0.01, 0.05, 0.1, 0.5, 1, 5, 30, 60, 300},
	}, []string{"tier"})

	// ActiveVMs tracks how many Firecracker VMs are currently allocated.
	ActiveVMs = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "sandbox_active_vms",
		Help: "Number of active Firecracker microVMs.",
	})

	// ActiveContainers tracks running GUI containers.
	ActiveContainers = promauto.NewGauge(prometheus.GaugeOpts{
		Name: "sandbox_active_gui_containers",
		Help: "Number of active GUI Docker containers.",
	})

	// QueueDepth reports how many jobs are waiting.
	QueueDepth = promauto.NewGaugeVec(prometheus.GaugeOpts{
		Name: "sandbox_queue_depth",
		Help: "Jobs currently queued, by stream.",
	}, []string{"stream"})
)
