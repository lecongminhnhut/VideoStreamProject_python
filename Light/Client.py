from tkinter import *
import tkinter.messagebox
from tkinter import messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import time
from ClientNetworkAnalyzer import ClientNetworkAnalyzer
from queue import Queue

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"

class Client:
	INIT = 0
	READY = 1
	PLAYING = 2
	state = INIT
	
	SETUP = 0
	PLAY = 1
	PAUSE = 2
	TEARDOWN = 3
	
	# Initiation..
	def __init__(self, master, serveraddr, serverport, rtpport, filename):
		self.master = master
		self.master.protocol("WM_DELETE_WINDOW", self.handler)
		self.createWidgets()
		self.serverAddr = serveraddr
		self.serverPort = int(serverport)
		self.rtpPort = int(rtpport)
		self.fileName = filename
		self.rtspSeq = 0
		self.sessionId = 0
		self.requestSent = -1
		self.teardownAcked = 0
		self.connectToServer()
		self.frameNbr = 0
		self.frame_buffer = FrameBuffer()

		
	def createWidgets(self):
		"""Build GUI."""
		# Create Setup button
		self.setup = Button(self.master, width=20, padx=3, pady=3)
		self.setup["text"] = "Setup"
		self.setup["command"] = self.setupMovie
		self.setup.grid(row=1, column=0, padx=2, pady=2)
		
		# Create Play button		
		self.start = Button(self.master, width=20, padx=3, pady=3)
		self.start["text"] = "Play"
		self.start["command"] = self.playMovie
		self.start.grid(row=1, column=1, padx=2, pady=2)
		
		# Create Pause button			
		self.pause = Button(self.master, width=20, padx=3, pady=3)
		self.pause["text"] = "Pause"
		self.pause["command"] = self.pauseMovie
		self.pause.grid(row=1, column=2, padx=2, pady=2)
		
		# Create Teardown button
		self.teardown = Button(self.master, width=20, padx=3, pady=3)
		self.teardown["text"] = "Teardown"
		self.teardown["command"] =  self.exitClient
		self.teardown.grid(row=1, column=3, padx=2, pady=2)
		
		# Create a label to display the movie
		self.label = Label(self.master, height=19)
		self.label.grid(row=0, column=0, columnspan=4, sticky=W+E+N+S, padx=5, pady=5) 
	
	def setupMovie(self):
		"""Setup button handler."""
		if self.state == self.INIT:
			self.sendRtspRequest(self.SETUP)
	
	def exitClient(self):
		"""Teardown button handler."""
		self.sendRtspRequest(self.TEARDOWN)		
		self.master.destroy() # Close the gui window
		os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT) # Delete the cache image from video

	def pauseMovie(self):
		"""Pause button handler."""
		if self.state == self.PLAYING:
			self.sendRtspRequest(self.PAUSE)
	
	def playMovie(self):
		"""Play button handler."""
		if self.state == self.READY:
			# Create a new thread to listen for RTP packets
			self.frame_buffer.start_buffered_playback(self)
			threading.Thread(target=self.listenRtp).start()
			self.playEvent = threading.Event()
			self.playEvent.clear()
			self.sendRtspRequest(self.PLAY)
	
	# def listenRtp(self):		
	# 	"""Listen for RTP packets."""
	# 	while True:
	# 		try:
	# 			data = self.rtpSocket.recv(20480)
	# 			if data:
	# 				rtpPacket = RtpPacket()
	# 				rtpPacket.decode(data)
					
	# 				currFrameNbr = rtpPacket.seqNum()
	# 				print("Current Seq Num: " + str(currFrameNbr))
										
	# 				if currFrameNbr > self.frameNbr: # Discard the late packet
	# 					self.frameNbr = currFrameNbr
	# 					self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
	# 		except:
	# 			# Stop listening upon requesting PAUSE or TEARDOWN
	# 			if self.playEvent.isSet(): 
	# 				break
				
	# 			# Upon receiving ACK for TEARDOWN request,
	# 			# close the RTP socket
	# 			if self.teardownAcked == 1:
	# 				self.rtpSocket.shutdown(socket.SHUT_RDWR)
	# 				self.rtpSocket.close()
	# 				break 
	# -->> Day la ban cu <<--

	def listenRtp(self):
		while True:
			try:
				data, addr = self.rtpSocket.recvfrom(65535)
				packet = RtpPacket()
				packet.decode(data)

				frame_id = packet.frame_id()
				frag_id = packet.fragment_id()
				total_frag = packet.total_fragments()
				payload = packet.get_payload()

				self.frame_buffer.add_frame_fragment(
					frame_id, frag_id, total_frag, payload
				)

			except:
				if self.playEvent.isSet():
					break
				if self.teardownAcked == 1:
					try:
						self.rtpSocket.shutdown(socket.SHUT_RDWR)
						self.rtpSocket.close()
					except:
						pass
					break
				continue
					
	def writeFrame(self, data):
		"""Write the received frame to a temp image file. Return the image file."""
		cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
		file = open(cachename, "wb")
		file.write(data)
		file.close()
		
		return cachename
	
	def updateMovie(self, imageFile):
		"""Update the image file as video frame in the GUI."""
		photo = ImageTk.PhotoImage(Image.open(imageFile))
		self.label.configure(image = photo, height=288) 
		self.label.image = photo
		
	def connectToServer(self):
		"""Connect to the Server. Start a new RTSP/TCP session."""
		self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		try:
			self.rtspSocket.connect((self.serverAddr, self.serverPort))
		except:
			tkinter.messagebox.showwarning('Unable to Bind', 'Unable to bind PORT=%d' %self.rtpPort)

	def sendRtspRequest(self, requestCode):
		"""Send RTSP request to the server."""
		if requestCode == self.SETUP and self.state == self.INIT:
			threading.Thread(target=self.recvRtspReply).start()
			self.rtspSeq += 1
			request = f"SETUP {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nTransport: RTP/UDP; client_port= {self.rtpPort}"
			self.requestSent = self.SETUP

		elif requestCode == self.PLAY and self.state == self.READY:
			self.rtspSeq += 1
			request = f"PLAY {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"
			self.requestSent = self.PLAY

		elif requestCode == self.PAUSE and self.state == self.PLAYING:
			self.rtspSeq += 1
			request = f"PAUSE {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"
			self.requestSent = self.PAUSE

		elif requestCode == self.TEARDOWN and not self.state == self.INIT:
			self.rtspSeq += 1
			request = f"TEARDOWN {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"
			self.requestSent = self.TEARDOWN

		else:
			return

		self.rtspSocket.send(request.encode())
		print('\nData sent:\n' + request)
	
	def recvRtspReply(self):
		"""Receive RTSP reply from the server."""
		while True:
			reply = self.rtspSocket.recv(1024)
			
			if reply: 
				self.parseRtspReply(reply.decode("utf-8"))
			
			# Close the RTSP socket upon requesting Teardown
			if self.requestSent == self.TEARDOWN:
				self.rtspSocket.shutdown(socket.SHUT_RDWR)
				self.rtspSocket.close()
				break
	
	def parseRtspReply(self, data):
		"""Parse the RTSP reply from the server."""
		lines = data.split('\n')
		seqNum = int(lines[1].split(' ')[1])
		
		# Process only if the server reply's sequence number is the same as the request's
		if seqNum == self.rtspSeq:
			session = int(lines[2].split(' ')[1])
			# New RTSP session ID
			if self.sessionId == 0:
				self.sessionId = session
			
			# Process only if the session ID is the same
			if self.sessionId == session:
				if int(lines[0].split(' ')[1]) == 200: 
					if self.requestSent == self.SETUP:
						self.state = self.READY
						self.openRtpPort() 
					elif self.requestSent == self.PLAY:
						self.state = self.PLAYING
						self.start_buffered_playback()
					elif self.requestSent == self.PAUSE:
						self.state = self.READY
						self.playEvent.set()
					elif self.requestSent == self.TEARDOWN:
						self.state = self.INIT
						self.teardownAcked = 1
	
	def openRtpPort(self):
		"""Open RTP socket binded to a specified port."""
		# Create a new datagram socket to receive RTP packets from the server
		self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		
		# Set the timeout value of the socket to 0.5sec
		self.rtpSocket.settimeout(0.5)
		
		try:
			# Bind the socket to the address using the RTP port given by the client user
			self.rtpSocket.bind(('', self.rtpPort))
		except:
			tkinter.messagebox.showwarning('Unable to Bind', f'Unable to bind PORT={self.rtpPort}')
	
	def handler(self):
		"""Handler on explicitly closing the GUI window."""
		self.pauseMovie()
		if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
			self.exitClient()
		else: # When the user presses cancel, resume playing.
			self.playMovie()

	def start_buffered_playback(self):
		t = threading.Thread(target=self.play_from_buffer, daemon=True)
		t.start()

	def play_from_buffer(self):
		delay = 1 / 30
		while True:
			frame = self.frame_buffer.get_next_frame()
			if frame:
				img = Image.open(io.BytesIO(frame))
				imgtk = ImageTk.PhotoImage(image=img)
				self.label.configure(image=imgtk)
				self.label.image = imgtk
				time.sleep(delay)
			else:
				time.sleep(0.005)


class FrameBuffer:
	def __init__(self, max_buffer_size=50):
		self.fragment_map = {}
		self.frame_queue = Queue(maxsize=max_buffer_size)
		self.max_buffer_size = max_buffer_size
		
	def add_frame_fragment(self, frame_id, fragment_id, total_fragments, payload):
		if frame_id not in self.fragment_map:
			self.fragment_map[frame_id] = {
				"total": total_fragments,
				"received": {},
				"timestamp": time.time()
			}
			self.fragment_map[frame_id]["received"][fragment_id] = payload
		
		if len(self.fragment_map[frame_id]["received"]) == total_fragments:
			return self._assemble_frame(frame_id)
		
		return None

	def _assemble_frame(self, frame_id):
		data = self.fragment_map[frame_id]
		fragments = data["received"]

		frame_bytes = b"".join(
			fragments[i] for i in sorted(fragments.keys())
		)

		del self.fragment_map[frame_id]

		if not self.frame_queue.full():
			self.frame_queue.put(frame_bytes)

		return frame_bytes
	
	def get_buffer_health(self):
		return self.frame_queue.qsize() / self.max_buffer_size
	
	def get_next_frame(self):
		if self.frame_queue.empty():
			return None
		return self.frame_queue.get()
	
	