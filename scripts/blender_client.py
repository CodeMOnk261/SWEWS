import socket
import struct
import json
import argparse
import sys
import os

HOST = '127.0.0.1'
PORT = 19090

def send_code(code, host=HOST, port=PORT):
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        
        # Prepare payload
        payload = json.dumps({"code": code}).encode('utf-8')
        length_prefix = struct.pack('!I', len(payload))
        
        # Send
        sock.sendall(length_prefix + payload)
        
        # Read response length
        resp_len_data = sock.recv(4)
        if not resp_len_data or len(resp_len_data) < 4:
            print("Error: Did not receive full response length from Blender server.", file=sys.stderr)
            return None
            
        resp_len = struct.unpack('!I', resp_len_data)[0]
        
        # Read response payload
        resp_data = bytearray()
        while len(resp_data) < resp_len:
            packet = sock.recv(min(4096, resp_len - len(resp_data)))
            if not packet:
                break
            resp_data.extend(packet)
            
        if len(resp_data) < resp_len:
            print("Error: Received truncated response from Blender server.", file=sys.stderr)
            return None
            
        response = json.loads(resp_data.decode('utf-8'))
        return response
        
    except ConnectionRefusedError:
        print(f"Error: Connection refused. Is the Blender Live Server running on {host}:{port}?", file=sys.stderr)
        print("Please make sure you have loaded and run scripts/blender_server.py inside Blender's Scripting tab.", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error communicating with Blender server: {e}", file=sys.stderr)
        return None
    finally:
        sock.close()

def run_repl(host=HOST, port=PORT):
    print("----------------------------------------------------------------")
    print(f"Interactive Blender Python REPL connected to {host}:{port}")
    print("Type your Python code. Type 'exit()' or 'quit' to quit.")
    print("----------------------------------------------------------------")
    
    while True:
        try:
            line = input("blender>>> ")
            if line.strip() in ("exit()", "quit", "exit"):
                break
            if not line.strip():
                continue
                
            # If the user wants to start a multiline block, they can prefix with key characters or we can let them type standard python.
            # For simplicity, we just execute the line.
            # If the line ends with ':' or they want to enter multiline mode:
            if line.strip().endswith(':'):
                lines = [line]
                while True:
                    subline = input("       ... ")
                    if not subline:
                        break
                    lines.append(subline)
                code = "\n".join(lines)
            else:
                code = line
                
            res = send_code(code, host, port)
            if res:
                if res.get("stdout"):
                    print(res["stdout"], end="")
                if res.get("stderr"):
                    print(res["stderr"], end="", file=sys.stderr)
                if res.get("error"):
                    print(res["error"], file=sys.stderr)
                elif res.get("result") is not None:
                    print(res["result"])
        except KeyboardInterrupt:
            print("\nKeyboardInterrupt")
            continue
        except EOFError:
            print()
            break

def main():
    parser = argparse.ArgumentParser(description="Blender Live Server Client Interface")
    parser.add_argument("-c", "--code", type=str, help="Python code string to execute in Blender")
    parser.add_argument("-f", "--file", type=str, help="Path to Python file to execute in Blender")
    parser.add_argument("--host", type=str, default=HOST, help="Blender server host (default: 127.0.0.1)")
    parser.add_argument("-p", "--port", type=int, default=PORT, help="Blender server port (default: 19090)")
    
    args = parser.parse_args()
    
    if args.code:
        # Run code string
        res = send_code(args.code, args.host, args.port)
        if res:
            if res.get("stdout"):
                print(res["stdout"], end="")
            if res.get("stderr"):
                print(res["stderr"], end="", file=sys.stderr)
            if res.get("error"):
                print(res["error"], file=sys.stderr)
                sys.exit(1)
            elif res.get("result") is not None:
                print(res["result"])
    elif args.file:
        # Run code from file
        if not os.path.exists(args.file):
            print(f"Error: File '{args.file}' not found.", file=sys.stderr)
            sys.exit(1)
        with open(args.file, 'r', encoding='utf-8') as f:
            code = f.read()
        res = send_code(code, args.host, args.port)
        if res:
            if res.get("stdout"):
                print(res["stdout"], end="")
            if res.get("stderr"):
                print(res["stderr"], end="", file=sys.stderr)
            if res.get("error"):
                print(res["error"], file=sys.stderr)
                sys.exit(1)
            elif res.get("result") is not None:
                print(res["result"])
    else:
        # Start interactive REPL
        # Test connection first
        test = send_code("import bpy; bpy.app.version", args.host, args.port)
        if test is None:
            sys.exit(1)
        run_repl(args.host, args.port)

if __name__ == "__main__":
    main()
