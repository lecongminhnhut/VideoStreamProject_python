
import json
import time

class AdaptiveStreamingController:
    def __init__(self, profile_file="quality_profiles.json"):
        with open(profile_file, "r") as f:
            self.quality_profiles = json.load(f)
        self.current_quality = "medium"
        self.last_adjust_time = 0

    def analyze_network_conditions(self, net_stats):
        score = 0
        score += max(0, 100 - net_stats['latency'])
        score += max(0, 100 - net_stats['packet_loss'] * 200)
        score += min(100, net_stats['bandwidth'] / 10)
        return score

    def calculate_optimal_delay(self, net_stats):
        if net_stats['packet_loss'] > 0.1:
            return 120
        if net_stats['latency'] > 200:
            return 80
        return 40

    def adjust_streaming_quality(self, net_score):
        now = time.time()
        if now - self.last_adjust_time < 2:
            return self.current_quality

        if net_score < 120:
            self.current_quality = "low"
        elif net_score < 200:
            self.current_quality = "medium"
        else:
            self.current_quality = "high"

        self.last_adjust_time = now
        return self.current_quality
