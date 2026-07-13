import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def start_health():
    port = int(os.getenv("PORT", 8080))
    ThreadingHTTPServer(('0.0.0.0', port), HealthHandler).serve_forever()

if __name__ == "__main__":
    threading.Thread(target=start_health, daemon=True).start()
    print("Test server running")
    while True:
        time.sleep(60)
