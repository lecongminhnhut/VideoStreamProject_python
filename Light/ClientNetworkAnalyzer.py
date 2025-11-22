import time

class ClientNetworkAnalyzer:
    def __init__(self):
        self.last_timestamp = time.time()
        self.received_packets = 0
        self.lost_packets = 0

    def update(self, packet_id, expected_id):
        if packet_id != expected_id:
            self.lost_packets += expected_id - packet_id
        self.received_packets += 1

    def calculate_packet_loss(self):
        total = self.received_packets + self.lost_packets
        if total == 0:
            return 0
        return self.lost_packets / total

    def estimate_available_bandwidth(self, bytes_received):
        now = time.time()
        dt = now - self.last_timestamp
        self.last_timestamp = now
        if dt == 0:
            return 0
        return bytes_received / dt