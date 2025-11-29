from tkinter import *
import tkinter.messagebox
from tkinter import messagebox as tkMessageBox
from PIL import Image, ImageTk
import socket, threading, os, time, io
from queue import Queue

from ClientNetworkAnalyzer import ClientNetworkAnalyzer
from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"


class FrameBuffer:
    def __init__(self, max_buffer_size=50, fragment_timeout=2.0, cleanup_interval=1.0):
        self.fragment_map = {}
        self.frame_queue = Queue(maxsize=max_buffer_size)
        self.max_buffer_size = max_buffer_size
        self.fragment_timeout = fragment_timeout
        self.lock = threading.Lock()
        self._stop_cleanup = threading.Event()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()

    def add_frame_fragment(self, frame_id, fragment_id, total_fragments, payload):
        with self.lock:
            if frame_id not in self.fragment_map:
                self.fragment_map[frame_id] = {
                    "total": total_fragments,
                    "received": {},
                    "timestamp": time.time()
                }
            entry = self.fragment_map[frame_id]
            # store fragment if new
            if fragment_id not in entry["received"]:
                entry["received"][fragment_id] = payload
            # check completion
            if len(entry["received"]) == entry["total"]:
                return self._assemble_frame_locked(frame_id)
        return None

    def _assemble_frame_locked(self, frame_id):
        data = self.fragment_map.pop(frame_id, None)
        if data is None:
            return None
        fragments = data["received"]
        try:
            frame_bytes = b"".join(fragments[i] for i in sorted(fragments.keys()))
        except Exception:
            # malformed fragments
            return None
        if not self.frame_queue.full():
            try:
                self.frame_queue.put_nowait(frame_bytes)
            except:
                pass
        return frame_bytes

    def _cleanup_loop(self):
        while not self._stop_cleanup.is_set():
            now = time.time()
            with self.lock:
                to_delete = [fid for fid, d in self.fragment_map.items() if now - d["timestamp"] > self.fragment_timeout]
                for fid in to_delete:
                    try:
                        del self.fragment_map[fid]
                    except:
                        pass
            time.sleep(1.0)

    def get_buffer_health(self):
        return self.frame_queue.qsize() / self.max_buffer_size

    def get_next_frame(self):
        try:
            return self.frame_queue.get_nowait()
        except:
            return None

    def stop(self):
        self._stop_cleanup.set()
        try:
            self._cleanup_thread.join(timeout=1.0)
        except:
            pass


class Client:
    INIT = 0
    READY = 1
    PLAYING = 2
    state = INIT

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3

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
        self.frameNbr = 0
        self.playEvent = threading.Event()
        self.playEvent.clear()
        self.analyzer = ClientNetworkAnalyzer()
        self.frame_buffer = FrameBuffer()
        self.rtpSocket = None
        self.rtspSocket = None
        self.rtp_listen_thread = None
        self.rtsp_reply_thread = None
        self.connectToServer()

    def createWidgets(self):
        self.setup = Button(self.master, width=20, padx=3, pady=3)
        self.setup["text"] = "Setup"
        self.setup["command"] = self.setupMovie
        self.setup.grid(row=1, column=0, padx=2, pady=2)

        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=1, padx=2, pady=2)

        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=2, padx=2, pady=2)

        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.exitClient
        self.teardown.grid(row=1, column=3, padx=2, pady=2)

        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W + E + N + S, padx=5, pady=5)

    def setupMovie(self):
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

    def exitClient(self):
        self.sendRtspRequest(self.TEARDOWN)
        self.master.destroy()
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        if os.path.exists(cachename):
            try:
                os.remove(cachename)
            except:
                pass
        # stop buffer cleanup
        try:
            self.frame_buffer.stop()
        except:
            pass

    def pauseMovie(self):
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        if self.state == self.READY:
            self.sendRtspRequest(self.PLAY)

    def connectToServer(self):
        try:
            self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.rtspSocket.settimeout(5.0)
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
            self.rtspSocket.settimeout(None)
        except Exception:
            tkinter.messagebox.showwarning('Unable to Connect', f'Unable to connect to RTSP server {self.serverAddr}:{self.serverPort}')

    def sendRtspRequest(self, requestCode):
        if requestCode == self.SETUP and self.state == self.INIT:
            self.rtspSeq += 1
            request = f"SETUP {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nTransport: RTP/UDP; client_port={self.rtpPort}"
            self.requestSent = self.SETUP
            self.analyzer.record_rtsp_send(self.rtspSeq)
            if not self.rtsp_reply_thread or not self.rtsp_reply_thread.is_alive():
                self.rtsp_reply_thread = threading.Thread(target=self.recvRtspReply, daemon=True)
                self.rtsp_reply_thread.start()

        elif requestCode == self.PLAY and self.state == self.READY:
            self.rtspSeq += 1
            request = f"PLAY {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"
            self.requestSent = self.PLAY
            self.analyzer.record_rtsp_send(self.rtspSeq)

        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            self.rtspSeq += 1
            request = f"PAUSE {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"
            self.requestSent = self.PAUSE
            self.analyzer.record_rtsp_send(self.rtspSeq)

        elif requestCode == self.TEARDOWN and self.state != self.INIT:
            self.rtspSeq += 1
            request = f"TEARDOWN {self.fileName} RTSP/1.0\nCSeq: {self.rtspSeq}\nSession: {self.sessionId}"
            self.requestSent = self.TEARDOWN
            self.analyzer.record_rtsp_send(self.rtspSeq)

        else:
            return

        try:
            self.rtspSocket.send(request.encode())
        except Exception:
            pass

    def recvRtspReply(self):
        while True:
            try:
                reply = self.rtspSocket.recv(4096)
                if not reply:
                    continue
                self.parseRtspReply(reply.decode("utf-8"))
            except Exception:
                # exit on teardown acked and socket closed
                if self.requestSent == self.TEARDOWN:
                    try:
                        if self.rtspSocket:
                            self.rtspSocket.close()
                    except:
                        pass
                    break
                time.sleep(0.1)
                continue

    def parseRtspReply(self, data):
        try:
            lines = [ln.strip() for ln in data.split('\n') if ln.strip() != ""]
            if len(lines) < 2:
                return
            seqNum = int(lines[1].split(' ')[1])
        except Exception:
            return

        self.analyzer.record_rtsp_reply(seqNum)

        if seqNum != self.rtspSeq:
            return

        try:
            session = int(lines[2].split(' ')[1])
        except Exception:
            session = self.sessionId

        if self.sessionId == 0:
            self.sessionId = session

        if session != self.sessionId:
            return

        try:
            status_code = int(lines[0].split(' ')[1])
        except Exception:
            status_code = 0

        if status_code != 200:
            return

        if self.requestSent == self.SETUP:
            self.state = self.READY
            self.openRtpPort()

        elif self.requestSent == self.PLAY:
            self.state = self.PLAYING
            self.playEvent.clear()
            # start buffered playback and RTP listening
            self.start_buffered_playback()
            if not self.rtp_listen_thread or not self.rtp_listen_thread.is_alive():
                self.rtp_listen_thread = threading.Thread(target=self.listenRtp, daemon=True)
                self.rtp_listen_thread.start()

        elif self.requestSent == self.PAUSE:
            self.state = self.READY
            self.playEvent.set()

        elif self.requestSent == self.TEARDOWN:
            self.state = self.INIT
            self.teardownAcked = 1
            # close sockets
            try:
                if self.rtpSocket:
                    self.rtpSocket.close()
            except:
                pass
            try:
                if self.rtspSocket:
                    self.rtspSocket.close()
            except:
                pass

    def openRtpPort(self):
        try:
            self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.rtpSocket.settimeout(0.5)
            self.rtpSocket.bind(('', self.rtpPort))
        except Exception:
            tkinter.messagebox.showwarning('Unable to Bind', f'Unable to bind PORT={self.rtpPort}')

    def listenRtp(self):
        while True:
            try:
                data, addr = self.rtpSocket.recvfrom(65535)
            except Exception:
                if self.playEvent.is_set():
                    break
                if self.teardownAcked == 1:
                    break
                continue

            if not data:
                continue

            try:
                packet = RtpPacket()
                packet.decode(data)
            except Exception:
                continue

            try:
                frame_id = packet.frame_id()
                frag_id = packet.fragment_id()
                total_frag = packet.total_fragments()
                payload = packet.get_payload()
            except Exception:
                continue

            self.analyzer.handle_rtp(packet)

            assembled = self.frame_buffer.add_frame_fragment(frame_id, frag_id, total_frag, payload)
            # If frame assembled immediately, we don't need to do anything here; playback thread will consume queue

            # check exit condition
            if self.playEvent.is_set():
                break
            if self.teardownAcked == 1:
                break

    def start_buffered_playback(self):
        if not hasattr(self, "_playback_thread") or not getattr(self, "_playback_thread").is_alive():
            t = threading.Thread(target=self.play_from_buffer, daemon=True)
            self._playback_thread = t
            t.start()

    def play_from_buffer(self):
        delay = 1 / 30
        while True:
            if self.playEvent.is_set() and self.state != self.PLAYING:
                # paused or stopping
                time.sleep(0.01)
                continue
            frame = self.frame_buffer.get_next_frame()
            if frame:
                try:
                    img = Image.open(io.BytesIO(frame))
                    imgtk = ImageTk.PhotoImage(image=img)
                    self.label.configure(image=imgtk)
                    self.label.image = imgtk
                except Exception:
                    pass
                time.sleep(delay)
            else:
                time.sleep(0.005)
            if self.teardownAcked == 1:
                break

    def handler(self):
        self.pauseMovie()
        if tkMessageBox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:
            self.playMovie()