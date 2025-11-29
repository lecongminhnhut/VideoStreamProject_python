import time

class ClientNetworkAnalyzer:
    def __init__(self):
        self.last_timestamp = time.time()
        self.received_packets = 0
        self.lost_packets = 0
        self.expected_rtp_seq = None
        self.bytes_since_last = 0
        self.last_bandwidth_calc = time.time()
        self.current_bandwidth = 0

    def record_rtsp_send(self, message):
        pass

    def record_rtsp_reply(self, message):
        pass

    def handle_rtp(self, packet):
        seq = packet.seqNum()
        if self.expected_rtp_seq is None:
            self.expected_rtp_seq = seq + 1
        else:
            if seq > self.expected_rtp_seq:
                self.lost_packets += seq - self.expected_rtp_seq
            self.expected_rtp_seq = seq + 1
        self.received_packets += 1
        payload = packet.getPayload()
        self.bytes_since_last += len(payload)
        now = time.time()
        if now - self.last_bandwidth_calc >= 1:
            self.current_bandwidth = self.bytes_since_last / (now - self.last_bandwidth_calc)
            self.bytes_since_last = 0
            self.last_bandwidth_calc = now

    def get_packet_loss(self):
        total = self.received_packets + self.lost_packets
        if total == 0:
            return 0
        return self.lost_packets / total

    def get_bandwidth(self):
        return self.current_bandwidth
