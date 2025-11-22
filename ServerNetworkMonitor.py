import time
import json
from datetime import datetime

class ServerNetworkMonitor:
    def __init__(self):
        self.packet_log = []
        self.start_time = time.time()
        self.total_packets_sent = 0
        self.total_bytes_sent = 0
        
    def log_packet_sent(self, packet_size, destination_ip, destination_port, packet_type):
        """Log thông tin packet được gửi"""
        log_entry = {
            'timestamp': datetime.now().isoformat(),
            'packet_size': packet_size,
            'destination_ip': destination_ip,
            'destination_port': destination_port,
            'packet_type': packet_type,
            'frame_time': time.time() - self.start_time
        }
        
        self.packet_log.append(log_entry)
        self.total_packets_sent += 1
        self.total_bytes_sent += packet_size
        
        # In log real-time (có thể tắt trong production)
        print(f"Packet sent: {packet_type} | Size: {packet_size} bytes | To: {destination_ip}:{destination_port}")
    
    def generate_network_report(self):
        """Tạo báo cáo hiệu năng mạng"""
        if not self.packet_log:
            return "No packets sent yet"
            
        current_time = time.time()
        session_duration = current_time - self.start_time
        
        # Tính toán thống kê
        avg_packet_size = self.total_bytes_sent / self.total_packets_sent if self.total_packets_sent > 0 else 0
        packets_per_second = self.total_packets_sent / session_duration if session_duration > 0 else 0
        bandwidth_usage = self.total_bytes_sent / session_duration if session_duration > 0 else 0
        
        report = {
            'session_start': datetime.fromtimestamp(self.start_time).isoformat(),
            'session_duration_seconds': session_duration,
            'total_packets_sent': self.total_packets_sent,
            'total_bytes_sent': self.total_bytes_sent,
            'average_packet_size_bytes': avg_packet_size,
            'packets_per_second': packets_per_second,
            'bandwidth_usage_bps': bandwidth_usage * 8,  # Convert to bits per second
            'hd_streaming_enabled': any('HD' in log['packet_type'] for log in self.packet_log),
            'fragmentation_used': any(log['packet_size'] > 1400 for log in self.packet_log)
        }
        
        return json.dumps(report, indent=2)
    
    def get_real_time_stats(self):
        """Lấy thống kê real-time"""
        current_time = time.time()
        session_duration = current_time - self.start_time
        
        return {
            'duration': session_duration,
            'total_packets': self.total_packets_sent,
            'total_data_mb': self.total_bytes_sent / (1024 * 1024),
            'current_bandwidth_mbps': (self.total_bytes_sent * 8) / (session_duration * 1000000) if session_duration > 0 else 0
        }