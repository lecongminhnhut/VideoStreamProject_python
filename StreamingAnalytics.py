
import statistics

class StreamingAnalytics:
    def __init__(self):
        self.latencies = []
        self.loss_events = 0
        self.quality_switches = []

    def collect_playback_metrics(self, latency, lost):
        if latency is not None:
            self.latencies.append(latency)
        if lost:
            self.loss_events += 1

    def generate_performance_report(self):
        avg_latency = statistics.mean(self.latencies) if self.latencies else 0
        return {
            'avg_latency': avg_latency,
            'loss_events': self.loss_events,
            'quality_switches': self.quality_switches
        }

    def create_visualization_dashboard(self):
        return "Dashboard generated (placeholder)."
