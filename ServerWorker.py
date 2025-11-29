from random import randint
import sys, traceback, threading, socket

from VideoStream import VideoStream
from RtpPacket import RtpPacket
from ServerNetworkMonitor import ServerNetworkMonitor

import time
import json

class ServerWorker:
    SETUP = 'SETUP'
    PLAY = 'PLAY'
    PAUSE = 'PAUSE'
    TEARDOWN = 'TEARDOWN'
    
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    OK_200 = 0
    FILE_NOT_FOUND_404 = 1
    CON_ERR_500 = 2
    
    clientInfo = {}
    
    def __init__(self, clientInfo):
        self.clientInfo = clientInfo
        self.network_monitor = ServerNetworkMonitor()

    def run(self):
        threading.Thread(target=self.recvRtspRequest).start()
    
    def recvRtspRequest(self):
        """Receive RTSP request from the client."""
        connSocket = self.clientInfo['rtspSocket'][0]
        while True:            
            data = connSocket.recv(256)
            if data:
                print("Data received:\n" + data.decode("utf-8"))
                self.processRtspRequest(data.decode("utf-8"))
    
    def processRtspRequest(self, data):
        """Process RTSP request sent from the client."""
        # Get the request type
        request = data.split('\n')
        line1 = request[0].split(' ')
        requestType = line1[0]
        
        # Get the media file name
        filename = line1[1]
        
        # Get the RTSP sequence number 
        seq = request[1].split(' ')
        
        # Process SETUP request
        if requestType == self.SETUP:
            if self.state == self.INIT:
                # Update state
                print("processing SETUP\n")
                
                try:
                    #self.clientInfo['videoStream'] = VideoStream(filename)
                    self.setup_hd_streaming(filename)
                    self.state = self.READY
                except IOError:
                    self.replyRtsp(self.FILE_NOT_FOUND_404, seq[1])
                
                # Generate a randomized RTSP session ID
                self.clientInfo['session'] = randint(100000, 999999)
                
                # Send RTSP reply
                self.replyRtsp(self.OK_200, seq[1])
                
                # Get the RTP/UDP port from the last line
                self.clientInfo['rtpPort'] = request[2].split(' ')[3]
        
        # Process PLAY request         
        elif requestType == self.PLAY:
            if self.state == self.READY:
                print("processing PLAY\n")
                self.state = self.PLAYING
                
                # Create a new socket for RTP/UDP
                self.clientInfo["rtpSocket"] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                
                self.replyRtsp(self.OK_200, seq[1])
                
                # Create a new thread and start sending RTP packets
                self.clientInfo['event'] = threading.Event()
                self.clientInfo['worker']= threading.Thread(target=self.sendRtp) 
                self.clientInfo['worker'].start()
        
        # Process PAUSE request
        elif requestType == self.PAUSE:
            if self.state == self.PLAYING:
                print("processing PAUSE\n")
                self.state = self.READY
                
                self.clientInfo['event'].set()
            
                self.replyRtsp(self.OK_200, seq[1])
        
        # Process TEARDOWN request
        elif requestType == self.TEARDOWN:
            print("processing TEARDOWN\n")

            self.clientInfo['event'].set()
            
            self.replyRtsp(self.OK_200, seq[1])
            
            # Close the RTP socket
            self.clientInfo['rtpSocket'].close()
            
    def sendRtp(self):
        """Send RTP packets over UDP."""
        while True:
            self.clientInfo['event'].wait(0.05) 
            
            # Stop sending if request is PAUSE or TEARDOWN
            if self.clientInfo['event'].isSet(): 
                break 
                
            data = self.clientInfo['videoStream'].nextFrame()
            if data: 
                frameNumber = self.clientInfo['videoStream'].frameNbr()
                try:
                    address = self.clientInfo['rtspSocket'][1][0]
                    port = int(self.clientInfo['rtpPort'])
                    self.clientInfo['rtpSocket'].sendto(self.makeRtp(data, frameNumber),(address,port))
                except:
                    print("Connection Error")

    def makeRtp(self, payload, frameNbr, marker = 0):
        """RTP-packetize the video data."""
        version = 2
        padding = 0
        extension = 0
        cc = 0
        marker_bit = marker
        pt = 26 # MJPEG type
        seqnum = frameNbr
        ssrc = 0 
        
        rtpPacket = RtpPacket()
        
        rtpPacket.encode(version, padding, extension, cc, seqnum, marker_bit, pt, ssrc, payload)
        
        return rtpPacket.getPacket()
        
    def replyRtsp(self, code, seq):
        """Send RTSP reply to the client."""
        if code == self.OK_200:
            reply = 'RTSP/1.0 200 OK\nCSeq: ' + seq + '\nSession: ' + str(self.clientInfo['session'])
            connSocket = self.clientInfo['rtspSocket'][0]
            connSocket.send(reply.encode())
        
        # Error messages
        elif code == self.FILE_NOT_FOUND_404:
            print("404 NOT FOUND")
        elif code == self.CON_ERR_500:
            print("500 CONNECTION ERROR")

    # ==================== CÁC HÀM MỚI - THỤT LỀ VÀO TRONG CLASS ====================
    
    def fragment_hd_frame(self, frame_data, frame_number):
        """Phân mảnh frame HD thành các RTP packet nhỏ hơn MTU"""
        MTU = 1400  # Maximum Transmission Unit
        fragments = []
        
        # Kiểm tra nếu frame cần phân mảnh
        if len(frame_data) <= MTU - 12:  # Trừ header RTP
            # Frame nhỏ, không cần phân mảnh
            fragments.append((frame_data, 1))  # (data, marker_bit)
        else:
            # Phân mảnh frame lớn
            frame_size = len(frame_data)
            offset = 0
            fragment_count = 0
            
            while offset < frame_size:
                # Tính kích thước fragment (trừ header RTP)
                chunk_size = min(MTU - 12, frame_size - offset)
                fragment_data = frame_data[offset:offset + chunk_size]
                offset += chunk_size
                
                # Marker bit = 1 cho fragment cuối cùng
                marker_bit = 1 if offset >= frame_size else 0
                fragments.append((fragment_data, marker_bit))
                fragment_count += 1
                
            print(f"Frame {frame_number} fragmented into {fragment_count} packets")
        
        return fragments

    def calculate_adaptive_delay(self, frame_size, network_conditions=None):
        """Tính delay tối ưu dựa trên kích thước frame và điều kiện mạng"""
        BASE_DELAY = 0.04  # 40ms base delay cho video thường
        
        # Điều chỉnh delay dựa trên kích thước frame
        if frame_size > 100000:  # Frame HD lớn
            adaptive_delay = BASE_DELAY * 1.5  # Tăng delay cho frame lớn
        elif frame_size > 50000:  # Frame HD trung bình
            adaptive_delay = BASE_DELAY * 1.2
        else:  # Frame nhỏ
            adaptive_delay = BASE_DELAY
        
        # Điều chỉnh dựa trên điều kiện mạng (nếu có thông tin)
        if network_conditions and network_conditions.get('congestion', False):
            adaptive_delay *= 2  # Tăng delay gấp đôi khi mạng nghẽn
        
        return max(0.02, min(adaptive_delay, 0.1))  # Giới hạn trong khoảng 20-100ms

    def send_rtp_packet(self, rtp_packet, address, port, retry_count=2):
        """Gửi RTP packet với cơ chế retry và logging"""
        max_retries = retry_count
        retries = 0
        
        while retries <= max_retries:
            try:
                # Gửi packet
                self.clientInfo['rtpSocket'].sendto(rtp_packet, (address, port))
                
                # Log packet đã gửi
                packet_size = len(rtp_packet)
                self.log_packet_sent(packet_size, address, port, "HD_FRAME")
                
                return True  # Gửi thành công
                
            except socket.error as e:
                retries += 1
                print(f"Packet send failed, retry {retries}/{max_retries}: {e}")
                
                if retries > max_retries:
                    print("Max retries exceeded, packet lost")
                    return False
        
        return False

    def setup_hd_streaming(self, filename):
        """Thiết lập streaming cho video HD"""
        # Mở file video
        self.clientInfo['videoStream'] = VideoStream(filename)
        
        # Kiểm tra nếu là video HD (dựa trên kích thước frame đầu tiên)
        test_frame = self.clientInfo['videoStream'].nextFrame()
        
        if test_frame and len(test_frame) > 50000:  # Frame > 50KB coi như HD
            print("HD video detected - enabling enhanced streaming")
            self.clientInfo['is_hd'] = True
        else:
            self.clientInfo['is_hd'] = False
            
        # Reset stream về đầu
        self.clientInfo['videoStream'].file.seek(0)
        self.clientInfo['videoStream'].frameNum = 0

    def log_packet_sent(self, packet_size, address, port, packet_type):
        """Log packet đã gửi"""
        try:
            self.network_monitor.log_packet_sent(packet_size, address, port, packet_type)
        except:
            print(f"Packet sent: {packet_type} | Size: {packet_size} bytes | To: {address}:{port}")