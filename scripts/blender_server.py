import bpy
import socket
import select
import sys
import io
import traceback
import json
import struct

HOST = '127.0.0.1'
PORT = 19090

class BlenderServer:
    def __init__(self, host=HOST, port=PORT):
        self.host = host
        self.port = port
        self.closed = False
        
        # Create TCP socket
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_sock.bind((self.host, self.port))
        self.server_sock.listen(5)
        self.server_sock.setblocking(False)
        
        self.clients = {} # conn -> bytearray (buffer)
        print(f"[Blender Server] Listening on {self.host}:{self.port}")

    def close(self):
        if self.closed:
            return
        self.closed = True
        
        # Close all client connections
        for conn in list(self.clients.keys()):
            try:
                conn.close()
            except Exception as e:
                print(f"[Blender Server] Error closing client: {e}")
        self.clients.clear()
        
        # Close server socket
        try:
            self.server_sock.close()
        except Exception as e:
            print(f"[Blender Server] Error closing server socket: {e}")
            
        print("[Blender Server] Server stopped.")

    def run_tick(self):
        if self.closed:
            return None
            
        # 1. Accept new connections
        try:
            r, w, x = select.select([self.server_sock], [], [], 0)
            if self.server_sock in r:
                conn, addr = self.server_sock.accept()
                conn.setblocking(False)
                self.clients[conn] = bytearray()
                print(f"[Blender Server] Client connected from {addr}")
        except Exception as e:
            # select or accept can throw when non-blocking or closed
            pass

        # 2. Service existing connections
        if not self.clients:
            return 0.1 # run again in 100ms

        try:
            r_clients, _, _ = select.select(list(self.clients.keys()), [], [], 0)
        except Exception as e:
            # Handle case where one of the sockets is bad
            # Clean up bad connections by testing them one by one
            bad_conns = []
            for conn in self.clients:
                try:
                    select.select([conn], [], [], 0)
                except Exception:
                    bad_conns.append(conn)
            for conn in bad_conns:
                print("[Blender Server] Removing bad connection.")
                try:
                    conn.close()
                except:
                    pass
                del self.clients[conn]
            return 0.1

        for conn in r_clients:
            try:
                data = conn.recv(4096)
                if not data:
                    # Client disconnected
                    print("[Blender Server] Client disconnected.")
                    conn.close()
                    del self.clients[conn]
                    continue
                self.clients[conn].extend(data)
            except Exception as e:
                print(f"[Blender Server] Connection read error: {e}")
                try:
                    conn.close()
                except:
                    pass
                del self.clients[conn]
                continue

            # Process any complete packets from buffer
            buffer = self.clients[conn]
            while len(buffer) >= 4:
                # read 4-byte big-endian length prefix
                length = struct.unpack('!I', buffer[:4])[0]
                if len(buffer) < 4 + length:
                    break # Wait for more data

                # Extract the full JSON packet
                packet = buffer[4:4+length]
                # remove from buffer
                del buffer[:4+length]

                # Process the packet
                response = self.process_packet(packet)
                
                # Send response
                try:
                    resp_data = json.dumps(response).encode('utf-8')
                    resp_len = struct.pack('!I', len(resp_data))
                    conn.setblocking(True)
                    conn.sendall(resp_len + resp_data)
                    conn.setblocking(False)
                except Exception as e:
                    print(f"[Blender Server] Error sending response: {e}")
                    try:
                        conn.close()
                    except:
                        pass
                    del self.clients[conn]
                    break
        
        return 0.1

    def process_packet(self, packet_bytes):
        try:
            req = json.loads(packet_bytes.decode('utf-8'))
            code = req.get("code", "")
            
            # Execute code and capture stdout/stderr
            stdout_buf = io.StringIO()
            stderr_buf = io.StringIO()
            
            old_stdout = sys.stdout
            old_stderr = sys.stderr
            sys.stdout = stdout_buf
            sys.stderr = stderr_buf
            
            result = None
            error = None
            try:
                # Try compiling as eval first, then fallback to exec
                try:
                    compiled_code = compile(code, "<blender_repl>", "eval")
                    result = eval(compiled_code, globals(), globals())
                except SyntaxError:
                    compiled_code = compile(code, "<blender_repl>", "exec")
                    exec(compiled_code, globals(), globals())
            except Exception as ex:
                error = "".join(traceback.format_exception(type(ex), ex, ex.__traceback__))
            finally:
                sys.stdout = old_stdout
                sys.stderr = old_stderr

            return {
                "stdout": stdout_buf.getvalue(),
                "stderr": stderr_buf.getvalue(),
                "result": str(result) if result is not None else None,
                "error": error
            }
        except Exception as e:
            return {
                "stdout": "",
                "stderr": "",
                "result": None,
                "error": f"Internal server error: {e}"
            }

def timer_callback():
    server = getattr(bpy, "blender_live_server", None)
    if server is None or server.closed:
        return None # stop the timer
    
    try:
        return server.run_tick()
    except Exception as e:
        print("[Blender Server] Error in server tick:", e)
        return 0.1

def register():
    # Stop existing server if registered
    if hasattr(bpy, "blender_live_server"):
        print("[Blender Server] Stopping existing server instance...")
        try:
            bpy.blender_live_server.close()
        except Exception as e:
            print("[Blender Server] Error stopping existing server:", e)
        delattr(bpy, "blender_live_server")
        
    # Start new server
    try:
        server = BlenderServer()
        bpy.blender_live_server = server
        # Register the timer function to execute ticks in main thread
        bpy.app.timers.register(timer_callback)
        print("[Blender Server] Server successfully started and timer registered!")
    except Exception as e:
        print("[Blender Server] Failed to start server:", e)

if __name__ == "__main__":
    register()
